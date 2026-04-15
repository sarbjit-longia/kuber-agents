import asyncio

from app.tools.strategy_tools.order_block_detector import OrderBlockDetector


def test_detects_bullish_and_bearish_order_blocks():
    candles = [
        {"timestamp": "2026-04-09T09:30:00", "open": 101.0, "high": 101.1, "low": 99.8, "close": 100.0, "volume": 100},
        {"timestamp": "2026-04-09T09:35:00", "open": 100.1, "high": 102.3, "low": 100.0, "close": 102.2, "volume": 140},
        {"timestamp": "2026-04-09T09:40:00", "open": 102.2, "high": 103.0, "low": 102.1, "close": 102.8, "volume": 120},
        {"timestamp": "2026-04-09T09:45:00", "open": 102.9, "high": 103.0, "low": 100.4, "close": 100.6, "volume": 130},
        {"timestamp": "2026-04-09T09:50:00", "open": 100.5, "high": 100.7, "low": 98.4, "close": 98.6, "volume": 150},
        {"timestamp": "2026-04-09T09:55:00", "open": 98.5, "high": 98.6, "low": 97.9, "close": 98.0, "volume": 110},
    ]

    detector = OrderBlockDetector(timeframe="5m", min_move_pips=10, lookback_periods=20)
    result = asyncio.run(detector.detect(candles))

    bullish = next(block for block in result["order_blocks"] if block["type"] == "bullish")
    assert bullish["low"] == 100.0
    assert bullish["high"] == 101.0
    assert bullish["zone_basis"] == "body"

    bearish = next(block for block in result["order_blocks"] if block["type"] == "bearish")
    assert bearish["low"] == 100.1
    assert bearish["high"] == 102.2
    assert bearish["zone_basis"] == "body"
