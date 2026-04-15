import asyncio

from app.tools.strategy_tools.session_context_analyzer import SessionContextAnalyzer


def test_detects_ny_killzone_and_session_levels():
    candles = [
        {"timestamp": "2026-04-09T13:00:00+00:00", "open": 100.0, "high": 100.5, "low": 99.8, "close": 100.3, "volume": 100},
        {"timestamp": "2026-04-09T13:30:00+00:00", "open": 100.4, "high": 100.8, "low": 100.2, "close": 100.6, "volume": 100},
        {"timestamp": "2026-04-09T14:00:00+00:00", "open": 100.7, "high": 101.2, "low": 100.6, "close": 101.0, "volume": 100},
    ]

    analyzer = SessionContextAnalyzer(timeframe="5m")
    result = asyncio.run(analyzer.analyze(candles))

    assert result["current_session"] == "ny_am"
    assert result["current_killzone"] == "ny_killzone"
    assert result["true_session_open"] == 100.0
