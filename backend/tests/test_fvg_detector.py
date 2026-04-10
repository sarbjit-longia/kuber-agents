import asyncio

from app.tools.strategy_tools.fvg_detector import FVGDetector


def test_detects_body_based_bullish_and_bearish_fvgs():
    candles = [
        {
            "timestamp": "2026-04-09T09:30:00",
            "open": 100.00,
            "high": 101.20,
            "low": 99.80,
            "close": 101.00,
            "volume": 1000,
        },
        {
            "timestamp": "2026-04-09T09:35:00",
            "open": 101.10,
            "high": 103.50,
            "low": 101.00,
            "close": 103.20,
            "volume": 1200,
        },
        {
            "timestamp": "2026-04-09T09:40:00",
            "open": 102.40,
            "high": 102.80,
            "low": 101.90,
            "close": 102.60,
            "volume": 1100,
        },
        {
            "timestamp": "2026-04-09T09:45:00",
            "open": 102.20,
            "high": 102.30,
            "low": 99.20,
            "close": 99.40,
            "volume": 1250,
        },
        {
            "timestamp": "2026-04-09T09:50:00",
            "open": 98.20,
            "high": 98.70,
            "low": 97.90,
            "close": 98.40,
            "volume": 900,
        },
    ]

    detector = FVGDetector(timeframe="5m", min_gap_pips=10, lookback_periods=10)
    result = asyncio.run(detector.detect(candles))

    bullish = next(fvg for fvg in result["fvgs"] if fvg["type"] == "bullish")
    assert bullish["low"] == 101.00
    assert bullish["high"] == 102.40
    assert bullish["gap_basis"] == "body"
    assert bullish["middle_candle_at"] == "2026-04-09T09:35:00"

    bearish = next(fvg for fvg in result["fvgs"] if fvg["type"] == "bearish")
    assert bearish["low"] == 98.40
    assert bearish["high"] == 102.40
    assert bearish["gap_basis"] == "body"
    assert bearish["middle_candle_at"] == "2026-04-09T09:45:00"
