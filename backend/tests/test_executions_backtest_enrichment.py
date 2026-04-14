from app.api.v1.executions import _enrich_backtest_result


def test_enrich_backtest_result_uses_closed_trade_for_execution():
    result = {"backtest_run_id": "run-1"}
    trades = [
        {
            "execution_id": "exec-1",
            "action": "BUY",
            "entry_price": 100.0,
            "exit_price": 110.0,
            "net_pnl": 50.0,
            "exit_reason": "target",
            "exit_time": "2026-04-14T01:00:00",
        }
    ]

    enriched = _enrich_backtest_result(result, "exec-1", trades, {})

    assert enriched["final_pnl"] == 50.0
    assert enriched["trade_outcome"]["status"] == "executed"
    assert enriched["trade_outcome"]["pnl"] == 50.0
    assert enriched["trade_outcome"]["exit_reason"] == "target"


def test_enrich_backtest_result_uses_open_position_when_trade_still_open():
    result = {"backtest_run_id": "run-1"}
    positions = {
        "AAPL": {
            "execution_id": "exec-2",
            "action": "SELL",
            "entry_price": 200.0,
            "mark_price": 190.0,
            "unrealized_pnl": 25.0,
        }
    }

    enriched = _enrich_backtest_result(result, "exec-2", [], positions)

    assert "final_pnl" not in enriched or enriched["final_pnl"] is None
    assert enriched["trade_outcome"]["status"] == "executed"
    assert enriched["trade_outcome"]["pnl"] == 25.0
    assert enriched["trade_outcome"]["entry_price"] == 200.0
    assert enriched["trade_outcome"]["exit_price"] == 190.0
