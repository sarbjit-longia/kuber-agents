"""
Market Data Agent

Ensures `state.market_data` is populated for downstream agents.

Note: The current execution engine (`PipelineExecutor`) already fetches market data
before running agents in most paths. This agent is intentionally safe to run as a
no-op when market data is already present, but it is also capable of fetching
from the Data Plane if needed (e.g., for validation/activation consistency).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from app.agents.base import BaseAgent, AgentProcessingError
from app.config import settings
from app.schemas.pipeline_state import AgentConfigSchema, AgentMetadata, MarketData, PipelineState, TimeframeData


class MarketDataAgent(BaseAgent):
    """
    Fetch market candles across required timeframes from the Data Plane and populate `state.market_data`.

    If `state.market_data` is already present, this agent will not refetch (idempotent).
    """

    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="market_data_agent",
            name="Market Data Agent",
            description="Fetches candles across required timeframes and populates market data for downstream agents.",
            category="data",
            version="1.0.0",
            icon="insights",
            pricing_rate=0.0,
            is_free=True,
            requires_timeframes=[],
            requires_market_data=False,
            requires_position=False,
            supported_tools=[],
            config_schema=AgentConfigSchema(
                type="object",
                title="Market Data Agent Configuration",
                description="Optional settings for market data fetch.",
                properties={
                    "lookback_candles": {
                        "type": "integer",
                        "title": "Lookback candles",
                        "description": "Number of candles to fetch per timeframe",
                        "default": 200,
                    }
                },
                required=[],
            ),
            can_initiate_trades=False,
            can_close_positions=False,
        )

    def process(self, state: PipelineState) -> PipelineState:
        if getattr(state, "market_data", None):
            self.log(state, "📈 Market data already present — skipping fetch")
            return state

        symbol = getattr(state, "symbol", None)
        if not symbol:
            raise AgentProcessingError("MarketDataAgent requires state.symbol")

        timeframes: List[str] = list(getattr(state, "timeframes", None) or [])
        if not timeframes:
            # Conservative defaults: enough for most agents to proceed.
            timeframes = ["1m", "5m"]
            state.timeframes = timeframes

        lookback: int = int(self.config.get("lookback_candles", 200) or 200)

        data_plane_url = getattr(settings, "DATA_PLANE_URL", "http://data-plane:8000")

        try:
            self.log(state, f"📡 Fetching market data from Data Plane for {symbol} ({', '.join(timeframes)})")

            timeframe_data: Dict[str, TimeframeData] = {}
            current_price: Optional[float] = None
            bid: Optional[float] = None
            ask: Optional[float] = None

            for tf in timeframes:
                resp = requests.get(
                    f"{data_plane_url}/api/v1/data/candles/{symbol}",
                    params={"timeframe": tf, "limit": lookback},
                    timeout=(5, 20),
                )
                resp.raise_for_status()
                payload = resp.json()

                candles = payload.get("candles") or []
                if not candles:
                    continue

                # Use last candle close as current price proxy
                last = candles[-1]
                last_close = float(last.get("close")) if last.get("close") is not None else None
                if last_close is not None and current_price is None:
                    current_price = last_close
                    bid = last_close
                    ask = last_close

                timeframe_data[tf] = TimeframeData(
                    timeframe=tf,
                    candles=candles,
                    last_updated=datetime.utcnow(),
                )

            if current_price is None:
                raise AgentProcessingError(f"No candles returned from Data Plane for {symbol}")

            state.market_data = MarketData(
                symbol=symbol,
                current_price=current_price,
                bid=bid,
                ask=ask,
                spread=None,
                timeframes=timeframe_data,
                market_status="unknown",
                last_updated=datetime.utcnow(),
            )
            self.log(state, "✅ Market data fetched")
            return state

        except Exception as e:
            raise AgentProcessingError(f"MarketDataAgent failed to fetch data: {str(e)}") from e

