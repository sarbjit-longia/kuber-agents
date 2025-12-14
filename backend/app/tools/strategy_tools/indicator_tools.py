"""
Indicator Tools - Wrappers for Data Plane indicators

These tools fetch pre-computed indicators from the Data Plane service
and format them for LLM consumption.
"""
import structlog
import httpx
from typing import List, Dict, Any, Optional
from app.config import settings

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
        self.data_plane_url = getattr(settings, "DATA_PLANE_URL", "http://data-plane:8001")
    
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
            
            if not rsi_values:
                return self._empty_rsi_result()
            
            current_rsi = rsi_values[-1]
            previous_rsi = rsi_values[-2] if len(rsi_values) > 1 else current_rsi
            
            return {
                "current_rsi": round(current_rsi, 2),
                "previous_rsi": round(previous_rsi, 2),
                "is_oversold": current_rsi < 30,
                "is_overbought": current_rsi > 70,
                "is_bullish_divergence": False,  # TODO: Implement divergence detection
                "is_bearish_divergence": False,
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
                response = await client.get(
                    f"{self.data_plane_url}/api/v1/data/indicators/{self.ticker}",
                    params={
                        "timeframe": timeframe,
                        "indicators": "sma",
                        "limit": limit
                    }
                )
                response.raise_for_status()
                data = response.json()
            
            # Note: Data Plane would need to support multiple SMA periods
            # For now, we'll use a simplified version
            sma_values = data.get("indicators", {}).get("sma", [])
            
            if len(sma_values) < 2:
                return self._empty_sma_result()
            
            # Simplified: assume data plane returns fast and slow SMA
            # In reality, we'd need to fetch both separately or extend the API
            
            return {
                "current_fast_sma": 0.0,  # TODO: Fetch from Data Plane
                "current_slow_sma": 0.0,
                "is_golden_cross": False,
                "is_death_cross": False,
                "trend": "neutral",
                "timeframe": timeframe
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
            "timeframe": "unknown"
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

