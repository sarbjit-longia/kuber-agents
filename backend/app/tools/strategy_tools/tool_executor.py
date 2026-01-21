"""
Tool Executor - Dynamically executes strategy tools based on LLM detection

This executor takes the auto-detected tools from the frontend and executes them,
returning structured data that the LLM can use for strategy decisions.
"""
import structlog
from typing import List, Dict, Any, Optional
import httpx

from app.tools.strategy_tools.fvg_detector import FVGDetector
from app.tools.strategy_tools.liquidity_analyzer import LiquidityAnalyzer
from app.tools.strategy_tools.market_structure import MarketStructureAnalyzer
from app.tools.strategy_tools.premium_discount import PremiumDiscountAnalyzer
from app.tools.strategy_tools.indicator_tools import IndicatorTools
from app.config import settings

logger = structlog.get_logger()


class StrategyToolExecutor:
    """Executes strategy tools and aggregates results."""
    
    def __init__(self, ticker: str):
        """
        Initialize Tool Executor.
        
        Args:
            ticker: Stock symbol being analyzed
        """
        self.ticker = ticker
        self.data_plane_url = getattr(settings, "DATA_PLANE_URL", "http://data-plane:8000")
        self.indicator_tools = IndicatorTools(ticker)
    
    async def execute_tools(
        self,
        detected_tools: List[Dict[str, Any]],
        candles_cache: Optional[Dict[str, List[Dict]]] = None
    ) -> Dict[str, Any]:
        """
        Execute all detected tools and return aggregated results.
        
        Args:
            detected_tools: List of tools detected by LLM
                            [{"tool": "fvg_detector", "params": {...}, "cost": 0.01}]
            candles_cache: Optional pre-fetched candles to avoid repeated API calls
        
        Returns:
            {
                "tool_name": {result},
                ...
            }
        """
        results = {}
        
        for tool_spec in detected_tools:
            tool_name = tool_spec["tool"]
            params = tool_spec["params"]
            
            try:
                # Fetch candles if needed
                timeframe = params.get("timeframe", "1h")
                if candles_cache and timeframe in candles_cache:
                    candles = candles_cache[timeframe]
                else:
                    candles = await self._fetch_candles(timeframe)
                
                # Execute the tool
                if tool_name == "fvg_detector":
                    result = await self._execute_fvg_detector(params, candles)
                elif tool_name == "liquidity_analyzer":
                    result = await self._execute_liquidity_analyzer(params, candles)
                elif tool_name == "market_structure":
                    result = await self._execute_market_structure(params, candles)
                elif tool_name == "premium_discount":
                    result = await self._execute_premium_discount(params, candles)
                elif tool_name == "rsi":
                    result = await self.indicator_tools.get_rsi(**params)
                elif tool_name == "sma_crossover":
                    result = await self.indicator_tools.get_sma_crossover(**params)
                elif tool_name == "macd":
                    result = await self.indicator_tools.get_macd(**params)
                elif tool_name == "bollinger_bands":
                    result = await self.indicator_tools.get_bollinger_bands(**params)
                else:
                    logger.warning("unknown_tool", tool=tool_name)
                    result = {"error": f"Unknown tool: {tool_name}"}
                
                results[tool_name] = result
                
                logger.info(
                    "tool_executed",
                    tool=tool_name,
                    ticker=self.ticker,
                    timeframe=params.get("timeframe")
                )
                
            except Exception as e:
                logger.error(
                    "tool_execution_failed",
                    tool=tool_name,
                    error=str(e),
                    exc_info=True
                )
                results[tool_name] = {"error": str(e)}
        
        return results
    
    async def _fetch_candles(self, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
        """
        Fetch candles from Data Plane.
        
        Args:
            timeframe: Timeframe (5m, 15m, 1h, 4h, D)
            limit: Number of candles to fetch
        
        Returns:
            List of OHLC candles
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.data_plane_url}/api/v1/data/candles/{self.ticker}",
                    params={"resolution": timeframe, "limit": limit}
                )
                response.raise_for_status()
                data = response.json()
            
            candles = data.get("candles", [])
            
            logger.debug(
                "candles_fetched",
                ticker=self.ticker,
                timeframe=timeframe,
                count=len(candles)
            )
            
            return candles
            
        except Exception as e:
            logger.error(
                "candle_fetch_failed",
                ticker=self.ticker,
                timeframe=timeframe,
                error=str(e)
            )
            return []
    
    async def _execute_fvg_detector(
        self,
        params: Dict[str, Any],
        candles: List[Dict]
    ) -> Dict[str, Any]:
        """Execute FVG Detector tool."""
        detector = FVGDetector(
            timeframe=params.get("timeframe", "1h"),
            min_gap_pips=params.get("min_gap_pips", 10),
            lookback_periods=params.get("lookback_periods", 100)
        )
        return await detector.detect(candles)
    
    async def _execute_liquidity_analyzer(
        self,
        params: Dict[str, Any],
        candles: List[Dict]
    ) -> Dict[str, Any]:
        """Execute Liquidity Analyzer tool."""
        analyzer = LiquidityAnalyzer(
            timeframe=params.get("timeframe", "1h"),
            swing_strength=params.get("swing_strength", 5),
            grab_threshold_pips=params.get("grab_threshold_pips", 10),
            lookback_periods=params.get("lookback_periods", 100)
        )
        return await analyzer.analyze(candles)
    
    async def _execute_market_structure(
        self,
        params: Dict[str, Any],
        candles: List[Dict]
    ) -> Dict[str, Any]:
        """Execute Market Structure Analyzer tool."""
        analyzer = MarketStructureAnalyzer(
            timeframe=params.get("timeframe", "1h"),
            swing_strength=params.get("swing_strength", 5),
            lookback_periods=params.get("lookback_periods", 100)
        )
        return await analyzer.analyze(candles)
    
    async def _execute_premium_discount(
        self,
        params: Dict[str, Any],
        candles: List[Dict]
    ) -> Dict[str, Any]:
        """Execute Premium/Discount Analyzer tool."""
        analyzer = PremiumDiscountAnalyzer(
            timeframe=params.get("timeframe", "D"),
            lookback_periods=params.get("lookback_periods", 50)
        )
        return await analyzer.analyze(candles)

