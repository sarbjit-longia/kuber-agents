"""
Indicator Tools - Wrappers for Data Plane indicators

These tools fetch pre-computed indicators from the Data Plane service
and format them for LLM consumption.
"""
import asyncio
import structlog
import httpx
from typing import List, Dict, Any, Optional, Tuple
from app.config import settings


async def _gather(*coros):
    """Run coroutines concurrently and return results in order."""
    return await asyncio.gather(*coros)

logger = structlog.get_logger()


class IndicatorTools:
    """Wrapper for Data Plane indicators."""
    
    def __init__(self, ticker: str):
        """
        Initialize Indicator Tools.
        
        Args:
            ticker: Stock symbol to fetch indicators for
        """
        self.ticker = ticker
        self.data_plane_url = getattr(settings, "DATA_PLANE_URL", "http://data-plane:8000")
    
    async def get_rsi(
        self,
        timeframe: str = "1h",
        period: int = 14,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get RSI (Relative Strength Index) values.
        
        Args:
            timeframe: Timeframe (5m, 15m, 1h, 4h, D)
            period: RSI period (default: 14)
            limit: Number of values to return
        
        Returns:
            {
                "current_rsi": float,
                "previous_rsi": float,
                "is_oversold": bool,  # RSI < 30
                "is_overbought": bool,  # RSI > 70
                "values": [...]
            }
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.data_plane_url}/api/v1/data/indicators/{self.ticker}",
                    params={
                        "timeframe": timeframe,
                        "indicators": "rsi",
                        "limit": limit
                    }
                )
                response.raise_for_status()
                data = response.json()
            
            rsi_values = data.get("indicators", {}).get("rsi", [])
            
            # Filter out None values (RSI needs warmup period)
            rsi_values = [v for v in rsi_values if v is not None]
            
            if not rsi_values:
                return self._empty_rsi_result()
            
            current_rsi = rsi_values[-1]
            previous_rsi = rsi_values[-2] if len(rsi_values) > 1 else current_rsi

            is_bullish_div, is_bearish_div = self._detect_rsi_divergence(rsi_values)

            return {
                "current_rsi": round(current_rsi, 2),
                "previous_rsi": round(previous_rsi, 2),
                "is_oversold": current_rsi < 30,
                "is_overbought": current_rsi > 70,
                "is_bullish_divergence": is_bullish_div,
                "is_bearish_divergence": is_bearish_div,
                "values": [round(v, 2) for v in rsi_values],
                "timeframe": timeframe
            }
            
        except Exception as e:
            logger.error("rsi_fetch_failed", ticker=self.ticker, error=str(e))
            return self._empty_rsi_result()
    
    async def get_sma_crossover(
        self,
        timeframe: str = "1h",
        fast_period: int = 20,
        slow_period: int = 50,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get SMA (Simple Moving Average) crossover analysis.
        
        Args:
            timeframe: Timeframe
            fast_period: Fast SMA period
            slow_period: Slow SMA period
            limit: Number of values
        
        Returns:
            {
                "current_fast_sma": float,
                "current_slow_sma": float,
                "is_golden_cross": bool,  # Fast crossed above slow
                "is_death_cross": bool,   # Fast crossed below slow
                "trend": "bullish" | "bearish" | "neutral"
            }
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                fast_resp, slow_resp = await _gather(
                    client.get(
                        f"{self.data_plane_url}/api/v1/data/indicators/{self.ticker}",
                        params={"timeframe": timeframe, "indicators": "sma",
                                "sma_period": fast_period, "limit": limit + 1},
                    ),
                    client.get(
                        f"{self.data_plane_url}/api/v1/data/indicators/{self.ticker}",
                        params={"timeframe": timeframe, "indicators": "sma",
                                "sma_period": slow_period, "limit": limit + 1},
                    ),
                )
                fast_resp.raise_for_status()
                slow_resp.raise_for_status()

            fast_vals = [v for v in fast_resp.json().get("indicators", {}).get("sma", []) if v is not None]
            slow_vals = [v for v in slow_resp.json().get("indicators", {}).get("sma", []) if v is not None]

            if len(fast_vals) < 2 or len(slow_vals) < 2:
                return self._empty_sma_result()

            cur_fast, cur_slow = fast_vals[-1], slow_vals[-1]
            prev_fast, prev_slow = fast_vals[-2], slow_vals[-2]

            is_golden = prev_fast <= prev_slow and cur_fast > cur_slow
            is_death  = prev_fast >= prev_slow and cur_fast < cur_slow

            if cur_fast > cur_slow:
                trend = "bullish"
            elif cur_fast < cur_slow:
                trend = "bearish"
            else:
                trend = "neutral"

            return {
                "current_fast_sma": round(cur_fast, 4),
                "current_slow_sma": round(cur_slow, 4),
                "is_golden_cross": is_golden,
                "is_death_cross": is_death,
                "trend": trend,
                "fast_period": fast_period,
                "slow_period": slow_period,
                "timeframe": timeframe,
            }

        except Exception as e:
            logger.error("sma_fetch_failed", ticker=self.ticker, error=str(e))
            return self._empty_sma_result()
    
    async def get_macd(
        self,
        timeframe: str = "1h",
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get MACD (Moving Average Convergence Divergence) values.
        
        Returns:
            {
                "current_macd": float,
                "current_signal": float,
                "current_histogram": float,
                "is_bullish": bool,  # MACD above signal
                "is_bearish": bool,  # MACD below signal
                "is_bullish_crossover": bool,
                "is_bearish_crossover": bool
            }
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.data_plane_url}/api/v1/data/indicators/{self.ticker}",
                    params={
                        "timeframe": timeframe,
                        "indicators": "macd",
                        "limit": limit
                    }
                )
                response.raise_for_status()
                data = response.json()
            
            macd_data = data.get("indicators", {}).get("macd", {})
            
            if not macd_data:
                return self._empty_macd_result()
            
            # Finnhub returns MACD as {macd: [...], macd_signal: [...], macd_hist: [...]}
            macd_values = macd_data.get("macd", [])
            signal_values = macd_data.get("macd_signal", [])
            hist_values = macd_data.get("macd_hist", [])
            
            # Filter out None values (MACD needs warmup period)
            macd_values = [v for v in macd_values if v is not None]
            signal_values = [v for v in signal_values if v is not None]
            hist_values = [v for v in hist_values if v is not None]
            
            if not all([macd_values, signal_values, hist_values]):
                return self._empty_macd_result()
            
            current_macd = macd_values[-1]
            current_signal = signal_values[-1]
            current_histogram = hist_values[-1]
            
            prev_macd = macd_values[-2] if len(macd_values) > 1 else current_macd
            prev_signal = signal_values[-2] if len(signal_values) > 1 else current_signal
            
            is_bullish_crossover = prev_macd <= prev_signal and current_macd > current_signal
            is_bearish_crossover = prev_macd >= prev_signal and current_macd < current_signal
            
            return {
                "current_macd": round(current_macd, 5),
                "current_signal": round(current_signal, 5),
                "current_histogram": round(current_histogram, 5),
                "is_bullish": current_macd > current_signal,
                "is_bearish": current_macd < current_signal,
                "is_bullish_crossover": is_bullish_crossover,
                "is_bearish_crossover": is_bearish_crossover,
                "timeframe": timeframe
            }
            
        except Exception as e:
            logger.error("macd_fetch_failed", ticker=self.ticker, error=str(e))
            return self._empty_macd_result()
    
    async def get_bollinger_bands(
        self,
        timeframe: str = "1h",
        period: int = 20,
        std_dev: float = 2.0,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get Bollinger Bands values.
        
        Returns:
            {
                "upper_band": float,
                "middle_band": float,
                "lower_band": float,
                "current_price": float,
                "price_position": "above_upper" | "in_bands" | "below_lower",
                "bandwidth_percent": float
            }
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.data_plane_url}/api/v1/data/indicators/{self.ticker}",
                    params={
                        "timeframe": timeframe,
                        "indicators": "bbands",
                        "limit": limit
                    }
                )
                response.raise_for_status()
                data = response.json()
            
            bbands_data = data.get("indicators", {}).get("bbands", {})
            
            if not bbands_data:
                return self._empty_bbands_result()
            
            upper_values = bbands_data.get("upper", [])
            middle_values = bbands_data.get("middle", [])
            lower_values = bbands_data.get("lower", [])
            
            # Filter out None values (Bollinger Bands need warmup period)
            upper_values = [v for v in upper_values if v is not None]
            middle_values = [v for v in middle_values if v is not None]
            lower_values = [v for v in lower_values if v is not None]
            
            if not all([upper_values, middle_values, lower_values]):
                return self._empty_bbands_result()
            
            upper = upper_values[-1]
            middle = middle_values[-1]
            lower = lower_values[-1]
            
            # Get current price from candles (would need to be passed in)
            current_price = middle  # Placeholder
            
            if current_price > upper:
                position = "above_upper"
            elif current_price < lower:
                position = "below_lower"
            else:
                position = "in_bands"
            
            bandwidth = ((upper - lower) / middle) * 100 if middle > 0 else 0
            
            return {
                "upper_band": round(upper, 5),
                "middle_band": round(middle, 5),
                "lower_band": round(lower, 5),
                "current_price": round(current_price, 5),
                "price_position": position,
                "bandwidth_percent": round(bandwidth, 2),
                "is_squeeze": bandwidth < 10,  # Narrow bands
                "timeframe": timeframe
            }
            
        except Exception as e:
            logger.error("bbands_fetch_failed", ticker=self.ticker, error=str(e))
            return self._empty_bbands_result()
    
    def _detect_rsi_divergence(self, rsi_values: List[float]) -> Tuple[bool, bool]:
        """
        Detect basic RSI divergence using the last two swing points.

        Bullish divergence: price makes lower low, RSI makes higher low.
        Bearish divergence: price makes higher high, RSI makes lower high.

        We approximate price direction from the RSI series itself (both
        reflect price momentum) — a proper implementation would compare
        against the candle close series. Returns (is_bullish, is_bearish).
        """
        if len(rsi_values) < 4:
            return False, False

        # Split into two halves and compare trough/peak RSI values
        mid = len(rsi_values) // 2
        first_half = rsi_values[:mid]
        second_half = rsi_values[mid:]

        first_min = min(first_half)
        second_min = min(second_half)
        first_max = max(first_half)
        second_max = max(second_half)

        # Bullish divergence: RSI trough rising while price trough falling
        # We use RSI trough as proxy — if the latest trough is higher while
        # RSI is still in oversold territory, flag it.
        is_bullish = (
            second_min > first_min
            and second_half[-1] < 40
        )

        # Bearish divergence: RSI peak falling while in overbought territory
        is_bearish = (
            second_max < first_max
            and second_half[-1] > 60
        )

        return is_bullish, is_bearish

    def _empty_rsi_result(self) -> Dict[str, Any]:
        return {
            "current_rsi": 50.0,
            "previous_rsi": 50.0,
            "is_oversold": False,
            "is_overbought": False,
            "is_bullish_divergence": False,
            "is_bearish_divergence": False,
            "values": [],
            "timeframe": "unknown"
        }
    
    def _empty_sma_result(self) -> Dict[str, Any]:
        return {
            "current_fast_sma": 0.0,
            "current_slow_sma": 0.0,
            "is_golden_cross": False,
            "is_death_cross": False,
            "trend": "neutral",
            "fast_period": 20,
            "slow_period": 50,
            "timeframe": "unknown",
        }
    
    def _empty_macd_result(self) -> Dict[str, Any]:
        return {
            "current_macd": 0.0,
            "current_signal": 0.0,
            "current_histogram": 0.0,
            "is_bullish": False,
            "is_bearish": False,
            "is_bullish_crossover": False,
            "is_bearish_crossover": False,
            "timeframe": "unknown"
        }
    
    def _empty_bbands_result(self) -> Dict[str, Any]:
        return {
            "upper_band": 0.0,
            "middle_band": 0.0,
            "lower_band": 0.0,
            "current_price": 0.0,
            "price_position": "in_bands",
            "bandwidth_percent": 0.0,
            "is_squeeze": False,
            "timeframe": "unknown"
        }

