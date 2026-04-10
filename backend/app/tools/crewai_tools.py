"""
CrewAI Tool Wrappers - Standard tool implementations for LLM agents

These tools follow CrewAI's BaseTool pattern with proper schemas,
allowing LLMs to automatically discover and use them based on natural language instructions.
"""
import structlog
from typing import Type, Optional, Any, Dict
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from app.tools.strategy_tools.indicator_tools import IndicatorTools
from app.tools.strategy_tools.fvg_detector import FVGDetector
from app.tools.strategy_tools.liquidity_analyzer import LiquidityAnalyzer
from app.tools.strategy_tools.market_structure import MarketStructureAnalyzer
from app.tools.strategy_tools.premium_discount import PremiumDiscountAnalyzer

logger = structlog.get_logger()


# ============================================================================
# INPUT SCHEMAS (Pydantic models for tool parameters)
# ============================================================================

class RSIInput(BaseModel):
    """Input schema for RSI calculator."""
    timeframe: str = Field(
        description="Timeframe to analyze (5m, 15m, 30m, 1h, 4h, 1d)",
        default="1h"
    )
    period: int = Field(
        description="RSI period (typically 14)",
        default=14
    )
    threshold_oversold: int = Field(
        description="Oversold threshold (typically 30)",
        default=30
    )
    threshold_overbought: int = Field(
        description="Overbought threshold (typically 70)",
        default=70
    )


class MACDInput(BaseModel):
    """Input schema for MACD calculator."""
    timeframe: str = Field(
        description="Timeframe to analyze",
        default="1h"
    )
    fast_period: int = Field(description="Fast EMA period", default=12)
    slow_period: int = Field(description="Slow EMA period", default=26)
    signal_period: int = Field(description="Signal line period", default=9)


class SMAInput(BaseModel):
    """Input schema for SMA crossover."""
    timeframe: str = Field(description="Timeframe to analyze", default="1h")
    fast_period: int = Field(description="Fast SMA period", default=20)
    slow_period: int = Field(description="Slow SMA period", default=50)


class FVGInput(BaseModel):
    """Input schema for FVG (Fair Value Gap) detector."""
    timeframe: str = Field(description="Timeframe to analyze", default="5m")
    lookback_candles: int = Field(
        description="Number of candles to analyze",
        default=50
    )


class LiquidityInput(BaseModel):
    """Input schema for liquidity analyzer."""
    timeframe: str = Field(description="Timeframe to analyze", default="5m")
    lookback_candles: int = Field(default=100)


class MarketStructureInput(BaseModel):
    """Input schema for market structure analyzer."""
    timeframe: str = Field(description="Timeframe to analyze", default="1h")
    lookback_candles: int = Field(default=100)


class PremiumDiscountInput(BaseModel):
    """Input schema for premium/discount zone analyzer."""
    timeframe: str = Field(description="Timeframe to analyze", default="4h")
    lookback_candles: int = Field(default=50)


# ============================================================================
# CREWAI TOOL IMPLEMENTATIONS
# ============================================================================

class RSITool(BaseTool):
    """
    Calculate RSI (Relative Strength Index) indicator.
    
    RSI measures momentum and identifies overbought/oversold conditions.
    - RSI > 70: Overbought (potential sell signal)
    - RSI < 30: Oversold (potential buy signal)
    """
    name: str = "rsi_calculator"
    description: str = (
        "Calculates RSI-14 to measure momentum and identify overbought/oversold extremes. "
        "Call this for any strategy that mentions RSI, momentum, divergence, oversold/overbought, or mean-reversion. "
        "RSI > 70 = overbought (caution for longs); RSI < 30 = oversold (caution for shorts). "
        "Focus on RSI direction as trend confirmation and watch for bullish divergence "
        "(price lower low, RSI higher low) near support as a high-probability reversal signal. "
        "Use as confirmation alongside FVG or market structure tools."
    )
    args_schema: Type[BaseModel] = RSIInput
    
    ticker: str = Field(description="Stock symbol to analyze")
    
    def _run(
        self,
        timeframe: str = "1h",
        period: int = 14,
        threshold_oversold: int = 30,
        threshold_overbought: int = 70
    ) -> str:
        """Execute RSI calculation."""
        try:
            import asyncio
            indicator_tools = IndicatorTools(ticker=self.ticker)
            
            # Run async function in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                indicator_tools.get_rsi(timeframe=timeframe, period=period)
            )
            loop.close()
            
            # Format for LLM consumption
            current_rsi = result.get("current_rsi", 0)
            
            # Apply user-defined thresholds
            is_oversold = current_rsi < threshold_oversold
            is_overbought = current_rsi > threshold_overbought
            
            interpretation = "neutral"
            if is_oversold:
                interpretation = f"OVERSOLD (RSI < {threshold_oversold})"
            elif is_overbought:
                interpretation = f"OVERBOUGHT (RSI > {threshold_overbought})"
            
            return (
                f"RSI Analysis for {self.ticker} on {timeframe}:\n"
                f"  Current RSI: {current_rsi:.2f}\n"
                f"  Previous RSI: {result.get('previous_rsi', 0):.2f}\n"
                f"  Status: {interpretation}\n"
                f"  Thresholds: Oversold={threshold_oversold}, Overbought={threshold_overbought}\n"
                f"\nInterpretation: {'Potential BUY signal (oversold)' if is_oversold else 'Potential SELL signal (overbought)' if is_overbought else 'Neutral momentum'}"
            )
        except Exception as e:
            logger.error("rsi_tool_failed", error=str(e))
            return f"Error calculating RSI: {str(e)}"


class MACDTool(BaseTool):
    """
    Calculate MACD (Moving Average Convergence Divergence) indicator.
    
    MACD identifies trend direction and momentum through crossovers.
    - Bullish crossover: MACD crosses above signal line
    - Bearish crossover: MACD crosses below signal line
    """
    name: str = "macd_calculator"
    description: str = (
        "Calculates MACD (12/26/9) to show trend direction and momentum strength. "
        "Call this when the user mentions MACD, momentum, histogram, crossover, or trend-following strategies. "
        "Bullish crossover (MACD line crosses above signal) = buy bias; bearish = sell bias. "
        "Histogram expansion confirms strengthening momentum; contraction signals fading momentum ahead of reversal. "
        "Use as a secondary confirmation tool alongside structure or FVG analysis."
    )
    args_schema: Type[BaseModel] = MACDInput
    
    ticker: str = Field(description="Stock symbol")
    
    def _run(
        self,
        timeframe: str = "1h",
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> str:
        """Execute MACD calculation."""
        try:
            import asyncio
            indicator_tools = IndicatorTools(ticker=self.ticker)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                indicator_tools.get_macd(timeframe=timeframe)
            )
            loop.close()
            
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
                f"MACD Analysis for {self.ticker} on {timeframe}:\n"
                f"  MACD Line: {macd:.4f}\n"
                f"  Signal Line: {signal:.4f}\n"
                f"  Histogram: {histogram:.4f}\n"
                f"  Signal: {signal_text}\n"
                f"\nInterpretation: {'Bullish momentum - consider long positions' if is_bullish_cross else 'Bearish momentum - consider short positions' if is_bearish_cross else 'No clear crossover signal'}"
            )
        except Exception as e:
            logger.error("macd_tool_failed", error=str(e))
            return f"Error calculating MACD: {str(e)}"


class SMACrossoverTool(BaseTool):
    """
    Calculate SMA (Simple Moving Average) crossover signals.
    
    Identifies trend changes when fast SMA crosses slow SMA.
    Common periods: 20/50, 50/200 (golden/death cross)
    """
    name: str = "sma_crossover"
    description: str = (
        "Detects fast/slow SMA crossovers (default 20/50) to identify trend changes and moving average levels. "
        "Call this for moving-average strategies, trend-following systems, golden cross / death cross setups, "
        "or any instruction mentioning SMA, EMA, or MA crossovers. "
        "Price above both SMAs with fast > slow = strong uptrend. "
        "Use the 50-period SMA as a dynamic support/resistance level for pullback entries in trend."
    )
    args_schema: Type[BaseModel] = SMAInput
    
    ticker: str = Field(description="Stock symbol")
    
    def _run(
        self,
        timeframe: str = "1h",
        fast_period: int = 20,
        slow_period: int = 50
    ) -> str:
        """Execute SMA crossover analysis."""
        try:
            import asyncio
            indicator_tools = IndicatorTools(ticker=self.ticker)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                indicator_tools.get_sma_crossover(
                    timeframe=timeframe,
                    fast_period=fast_period,
                    slow_period=slow_period
                )
            )
            loop.close()
            
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
            
            return (
                f"SMA Crossover Analysis for {self.ticker} on {timeframe}:\n"
                f"  Fast SMA ({fast_period}): ${fast_sma:.2f}\n"
                f"  Slow SMA ({slow_period}): ${slow_sma:.2f}\n"
                f"  Current Trend: {trend.upper()}\n"
                f"  Signal: {signal_text}\n"
                f"\nInterpretation: {trend.capitalize()} trend confirmed" if trend != "unknown" else "Sideways market"
            )
        except Exception as e:
            logger.error("sma_tool_failed", error=str(e))
            return f"Error calculating SMA crossover: {str(e)}"


class FVGDetectorTool(BaseTool):
    """
    Detect Fair Value Gaps (FVGs) - imbalances in price action.
    
    FVGs are gaps left by aggressive buying/selling that often get filled.
    Useful for ICT-style trading strategies.
    """
    name: str = "fvg_detector"
    description: str = (
        "Detects Fair Value Gaps (FVGs) — 3-candle price imbalances where institutional orders were filled rapidly. "
        "Use this for any ICT / Smart Money strategy referencing FVGs, imbalances, inefficiencies, or displacement candles. "
        "A bullish FVG below current price is a buy zone; a bearish FVG above is a sell zone. "
        "Unfilled FVGs with large gap sizes aligned with the trend are highest-probability entries. "
        "Also call this when the user mentions 'mitigation block', 'return to FVG', or 'order flow imbalance'."
    )
    args_schema: Type[BaseModel] = FVGInput
    
    ticker: str = Field(description="Stock symbol")
    candles: list = Field(description="Candle data")
    
    def _run(
        self,
        timeframe: str = "5m",
        lookback_candles: int = 50
    ) -> str:
        """Execute FVG detection."""
        try:
            detector = FVGDetector(ticker=self.ticker, candles=self.candles)
            result = detector.detect_fvgs(timeframe=timeframe, lookback_candles=lookback_candles)
            
            bullish_fvgs = [fvg for fvg in result.get("fvgs", []) if fvg["type"] == "bullish"]
            bearish_fvgs = [fvg for fvg in result.get("fvgs", []) if fvg["type"] == "bearish"]
            
            latest_bullish = bullish_fvgs[-1] if bullish_fvgs else None
            latest_bearish = bearish_fvgs[-1] if bearish_fvgs else None
            
            output = f"FVG Detection for {self.ticker} on {timeframe}:\n"
            output += f"  Total FVGs found: {len(result.get('fvgs', []))}\n"
            output += f"  Bullish FVGs: {len(bullish_fvgs)}\n"
            output += f"  Bearish FVGs: {len(bearish_fvgs)}\n\n"
            
            if latest_bullish:
                output += f"Latest Bullish FVG:\n"
                output += f"  Range: ${latest_bullish['low']:.2f} - ${latest_bullish['high']:.2f}\n"
                output += f"  Status: {'Filled' if latest_bullish['is_filled'] else 'Unfilled'}\n"
                output += f"  Gap Size: {latest_bullish['gap_size_pips']:.1f} pips\n\n"
            
            if latest_bearish:
                output += f"Latest Bearish FVG:\n"
                output += f"  Range: ${latest_bearish['low']:.2f} - ${latest_bearish['high']:.2f}\n"
                output += f"  Status: {'Filled' if latest_bearish['is_filled'] else 'Unfilled'}\n"
                output += f"  Gap Size: {latest_bearish['gap_size_pips']:.1f} pips\n\n"
            
            return output + "Interpretation: Unfilled FVGs are potential reversal zones."
            
        except Exception as e:
            logger.error("fvg_tool_failed", error=str(e))
            return f"Error detecting FVGs: {str(e)}"


class LiquidityAnalyzerTool(BaseTool):
    """Analyze liquidity pools and grabs for ICT trading."""
    name: str = "liquidity_analyzer"
    description: str = (
        "Identifies liquidity pools (clusters of stop-losses at swing highs/lows) and detects liquidity grabs "
        "(price sweeps through a pool then reverses sharply). "
        "Call this for ICT strategies involving stop hunts, equal highs/lows, inducement, or 'raid the liquidity'. "
        "After a confirmed grab, price typically displaces in the opposite direction — "
        "use the grab level as the invalidation point for stop placement. "
        "Also useful for strategies that target opposing liquidity as a take-profit."
    )
    args_schema: Type[BaseModel] = LiquidityInput
    
    ticker: str = Field(description="Stock symbol")
    candles: list = Field(description="Candle data")
    
    def _run(self, timeframe: str = "5m", lookback_candles: int = 100) -> str:
        """Execute liquidity analysis."""
        try:
            analyzer = LiquidityAnalyzer(ticker=self.ticker, candles=self.candles)
            result = analyzer.analyze_liquidity(timeframe=timeframe, lookback_candles=lookback_candles)
            
            pools = result.get("active_liquidity_pools", {})
            grabs = result.get("liquidity_grabs", [])
            
            output = f"Liquidity Analysis for {self.ticker} on {timeframe}:\n"
            output += f"  Buy-side liquidity levels (above price): {len(pools.get('above', []))}\n"
            output += f"  Sell-side liquidity levels (below price): {len(pools.get('below', []))}\n"
            output += f"  Recent liquidity grabs: {len(grabs)}\n\n"
            
            if grabs:
                latest_grab = grabs[-1]
                output += f"Latest Liquidity Grab:\n"
                output += f"  Type: {latest_grab['type']}\n"
                output += f"  Level: ${latest_grab['level']:.2f}\n"
                output += f"  Reversed: {latest_grab.get('reversed', False)}\n\n"
            
            return output + "Interpretation: Recent liquidity grabs with reversals signal institutional accumulation/distribution."
            
        except Exception as e:
            logger.error("liquidity_tool_failed", error=str(e))
            return f"Error analyzing liquidity: {str(e)}"


class MarketStructureTool(BaseTool):
    """Analyze market structure (BOS, CHoCH) for trend identification."""
    name: str = "market_structure_analyzer"
    description: str = (
        "Reads Break of Structure (BOS) and Change of Character (CHoCH) events to determine trend direction. "
        "Call this whenever the user's instructions reference market structure, trend direction, BOS, CHoCH, MSS, or SMC. "
        "A BOS confirms the existing trend continuing; a CHoCH signals a potential shift in direction. "
        "Use the trend output as a directional filter: only take longs in bullish structure, shorts in bearish. "
        "Pair with fvg_detector for complete high-confluence ICT setups."
    )
    args_schema: Type[BaseModel] = MarketStructureInput
    
    ticker: str = Field(description="Stock symbol")
    candles: list = Field(description="Candle data")
    
    def _run(self, timeframe: str = "1h", lookback_candles: int = 100) -> str:
        """Execute market structure analysis."""
        try:
            analyzer = MarketStructureAnalyzer(ticker=self.ticker, candles=self.candles)
            result = analyzer.analyze_structure(timeframe=timeframe, lookback_candles=lookback_candles)
            
            trend = result.get("trend", "ranging")
            events = result.get("structure_events", [])
            
            output = f"Market Structure for {self.ticker} on {timeframe}:\n"
            output += f"  Current Trend: {trend.upper()}\n"
            output += f"  Structure Events: {len(events)}\n\n"
            
            if events:
                latest = events[-1]
                output += f"Latest Event:\n"
                output += f"  Type: {latest['type']} ({latest['direction']})\n"
                output += f"  Level: ${latest['level']:.2f}\n\n"
            
            return output + f"Interpretation: {trend.capitalize()} market structure confirmed."
            
        except Exception as e:
            logger.error("structure_tool_failed", error=str(e))
            return f"Error analyzing structure: {str(e)}"


class PremiumDiscountTool(BaseTool):
    """Identify premium/discount zones for optimal entry timing."""
    name: str = "premium_discount_analyzer"
    description: str = (
        "Divides the current price range into premium (above 50% — expensive, favour sells), "
        "equilibrium (40–60%), and discount (below 50% — cheap, favour buys) zones. "
        "Also calculates Fibonacci OTE levels (62–79% retracement) for optimal entries. "
        "Call this for any ICT strategy referencing PD arrays, OTE, 'buy in discount / sell in premium', "
        "or golden pocket entries. "
        "Entering a BUY in the discount zone adds confluence; entering a BUY in premium is low-probability."
    )
    args_schema: Type[BaseModel] = PremiumDiscountInput
    
    ticker: str = Field(description="Stock symbol")
    candles: list = Field(description="Candle data")
    
    def _run(self, timeframe: str = "4h", lookback_candles: int = 50) -> str:
        """Execute premium/discount analysis."""
        try:
            analyzer = PremiumDiscountAnalyzer(ticker=self.ticker, candles=self.candles)
            result = analyzer.analyze_zones(timeframe=timeframe, lookback_candles=lookback_candles)
            
            zone = result.get("zone", "equilibrium")
            price_level = result.get("price_level_percent", 50)
            
            output = f"Premium/Discount Analysis for {self.ticker} on {timeframe}:\n"
            output += f"  Current Zone: {zone.upper()}\n"
            output += f"  Price Level: {price_level:.0f}% of range\n\n"
            
            if zone == "discount":
                output += "Interpretation: Price in DISCOUNT zone (0-30%) - favorable for LONG entries"
            elif zone == "premium":
                output += "Interpretation: Price in PREMIUM zone (70-100%) - favorable for SHORT entries"
            else:
                output += "Interpretation: Price in EQUILIBRIUM zone (40-60%) - wait for better price"
            
            return output
            
        except Exception as e:
            logger.error("premium_discount_tool_failed", error=str(e))
            return f"Error analyzing zones: {str(e)}"


# ============================================================================
# TOOL REGISTRY - All available tools for agents
# ============================================================================

def get_available_tools(ticker: str, candles: list = None) -> list:
    """
    Get all available tools for LLM agents.

    Args:
        ticker: Stock symbol
        candles: Optional candle data (required for some tools)

    Returns:
        List of CrewAI BaseTool instances
    """
    tools = [
        RSITool(ticker=ticker),
        MACDTool(ticker=ticker),
        SMACrossoverTool(ticker=ticker),
    ]

    # Tools that require candle data
    if candles:
        tools.extend([
            FVGDetectorTool(ticker=ticker, candles=candles),
            LiquidityAnalyzerTool(ticker=ticker, candles=candles),
            MarketStructureTool(ticker=ticker, candles=candles),
            PremiumDiscountTool(ticker=ticker, candles=candles),
        ])

    return tools


# Map from tool name strings (used in AgentMetadata.default_tools) to CrewAI tool classes
_CREWAI_TOOL_MAP = {
    "fvg_detector": FVGDetectorTool,
    "liquidity_analyzer": LiquidityAnalyzerTool,
    "market_structure_analyzer": MarketStructureTool,
    "premium_discount_analyzer": PremiumDiscountTool,
    "rsi_calculator": RSITool,
    "macd_calculator": MACDTool,
    "sma_crossover": SMACrossoverTool,
}

# Tools that require candle data to instantiate
_CANDLE_TOOLS = {"fvg_detector", "liquidity_analyzer", "market_structure_analyzer", "premium_discount_analyzer"}


def load_tools_for_agent(tool_names: list, ticker: str, candles: list = None) -> list:
    """
    Load CrewAI tool instances for the given tool names.

    Only loads candle-dependent tools (FVG, liquidity, market structure, premium/discount)
    when candle data is provided, so callers that don't have candles still get their
    indicator tools (RSI, MACD, SMA) without error.

    Args:
        tool_names: List of tool name strings from AgentMetadata.default_tools
        ticker: Stock symbol
        candles: Optional candle data (required for ICT/SMC tools)

    Returns:
        List of instantiated CrewAI BaseTool instances
    """
    tools = []
    for name in tool_names:
        cls = _CREWAI_TOOL_MAP.get(name)
        if not cls:
            continue
        if name in _CANDLE_TOOLS:
            if not candles:
                continue  # skip candle-dependent tools when no candle data available
            tools.append(cls(ticker=ticker, candles=candles))
        else:
            tools.append(cls(ticker=ticker))
    return tools

