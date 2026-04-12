"""
Redis-backed broker state for backtests.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import redis

from app.backtesting.simulation import CommissionModel, ExecutionSimulator, SlippageModel
from app.config import settings

if TYPE_CHECKING:
    from app.backtesting.engine import Trade


class BacktestBroker:
    def __init__(
        self,
        run_id: str,
        initial_capital: float,
        slippage_model: str = "fixed",
        slippage_value: float = 0.01,
        commission_model: str = "per_share",
        commission_value: float = 0.005,
    ):
        self.run_id = run_id
        self.redis = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        self.simulator = ExecutionSimulator(
            slippage=SlippageModel(slippage_model, slippage_value),
            commission=CommissionModel(commission_model, commission_value),
        )
        self.initial_capital = initial_capital
        self._ensure_account()

    def _key(self, suffix: str) -> str:
        return f"backtest:{self.run_id}:{suffix}"

    def _ensure_account(self) -> None:
        key = self._key("account")
        if not self.redis.exists(key):
            self.redis.set(
                key,
                json.dumps(
                    {
                        "cash": self.initial_capital,
                        "equity": self.initial_capital,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                ),
            )

    def get_account(self) -> Dict[str, Any]:
        raw = self.redis.get(self._key("account"))
        if not raw:
            self._ensure_account()
            raw = self.redis.get(self._key("account"))
        return json.loads(raw)

    def _save_account(self, account: Dict[str, Any]) -> None:
        account["updated_at"] = datetime.utcnow().isoformat()
        self.redis.set(self._key("account"), json.dumps(account))

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        raw = self.redis.get(self._key("positions"))
        return json.loads(raw) if raw else {}

    def _save_positions(self, positions: Dict[str, Dict[str, Any]]) -> None:
        self.redis.set(self._key("positions"), json.dumps(positions))

    def open_position(
        self,
        symbol: str,
        action: str,
        qty: float,
        entry_price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        execution_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        positions = self.get_positions()
        if symbol in positions:
            return positions[symbol]

        fill_price = self.simulator.apply_slippage(entry_price, action)
        commission = self.simulator.commission.calculate(fill_price, qty)
        account = self.get_account()
        account["cash"] = float(account.get("cash", self.initial_capital)) - commission
        self._save_account(account)

        position = {
            "symbol": symbol,
            "action": action,
            "qty": qty,
            "entry_price": fill_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "commission": commission,
            "execution_id": execution_id,
            "opened_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        positions[symbol] = position
        self._save_positions(positions)
        return position

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str,
        closed_at: Optional[datetime] = None,
    ) -> Optional[Trade]:
        from app.backtesting.engine import Trade

        positions = self.get_positions()
        position = positions.pop(symbol, None)
        if not position:
            return None

        side = position["action"]
        qty = float(position["qty"])
        fill_exit = self.simulator.apply_slippage(exit_price, "SELL" if side == "BUY" else "BUY")
        exit_commission = self.simulator.commission.calculate(fill_exit, qty)
        gross_pnl = (fill_exit - position["entry_price"]) * qty if side == "BUY" else (position["entry_price"] - fill_exit) * qty
        net_pnl = gross_pnl - float(position["commission"]) - exit_commission

        trade = Trade(
            strategy_family=position["metadata"].get("strategy_family", ""),
            action=side,
            entry_time=datetime.fromisoformat(position["opened_at"]),
            exit_time=closed_at or datetime.utcnow(),
            entry_price=float(position["entry_price"]),
            exit_price=float(fill_exit),
            stop_loss=float(position["stop_loss"] or 0),
            take_profit=float(position["take_profit"] or 0),
            position_size=qty,
            gross_pnl=gross_pnl,
            commission=float(position["commission"]) + exit_commission,
            slippage=abs(float(position["entry_price"]) - float(position["metadata"].get("signal_entry_price", position["entry_price"]))),
            net_pnl=net_pnl,
            exit_reason=exit_reason,
            regime=position["metadata"].get("regime", ""),
            session=position["metadata"].get("session", ""),
            duration_bars=int(position["metadata"].get("duration_bars", 0)),
            r_multiple=float(position["metadata"].get("r_multiple", 0.0)),
        )

        trades_key = self._key("trades")
        trades = json.loads(self.redis.get(trades_key) or "[]")
        trades.append(asdict(trade))
        self.redis.set(trades_key, json.dumps(trades, default=str))

        account = self.get_account()
        account["cash"] = float(account.get("cash", self.initial_capital)) + net_pnl
        account["equity"] = account["cash"]
        self._save_account(account)
        self._save_positions(positions)
        return trade

    def evaluate_bar(self, symbol: str, candle: Dict[str, Any]) -> Optional[Trade]:
        position = self.get_positions().get(symbol)
        if not position:
            return None
        action = position["action"]
        stop_loss = position.get("stop_loss")
        take_profit = position.get("take_profit")
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        ts = candle.get("timestamp") or candle.get("time")
        closed_at = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else datetime.utcnow()

        if action == "BUY":
            if stop_loss and low <= float(stop_loss):
                return self.close_position(symbol, float(stop_loss), "stop", closed_at)
            if take_profit and high >= float(take_profit):
                return self.close_position(symbol, float(take_profit), "target", closed_at)
        else:
            if stop_loss and high >= float(stop_loss):
                return self.close_position(symbol, float(stop_loss), "stop", closed_at)
            if take_profit and low <= float(take_profit):
                return self.close_position(symbol, float(take_profit), "target", closed_at)

        account = self.get_account()
        account["equity"] = float(account.get("cash", self.initial_capital))
        unrealized = (close - float(position["entry_price"])) * float(position["qty"]) if action == "BUY" else (float(position["entry_price"]) - close) * float(position["qty"])
        account["equity"] += unrealized
        self._save_account(account)
        return None

    def get_closed_trades(self) -> List[Dict[str, Any]]:
        return json.loads(self.redis.get(self._key("trades")) or "[]")

    def get_equity(self) -> float:
        return float(self.get_account().get("equity", self.initial_capital))
