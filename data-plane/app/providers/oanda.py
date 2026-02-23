"""
OANDA Market Data Provider

Provides forex market data via OANDA REST API.

Practice Account (Development):
- FREE - No rate limits
- Endpoint: https://api-fxpractice.oanda.com

Live Account (Production):
- FREE data with funded account
- Endpoint: https://api-fxtrade.oanda.com

Documentation: https://developer.oanda.com/rest-live-v20/introduction/
"""
import httpx
from typing import List, Dict
from datetime import datetime
import structlog
import time

from .base import BaseProvider, ProviderType, AssetClass


logger = structlog.get_logger()


class OANDAProvider(BaseProvider):
    """
    OANDA forex data provider.
    
    Features:
    - Real-time forex quotes (bid/ask/spread)
    - Historical candles (all timeframes)
    - 70+ currency pairs
    - No rate limits (fair use)
    """
    
    def __init__(
        self, 
        api_key: str,
        account_type: str = "practice",
        **kwargs
    ):
        """
        Initialize OANDA provider.
        
        Args:
            api_key: OANDA API token (Personal Access Token)
            account_type: "practice" or "live"
        """
        super().__init__(api_key, **kwargs)
        
        self.account_type = account_type
        self.base_url = {
            "practice": "https://api-fxpractice.oanda.com",
            "live": "https://api-fxtrade.oanda.com"
        }[account_type]
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        logger.info(
            "oanda_provider_initialized",
            account_type=account_type,
            base_url=self.base_url
        )
    
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OANDA
    
    @property
    def supported_asset_classes(self) -> List[AssetClass]:
        return [AssetClass.FOREX]
    
    async def get_quote(
        self, 
        symbol: str, 
        asset_class: AssetClass = AssetClass.FOREX
    ) -> Dict:
        """
        Get real-time forex quote from OANDA.
        
        Example response:
        {
            "prices": [{
                "instrument": "EUR_USD",
                "time": "2024-01-15T12:34:56.000000Z",
                "bids": [{"price": "1.08234"}],
                "asks": [{"price": "1.08245"}]
            }]
        }
        """
        if asset_class != AssetClass.FOREX:
            raise ValueError(f"OANDA only supports forex, not {asset_class}")
        
        normalized_symbol = self.normalize_symbol(symbol, asset_class)
        
        url = f"{self.base_url}/v3/accounts/{await self._get_account_id()}/pricing"
        params = {"instruments": normalized_symbol}
        
        start_time = time.time()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self.headers,
                    timeout=10.0
                )
                duration = time.time() - start_time
                
                response.raise_for_status()
                data = response.json()
                
                # Track successful API call (OANDA has no rate limits)
                self._track_api_call("quote", duration, "success", len(response.content))
                
                if not data.get("prices"):
                    raise ValueError(f"No price data for {symbol}")
                
                price_data = data["prices"][0]
                
                # Extract bid/ask
                bid = float(price_data["bids"][0]["price"]) if price_data.get("bids") else 0.0
                ask = float(price_data["asks"][0]["price"]) if price_data.get("asks") else 0.0
                current_price = (bid + ask) / 2 if bid and ask else 0.0
                
                return {
                    "symbol": symbol,
                    "current_price": current_price,
                    "bid": bid,
                    "ask": ask,
                    "spread": ask - bid if bid and ask else 0.0,
                    "high": current_price,  # OANDA quotes don't include daily high/low
                    "low": current_price,
                    "open": current_price,
                    "previous_close": current_price,
                    "volume": 0,  # Forex doesn't have traditional volume
                    "timestamp": datetime.fromisoformat(price_data["time"].replace("Z", "+00:00"))
                }
        
        except httpx.HTTPStatusError as e:
            duration = time.time() - start_time
            self._track_api_call("quote", duration, "error")
            logger.error(
                "oanda_quote_http_error",
                symbol=symbol,
                status_code=e.response.status_code,
                error=str(e)
            )
            raise
        except Exception as e:
            duration = time.time() - start_time
            self._track_api_call("quote", duration, "error")
            logger.error(
                "oanda_quote_error",
                symbol=symbol,
                error=str(e),
                exc_info=True
            )
            raise
    
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
        asset_class: AssetClass = AssetClass.FOREX
    ) -> List[Dict]:
        """
        Get historical candle data from OANDA.
        
        Example response:
        {
            "candles": [{
                "time": "2024-01-15T12:00:00.000000Z",
                "mid": {"o": "1.08234", "h": "1.08456", "l": "1.08123", "c": "1.08345"},
                "volume": 1234
            }]
        }
        """
        if asset_class != AssetClass.FOREX:
            raise ValueError(f"OANDA only supports forex, not {asset_class}")
        
        normalized_symbol = self.normalize_symbol(symbol, asset_class)
        normalized_timeframe = self.normalize_timeframe(timeframe)
        
        url = f"{self.base_url}/v3/instruments/{normalized_symbol}/candles"
        params = {
            "granularity": normalized_timeframe,
            "count": min(count, 5000)  # OANDA max is 5000
        }
        
        start_time = time.time()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self.headers,
                    timeout=15.0
                )
                duration = time.time() - start_time
                
                response.raise_for_status()
                data = response.json()
                
                # Track successful API call
                self._track_api_call("candles", duration, "success", len(response.content))
                
                candles = []
                for candle in data.get("candles", []):
                    if not candle.get("complete"):
                        continue  # Skip incomplete candles
                    
                    mid = candle["mid"]
                    candles.append({
                        "time": candle["time"],
                        "open": float(mid["o"]),
                        "high": float(mid["h"]),
                        "low": float(mid["l"]),
                        "close": float(mid["c"]),
                        "volume": candle.get("volume", 0)
                    })
                
                logger.info(
                    "oanda_candles_fetched",
                    symbol=symbol,
                    timeframe=timeframe,
                    count=len(candles)
                )
                
                return candles
        
        except httpx.HTTPStatusError as e:
            duration = time.time() - start_time
            self._track_api_call("candles", duration, "error")
            logger.error(
                "oanda_candles_http_error",
                symbol=symbol,
                status_code=e.response.status_code,
                error=str(e)
            )
            raise
        except Exception as e:
            duration = time.time() - start_time
            self._track_api_call("candles", duration, "error")
            logger.error(
                "oanda_candles_error",
                symbol=symbol,
                error=str(e),
                exc_info=True
            )
            raise
    
    def normalize_symbol(self, symbol: str, asset_class: AssetClass) -> str:
        """
        Normalize symbol to OANDA format.
        
        Input formats:
        - "EUR/USD" → "EUR_USD"
        - "EURUSD" → "EUR_USD"
        - "EUR_USD" → "EUR_USD" (already normalized)
        
        Args:
            symbol: User-provided symbol
            asset_class: Asset class (must be FOREX)
        
        Returns:
            OANDA format: "EUR_USD"
        """
        if asset_class != AssetClass.FOREX:
            return symbol
        
        # Remove slashes
        symbol = symbol.replace("/", "_")
        
        # Handle 6-character format (EURUSD → EUR_USD)
        if len(symbol) == 6 and "_" not in symbol:
            symbol = f"{symbol[:3]}_{symbol[3:]}"
        
        # Uppercase
        return symbol.upper()
    
    def normalize_timeframe(self, timeframe: str) -> str:
        """
        Normalize timeframe to OANDA granularity format.
        
        Supports both string and numeric (minute-based) formats:
        - String: "1m", "5m", "1h", "D" → "M1", "M5", "H1", "D"
        - Numeric: "1", "5", "60", "240" → "M1", "M5", "H1", "H4"
        
        Args:
            timeframe: Standard format (string like "1h" or numeric like "60")
        
        Returns:
            OANDA granularity (e.g., "M5", "H1", "D")
        """
        # String-based mapping (preferred)
        mapping = {
            "1m": "M1",
            "5m": "M5",
            "15m": "M15",
            "30m": "M30",
            "1h": "H1",
            "2h": "H2",
            "4h": "H4",
            "8h": "H8",
            "D": "D",
            "W": "W",
            "M": "M"
        }
        
        # Check string mapping first
        if timeframe in mapping:
            return mapping[timeframe]
        
        # Handle numeric format (minutes as string: "1", "5", "60", "240")
        try:
            minutes = int(timeframe)
            if minutes == 1:
                return "M1"
            elif minutes == 5:
                return "M5"
            elif minutes == 15:
                return "M15"
            elif minutes == 30:
                return "M30"
            elif minutes == 60:
                return "H1"
            elif minutes == 120:
                return "H2"
            elif minutes == 240:
                return "H4"
            elif minutes == 480:
                return "H8"
            elif minutes == 1440:
                return "D"
        except ValueError:
            pass  # Not a numeric timeframe
        
        # Default: return as-is
        return timeframe
    
    async def _get_account_id(self) -> str:
        """
        Get OANDA account ID for pricing requests.
        
        Cached after first fetch.
        """
        if hasattr(self, "_account_id"):
            return self._account_id
        
        url = f"{self.base_url}/v3/accounts"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=self.headers,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                if not data.get("accounts"):
                    raise ValueError("No OANDA accounts found")
                
                self._account_id = data["accounts"][0]["id"]
                logger.info("oanda_account_id_fetched", account_id=self._account_id)
                
                return self._account_id
        
        except Exception as e:
            logger.error("oanda_account_id_fetch_error", error=str(e))
            # Fallback: Try using "primary" as account ID
            self._account_id = "primary"
            return self._account_id
