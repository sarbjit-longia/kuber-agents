"""
OpenAI-compatible tool adapters for LLM agents.

These tools replace the old CrewAI-specific wrappers while preserving the
same tool names and broadly similar textual outputs for prompts and parsing.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog

from app.tools.strategy_tools.fvg_detector import FVGDetector
from app.tools.strategy_tools.indicator_tools import IndicatorTools
from app.tools.strategy_tools.liquidity_analyzer import LiquidityAnalyzer
from app.tools.strategy_tools.market_structure import MarketStructureAnalyzer
from app.tools.strategy_tools.premium_discount import PremiumDiscountAnalyzer

logger = structlog.get_logger()


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@dataclass
class OpenAIToolDefinition:
    name: str
    schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], str]


def _rsi_handler(ticker: str) -> Callable[[Dict[str, Any]], str]:
    def handler(arguments: Dict[str, Any]) -> str:
        timeframe = arguments.get("timeframe", "1h")
        period = int(arguments.get("period", 14))
        threshold_oversold = int(arguments.get("threshold_oversold", 30))
        threshold_overbought = int(arguments.get("threshold_overbought", 70))

        indicator_tools = IndicatorTools(ticker=ticker)
        result = _run_async(indicator_tools.get_rsi(timeframe=timeframe, period=period))

        current_rsi = result.get("current_rsi", 0)
        is_oversold = current_rsi < threshold_oversold
        is_overbought = current_rsi > threshold_overbought

        interpretation = "neutral"
        if is_oversold:
            interpretation = f"OVERSOLD (RSI < {threshold_oversold})"
        elif is_overbought:
            interpretation = f"OVERBOUGHT (RSI > {threshold_overbought})"

        return (
            f"RSI Analysis for {ticker} on {timeframe}:\n"
            f"  Current RSI: {current_rsi:.2f}\n"
            f"  Previous RSI: {result.get('previous_rsi', 0):.2f}\n"
            f"  Status: {interpretation}\n"
            f"  Thresholds: Oversold={threshold_oversold}, Overbought={threshold_overbought}\n"
            f"\nInterpretation: {'Potential BUY signal (oversold)' if is_oversold else 'Potential SELL signal (overbought)' if is_overbought else 'Neutral momentum'}"
        )

    return handler


def _macd_handler(ticker: str) -> Callable[[Dict[str, Any]], str]:
    def handler(arguments: Dict[str, Any]) -> str:
        timeframe = arguments.get("timeframe", "1h")
        indicator_tools = IndicatorTools(ticker=ticker)
        result = _run_async(indicator_tools.get_macd(timeframe=timeframe))

        macd = result.get("current_macd", 0)
        signal = result.get("current_signal", 0)
        histogram = result.get("current_histogram", 0)
        is_bullish_cross = result.get("is_bullish_crossover", False)
        is_bearish_cross = result.get("is_bearish_crossover", False)

        signal_text = "NEUTRAL"
        if is_bullish_cross:
            signal_text = "BULLISH CROSSOVER (Buy signal)"
        elif is_bearish_cross:
            signal_text = "BEARISH CROSSOVER (Sell signal)"

        return (
            f"MACD Analysis for {ticker} on {timeframe}:\n"
            f"  MACD Line: {macd:.4f}\n"
            f"  Signal Line: {signal:.4f}\n"
            f"  Histogram: {histogram:.4f}\n"
            f"  Signal: {signal_text}\n"
            f"\nInterpretation: {'Bullish momentum - consider long positions' if is_bullish_cross else 'Bearish momentum - consider short positions' if is_bearish_cross else 'No clear crossover signal'}"
        )

    return handler


def _sma_handler(ticker: str) -> Callable[[Dict[str, Any]], str]:
    def handler(arguments: Dict[str, Any]) -> str:
        timeframe = arguments.get("timeframe", "1h")
        fast_period = int(arguments.get("fast_period", 20))
        slow_period = int(arguments.get("slow_period", 50))

        indicator_tools = IndicatorTools(ticker=ticker)
        result = _run_async(
            indicator_tools.get_sma_crossover(
                timeframe=timeframe,
                fast_period=fast_period,
                slow_period=slow_period,
            )
        )

        fast_sma = result.get("current_fast_sma", 0)
        slow_sma = result.get("current_slow_sma", 0)
        is_bullish = result.get("is_bullish_crossover", False)
        is_bearish = result.get("is_bearish_crossover", False)
        trend = result.get("trend", "unknown")

        signal_text = "NO CROSSOVER"
        if is_bullish:
            signal_text = f"BULLISH CROSSOVER (SMA{fast_period} > SMA{slow_period})"
        elif is_bearish:
            signal_text = f"BEARISH CROSSOVER (SMA{fast_period} < SMA{slow_period})"

        interpretation = f"{trend.capitalize()} trend confirmed" if trend != "unknown" else "Sideways market"
        return (
            f"SMA Crossover Analysis for {ticker} on {timeframe}:\n"
            f"  Fast SMA ({fast_period}): ${fast_sma:.2f}\n"
            f"  Slow SMA ({slow_period}): ${slow_sma:.2f}\n"
            f"  Current Trend: {trend.upper()}\n"
            f"  Signal: {signal_text}\n"
            f"\nInterpretation: {interpretation}"
        )

    return handler


def _fvg_handler(ticker: str, candles: List[Dict[str, Any]]) -> Callable[[Dict[str, Any]], str]:
    def handler(arguments: Dict[str, Any]) -> str:
        timeframe = arguments.get("timeframe", "5m")
        lookback_candles = int(arguments.get("lookback_candles", 50))

        detector = FVGDetector(ticker=ticker, candles=candles)
        result = detector.detect_fvgs(timeframe=timeframe, lookback_candles=lookback_candles)

        bullish_fvgs = [fvg for fvg in result.get("fvgs", []) if fvg["type"] == "bullish"]
        bearish_fvgs = [fvg for fvg in result.get("fvgs", []) if fvg["type"] == "bearish"]
        latest_bullish = bullish_fvgs[-1] if bullish_fvgs else None
        latest_bearish = bearish_fvgs[-1] if bearish_fvgs else None

        output = f"FVG Detection for {ticker} on {timeframe}:\n"
        output += f"  Total FVGs found: {len(result.get('fvgs', []))}\n"
        output += f"  Bullish FVGs: {len(bullish_fvgs)}\n"
        output += f"  Bearish FVGs: {len(bearish_fvgs)}\n\n"

        if latest_bullish:
            output += "Latest Bullish FVG:\n"
            output += f"  Range: ${latest_bullish['low']:.2f} - ${latest_bullish['high']:.2f}\n"
            output += f"  Status: {'Filled' if latest_bullish['is_filled'] else 'Unfilled'}\n"
            output += f"  Gap Size: {latest_bullish['gap_size_pips']:.1f} pips\n\n"

        if latest_bearish:
            output += "Latest Bearish FVG:\n"
            output += f"  Range: ${latest_bearish['low']:.2f} - ${latest_bearish['high']:.2f}\n"
            output += f"  Status: {'Filled' if latest_bearish['is_filled'] else 'Unfilled'}\n"
            output += f"  Gap Size: {latest_bearish['gap_size_pips']:.1f} pips\n\n"

        return output + "Interpretation: Unfilled FVGs are potential reversal zones."

    return handler


def _liquidity_handler(ticker: str, candles: List[Dict[str, Any]]) -> Callable[[Dict[str, Any]], str]:
    def handler(arguments: Dict[str, Any]) -> str:
        timeframe = arguments.get("timeframe", "5m")
        lookback_candles = int(arguments.get("lookback_candles", 100))
        analyzer = LiquidityAnalyzer(ticker=ticker, candles=candles)
        result = analyzer.analyze_liquidity(timeframe=timeframe, lookback_candles=lookback_candles)

        pools = result.get("active_liquidity_pools", {})
        grabs = result.get("liquidity_grabs", [])

        output = f"Liquidity Analysis for {ticker} on {timeframe}:\n"
        output += f"  Buy-side liquidity levels (above price): {len(pools.get('above', []))}\n"
        output += f"  Sell-side liquidity levels (below price): {len(pools.get('below', []))}\n"
        output += f"  Recent liquidity grabs: {len(grabs)}\n\n"

        if grabs:
            latest_grab = grabs[-1]
            output += "Latest Liquidity Grab:\n"
            output += f"  Type: {latest_grab['type']}\n"
            output += f"  Level: ${latest_grab['level']:.2f}\n"
            output += f"  Reversed: {latest_grab.get('reversed', False)}\n\n"

        return output + "Interpretation: Recent liquidity grabs with reversals signal institutional accumulation/distribution."

    return handler


def _market_structure_handler(ticker: str, candles: List[Dict[str, Any]]) -> Callable[[Dict[str, Any]], str]:
    def handler(arguments: Dict[str, Any]) -> str:
        timeframe = arguments.get("timeframe", "1h")
        lookback_candles = int(arguments.get("lookback_candles", 100))
        analyzer = MarketStructureAnalyzer(ticker=ticker, candles=candles)
        result = analyzer.analyze_structure(timeframe=timeframe, lookback_candles=lookback_candles)

        trend = result.get("trend", "ranging")
        events = result.get("structure_events", [])

        output = f"Market Structure for {ticker} on {timeframe}:\n"
        output += f"  Current Trend: {trend.upper()}\n"
        output += f"  Structure Events: {len(events)}\n\n"

        if events:
            latest = events[-1]
            output += "Latest Event:\n"
            output += f"  Type: {latest['type']} ({latest['direction']})\n"
            output += f"  Level: ${latest['level']:.2f}\n\n"

        return output + f"Interpretation: {trend.capitalize()} market structure confirmed."

    return handler


def _premium_discount_handler(ticker: str, candles: List[Dict[str, Any]]) -> Callable[[Dict[str, Any]], str]:
    def handler(arguments: Dict[str, Any]) -> str:
        timeframe = arguments.get("timeframe", "4h")
        lookback_candles = int(arguments.get("lookback_candles", 50))
        analyzer = PremiumDiscountAnalyzer(ticker=ticker, candles=candles)
        result = analyzer.analyze_zones(timeframe=timeframe, lookback_candles=lookback_candles)

        zone = result.get("zone", "equilibrium")
        price_level = result.get("price_level_percent", 50)

        output = f"Premium/Discount Analysis for {ticker} on {timeframe}:\n"
        output += f"  Current Zone: {zone.upper()}\n"
        output += f"  Price Level: {price_level:.0f}% of range\n\n"

        if zone == "discount":
            output += "Interpretation: Price in DISCOUNT zone (0-30%) - favorable for LONG entries"
        elif zone == "premium":
            output += "Interpretation: Price in PREMIUM zone (70-100%) - favorable for SHORT entries"
        else:
            output += "Interpretation: Price in EQUILIBRIUM zone (40-60%) - wait for better price"

        return output

    return handler


def _tool_schema(name: str, description: str, properties: Dict[str, Any], required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


def build_openai_tools(tool_names: List[str], *, ticker: str, candles: Optional[List[Dict[str, Any]]] = None) -> List[OpenAIToolDefinition]:
    candle_tools = {"fvg_detector", "liquidity_analyzer", "market_structure_analyzer", "premium_discount_analyzer"}
    tools: List[OpenAIToolDefinition] = []

    for name in tool_names:
        if name == "rsi_calculator":
            tools.append(
                OpenAIToolDefinition(
                    name=name,
                    schema=_tool_schema(
                        name,
                        "Calculates RSI to measure momentum and overbought/oversold conditions.",
                        {
                            "timeframe": {"type": "string", "default": "1h"},
                            "period": {"type": "integer", "default": 14},
                            "threshold_oversold": {"type": "integer", "default": 30},
                            "threshold_overbought": {"type": "integer", "default": 70},
                        },
                    ),
                    handler=_rsi_handler(ticker),
                )
            )
        elif name == "macd_calculator":
            tools.append(
                OpenAIToolDefinition(
                    name=name,
                    schema=_tool_schema(
                        name,
                        "Calculates MACD to measure trend direction and momentum.",
                        {
                            "timeframe": {"type": "string", "default": "1h"},
                            "fast_period": {"type": "integer", "default": 12},
                            "slow_period": {"type": "integer", "default": 26},
                            "signal_period": {"type": "integer", "default": 9},
                        },
                    ),
                    handler=_macd_handler(ticker),
                )
            )
        elif name == "sma_crossover":
            tools.append(
                OpenAIToolDefinition(
                    name=name,
                    schema=_tool_schema(
                        name,
                        "Detects fast/slow SMA crossovers for trend changes and moving average levels.",
                        {
                            "timeframe": {"type": "string", "default": "1h"},
                            "fast_period": {"type": "integer", "default": 20},
                            "slow_period": {"type": "integer", "default": 50},
                        },
                    ),
                    handler=_sma_handler(ticker),
                )
            )
        elif name in candle_tools and candles:
            if name == "fvg_detector":
                tools.append(
                    OpenAIToolDefinition(
                        name=name,
                        schema=_tool_schema(
                            name,
                            "Detects Fair Value Gaps (FVGs) and other imbalances in price action.",
                            {
                                "timeframe": {"type": "string", "default": "5m"},
                                "lookback_candles": {"type": "integer", "default": 50},
                            },
                        ),
                        handler=_fvg_handler(ticker, candles),
                    )
                )
            elif name == "liquidity_analyzer":
                tools.append(
                    OpenAIToolDefinition(
                        name=name,
                        schema=_tool_schema(
                            name,
                            "Analyzes liquidity pools and liquidity grabs.",
                            {
                                "timeframe": {"type": "string", "default": "5m"},
                                "lookback_candles": {"type": "integer", "default": 100},
                            },
                        ),
                        handler=_liquidity_handler(ticker, candles),
                    )
                )
            elif name == "market_structure_analyzer":
                tools.append(
                    OpenAIToolDefinition(
                        name=name,
                        schema=_tool_schema(
                            name,
                            "Analyzes market structure, BOS, and CHoCH events.",
                            {
                                "timeframe": {"type": "string", "default": "1h"},
                                "lookback_candles": {"type": "integer", "default": 100},
                            },
                        ),
                        handler=_market_structure_handler(ticker, candles),
                    )
                )
            elif name == "premium_discount_analyzer":
                tools.append(
                    OpenAIToolDefinition(
                        name=name,
                        schema=_tool_schema(
                            name,
                            "Analyzes premium, discount, and equilibrium zones.",
                            {
                                "timeframe": {"type": "string", "default": "4h"},
                                "lookback_candles": {"type": "integer", "default": 50},
                            },
                        ),
                        handler=_premium_discount_handler(ticker, candles),
                    )
                )

    logger.info("openai_tools_built", ticker=ticker, tool_count=len(tools), tool_names=[tool.name for tool in tools])
    return tools


def tool_schemas(tools: List[OpenAIToolDefinition]) -> List[Dict[str, Any]]:
    return [tool.schema for tool in tools]


def tool_handler_map(tools: List[OpenAIToolDefinition]) -> Dict[str, Callable[[Dict[str, Any]], str]]:
    return {tool.name: tool.handler for tool in tools}
