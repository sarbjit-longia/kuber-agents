from datetime import datetime, timedelta

from app.schemas.pipeline_state import StrategyResult
from app.services.chart_annotation_builder import ChartAnnotationBuilder


def _candles(base_price: float = 255.0, count: int = 30):
    start = datetime(2026, 4, 8, 14, 0, 0)
    candles = []
    for i in range(count):
        price = base_price + (i * 0.1)
        candles.append({
            "timestamp": (start + timedelta(minutes=5 * i)).isoformat(),
            "open": price - 0.2,
            "high": price + 0.3,
            "low": price - 0.4,
            "close": price,
            "volume": 100000 + i * 1000,
        })
    return candles


class TestChartAnnotationBuilder:
    def test_keeps_only_trade_relevant_fvg_and_swing_levels(self):
        builder = ChartAnnotationBuilder(symbol="AAPL", timeframe="5m")
        strategy = StrategyResult(
            action="BUY",
            confidence=0.81,
            entry_price=255.10,
            stop_loss=254.55,
            take_profit=256.40,
            reasoning="Bullish FVG retest with RSI confirmation and swing low stop placement.",
            pattern_detected="Bullish FVG",
        )

        tool_results = {
            "fvg_detector": {
                "fvgs": [
                    {
                        "type": "bullish",
                        "low": 255.00,
                        "high": 255.20,
                        "formed_at": "2026-04-08T15:00:00",
                        "gap_size_pips": 20.0,
                        "is_filled": False,
                        "fill_percentage": 10,
                    },
                    {
                        "type": "bullish",
                        "low": 252.00,
                        "high": 252.30,
                        "formed_at": "2026-04-08T13:00:00",
                        "gap_size_pips": 18.0,
                        "is_filled": False,
                        "fill_percentage": 0,
                    },
                    {
                        "type": "bearish",
                        "low": 256.80,
                        "high": 257.10,
                        "formed_at": "2026-04-08T14:10:00",
                        "gap_size_pips": 15.0,
                        "is_filled": False,
                        "fill_percentage": 0,
                    },
                ]
            },
            "market_structure": {
                "trend": "bullish",
                "swing_lows": [
                    {"price": 254.52, "timestamp": "2026-04-08T15:10:00"},
                    {"price": 253.20, "timestamp": "2026-04-08T14:00:00"},
                ],
                "swing_highs": [
                    {"price": 256.42, "timestamp": "2026-04-08T15:20:00"},
                    {"price": 257.80, "timestamp": "2026-04-08T14:20:00"},
                ],
                "structure_events": [
                    {"type": "BOS", "direction": "bullish", "level": 256.10, "timestamp": "2026-04-08T15:15:00"}
                ],
            },
            "premium_discount": {
                "zone": "discount",
                "price_level_percent": 25,
                "zones": {
                    "discount": {"low": 254.0, "high": 255.0},
                    "equilibrium": {"low": 255.0, "high": 256.0},
                    "premium": {"low": 256.0, "high": 257.0},
                },
            },
        }

        chart_data = builder.build_chart_data(
            candles=_candles(),
            tool_results=tool_results,
            strategy_result=strategy,
            instructions="Use RSI and a bullish FVG retest. Stop under swing low, target recent swing high.",
        )

        annotations = chart_data["annotations"]
        assert len(annotations["shapes"]) == 1
        assert annotations["shapes"][0]["price1"] == 255.00
        assert annotations["shapes"][0]["price2"] == 255.20

        swing_markers = [m for m in annotations["markers"] if m.get("text") in {"Stop Swing", "Target Swing"}]
        assert len(swing_markers) == 2
        assert {m["text"] for m in swing_markers} == {"Stop Swing", "Target Swing"}

        assert annotations["zones"] == []
        assert annotations["arrows"] == []

        line_labels = {line["label"]["text"] for line in annotations["lines"] if line.get("label")}
        assert "Stop Swing" in line_labels
        assert "Target Swing" in line_labels

    def test_only_keeps_indicators_explicitly_used_by_trade(self):
        builder = ChartAnnotationBuilder(symbol="AAPL", timeframe="5m")
        strategy = StrategyResult(
            action="SELL",
            confidence=0.72,
            entry_price=255.00,
            stop_loss=255.60,
            take_profit=253.80,
            reasoning="MACD rolled over into a bearish cross at entry.",
            pattern_detected="",
        )

        tool_results = {
            "rsi": {
                "values": [50, 51, 52],
                "current_rsi": 52,
                "is_oversold": False,
                "is_overbought": False,
            },
            "macd": {
                "values": {
                    "macd": [0.2, 0.1, -0.1],
                    "signal": [0.1, 0.1, 0.0],
                    "histogram": [0.1, 0.0, -0.1],
                },
                "is_bullish_crossover": False,
                "is_bearish_crossover": True,
            },
        }

        chart_data = builder.build_chart_data(
            candles=_candles(),
            tool_results=tool_results,
            strategy_result=strategy,
            instructions="Use MACD cross for the trade decision.",
        )

        assert "macd" in chart_data["indicators"]
        assert "rsi" not in chart_data["indicators"]
        assert chart_data["meta"]["trade_relevance"]["indicator_count"] == 1
