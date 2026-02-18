"""
Oanda Broker Service

Implementation using Oanda v3 REST API for forex trading.
Based on tested oanda_service.py from project root.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import requests

from app.services.brokers.base import (
    BrokerService, Position, Order, OrderSide, OrderType, TimeInForce, OrderStatus
)


class OandaBrokerService(BrokerService):
    """
    Oanda broker service using v3 REST API.
    
    Supports forex and CFD trading.
    """
    
    def __init__(self, api_key: str, secret_key: str = None, account_id: str = None, paper: bool = True):
        super().__init__(api_key, secret_key, account_id, paper)
        
        # Oanda doesn't use secret_key, just api_token
        self.api_token = api_key
        
        # Set base URLs
        if paper:
            self.base_url = "https://api-fxpractice.oanda.com/v3"
            self.stream_url = "https://stream-fxpractice.oanda.com/v3"
        else:
            self.base_url = "https://api-fxtrade.oanda.com/v3"
            self.stream_url = "https://stream-fxtrade.oanda.com/v3"
        
        # Setup session
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept-Datetime-Format': 'UNIX'
        })
        
        # Auto-detect account ID if not provided
        if not self.account_id:
            try:
                accounts = self._make_request("GET", "/accounts")
                if accounts and "accounts" in accounts:
                    self.account_id = accounts["accounts"][0]["id"]
            except:
                pass
        
        self.logger.info("Oanda broker initialized", account_id=self.account_id, paper=paper)

        # Prevent Celery tasks from hanging indefinitely on broker I/O
        # (connect_timeout, read_timeout) in seconds
        self._http_timeout = (5, 20)
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> Dict[str, Any]:
        """Make HTTP request to Oanda API"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params, timeout=self._http_timeout)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, params=params, timeout=self._http_timeout)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data, params=params, timeout=self._http_timeout)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, params=params, timeout=self._http_timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            
            if response.content:
                return response.json()
            else:
                return {"success": True}
                
        except requests.exceptions.HTTPError as e:
            error_msg = f"Oanda API HTTP error: {e.response.status_code}"
            if e.response.content:
                try:
                    error_detail = e.response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - {e.response.text}"
            
            self.logger.error(error_msg)
            return {"error": error_msg}
        except requests.exceptions.Timeout as e:
            error_msg = f"Oanda API timeout: {str(e)}"
            self.logger.error(error_msg)
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Oanda API request failed: {str(e)}"
            self.logger.error(error_msg)
            return {"error": error_msg}
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to Oanda API"""
        try:
            accounts = self._make_request("GET", "/accounts")
            if "error" in accounts:
                return {"status": "error", "error": accounts["error"]}
            
            return {
                "status": "connected",
                "message": "Oanda API connection successful",
                "accounts_count": len(accounts.get("accounts", [])),
                "paper_trading": self.paper
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_account_info(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Get Oanda account information"""
        target_account = account_id or self.account_id
        if not target_account:
            return {"error": "No account ID provided"}
        
        try:
            result = self._make_request("GET", f"/accounts/{target_account}")
            if "error" in result:
                return result
            
            account = result.get("account", {})
            
            return {
                "account_id": account.get("id"),
                "currency": account.get("currency"),
                "balance": float(account.get("balance", 0)),
                "cash": float(account.get("balance", 0)),
                "unrealized_pl": float(account.get("unrealizedPL", 0)),
                "nav": float(account.get("NAV", 0)),
                "margin_used": float(account.get("marginUsed", 0)),
                "margin_available": float(account.get("marginAvailable", 0)),
                "buying_power": float(account.get("marginAvailable", 0)),
                "portfolio_value": float(account.get("NAV", 0)),
                "paper_trading": self.paper
            }
        except Exception as e:
            self.logger.error("Failed to get Oanda account info", error=str(e))
            return {"error": str(e)}
    
    def get_positions(self, account_id: Optional[str] = None) -> List[Position]:
        """Get all open positions"""
        target_account = account_id or self.account_id
        if not target_account:
            return []
        
        try:
            result = self._make_request("GET", f"/accounts/{target_account}/openPositions")
            if "error" in result or "positions" not in result:
                # API returned error response - raise exception
                error_msg = result.get("error", "Unknown error")
                raise Exception(f"Oanda API error: {error_msg}")
            
            positions = []
            for pos in result["positions"]:
                converted = self._convert_position(pos)
                if converted:
                    positions.append(converted)
            
            return positions
            
        except Exception as e:
            self.logger.error("Failed to get Oanda positions", error=str(e))
            # Re-raise so caller can handle API errors (timeouts, auth, etc.)
            raise
    
    def get_position(self, symbol: str, account_id: Optional[str] = None) -> Optional[Position]:
        """Get position for specific instrument"""
        # Oanda uses instrument format like "EUR_USD"
        instrument = symbol.replace("/", "_") if "/" in symbol else symbol
        
        target_account = account_id or self.account_id
        if not target_account:
            return None
        
        try:
            result = self._make_request("GET", f"/accounts/{target_account}/positions/{instrument}")
            if "error" in result or "position" not in result:
                return None
            
            return self._convert_position(result["position"])
            
        except Exception as e:
            # 404 means position doesn't exist (closed) - return None
            if "404" in str(e):
                return None
            # Any other error (timeout, 401, 500, etc.) - re-raise so caller can handle
            self.logger.error("Failed to get Oanda position", symbol=symbol, error=str(e))
            raise
    
    def _convert_position(self, oanda_pos: Dict) -> Optional[Position]:
        """Convert Oanda position to standard Position model"""
        try:
            instrument = oanda_pos.get("instrument", "")
            
            # Oanda has separate long/short positions
            long_units = float(oanda_pos.get("long", {}).get("units", 0))
            short_units = float(oanda_pos.get("short", {}).get("units", 0))
            
            # Calculate net position
            net_units = long_units + short_units  # short_units is negative
            
            if net_units == 0:
                return None  # No position
            
            side = "long" if net_units > 0 else "short"
            qty = abs(net_units)
            
            # Get average entry price
            if side == "long":
                avg_price = float(oanda_pos.get("long", {}).get("averagePrice", 0))
                unrealized_pl = float(oanda_pos.get("long", {}).get("unrealizedPL", 0))
            else:
                avg_price = float(oanda_pos.get("short", {}).get("averagePrice", 0))
                unrealized_pl = float(oanda_pos.get("short", {}).get("unrealizedPL", 0))
            
            # Get current price from pricing API
            pricing = self.get_quote(instrument)
            current_price = pricing.get("last", avg_price)
            
            # Calculate values
            cost_basis = qty * avg_price
            market_value = qty * current_price
            unrealized_pl_percent = (unrealized_pl / cost_basis * 100) if cost_basis > 0 else 0.0
            
            return Position(
                symbol=instrument,
                qty=qty,
                side=side,
                avg_entry_price=avg_price,
                current_price=current_price,
                market_value=market_value,
                cost_basis=cost_basis,
                unrealized_pl=unrealized_pl,
                unrealized_pl_percent=unrealized_pl_percent,
                broker_data=oanda_pos
            )
            
        except Exception as e:
            self.logger.error("Failed to convert Oanda position", error=str(e))
            return None
    
    def place_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        account_id: Optional[str] = None
    ) -> Order:
        """Place a trading order"""
        target_account = account_id or self.account_id
        if not target_account:
            raise ValueError("No account ID provided")
        
        # Oanda uses instrument format like "EUR_USD"
        instrument = symbol.replace("/", "_") if "/" in symbol else symbol
        
        # Oanda uses units (positive for buy, negative for sell)
        units = int(qty if side == OrderSide.BUY else -qty)
        
        # Map order type
        oanda_type = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.STOP: "STOP",
            OrderType.STOP_LIMIT: "STOP"  # Oanda doesn't have separate stop-limit
        }.get(order_type, "MARKET")
        
        # Map time in force
        oanda_tif = {
            TimeInForce.DAY: "GFD",  # Good for day
            TimeInForce.GTC: "GTC",
            TimeInForce.IOC: "IOC",
            TimeInForce.FOK: "FOK"
        }.get(time_in_force, "FOK")
        
        # Build order data
        order_data = {
            "order": {
                "type": oanda_type,
                "instrument": instrument,
                "units": str(units),
                "timeInForce": oanda_tif
            }
        }
        
        # Add price for non-market orders
        if limit_price and order_type != OrderType.MARKET:
            order_data["order"]["price"] = str(limit_price)
        
        if stop_price and order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            order_data["order"]["price"] = str(stop_price)
        
        try:
            result = self._make_request("POST", f"/accounts/{target_account}/orders", data=order_data)
            
            if "error" in result:
                raise Exception(result["error"])
            
            oanda_order = result.get("orderFillTransaction") or result.get("orderCreateTransaction", {})
            
            self.logger.info(
                "Oanda order placed",
                order_id=oanda_order.get("id"),
                instrument=instrument,
                side=side.value,
                qty=qty
            )
            
            return self._convert_order(oanda_order, instrument, qty, side, order_type, time_in_force)
            
        except Exception as e:
            self.logger.error("Failed to place Oanda order", error=str(e))
            raise
    
    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide,
        take_profit_price: float,
        stop_loss_price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
        account_id: Optional[str] = None
    ) -> Order:
        """Place a bracket order (market entry + TP + SL)"""
        target_account = account_id or self.account_id
        if not target_account:
            raise ValueError("No account ID provided")
        
        instrument = symbol.replace("/", "_") if "/" in symbol else symbol
        units = int(qty if side == OrderSide.BUY else -qty)
        
        # Oanda supports TP/SL on fill
        order_data = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(units),
                "timeInForce": "FOK",
                "takeProfitOnFill": {
                    "price": str(take_profit_price)
                },
                "stopLossOnFill": {
                    "price": str(stop_loss_price)
                }
            }
        }
        
        try:
            result = self._make_request("POST", f"/accounts/{target_account}/orders", data=order_data)
            
            if "error" in result:
                raise Exception(result["error"])
            
            oanda_order = result.get("orderFillTransaction") or result.get("orderCreateTransaction", {})
            
            self.logger.info(
                "Oanda bracket order placed",
                order_id=oanda_order.get("id"),
                instrument=instrument,
                tp=take_profit_price,
                sl=stop_loss_price
            )
            
            return self._convert_order(oanda_order, instrument, qty, side, OrderType.BRACKET, time_in_force)
            
        except Exception as e:
            self.logger.error("Failed to place Oanda bracket order", error=str(e))
            raise
    
    def place_limit_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide,
        limit_price: float,
        take_profit_price: float,
        stop_loss_price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
        account_id: Optional[str] = None
    ) -> Order:
        """Place a limit bracket order (limit entry + TP + SL)"""
        target_account = account_id or self.account_id
        if not target_account:
            raise ValueError("No account ID provided")
        
        instrument = symbol.replace("/", "_") if "/" in symbol else symbol
        units = int(qty if side == OrderSide.BUY else -qty)
        
        # Oanda supports TP/SL on fill for limit orders
        order_data = {
            "order": {
                "type": "LIMIT",
                "instrument": instrument,
                "units": str(units),
                "price": str(limit_price),
                "timeInForce": "GTC",  # Good till cancelled for limit orders
                "takeProfitOnFill": {
                    "price": str(take_profit_price)
                },
                "stopLossOnFill": {
                    "price": str(stop_loss_price)
                }
            }
        }
        
        try:
            result = self._make_request("POST", f"/accounts/{target_account}/orders", data=order_data)
            
            if "error" in result:
                raise Exception(result["error"])
            
            oanda_order = result.get("orderCreateTransaction", {})
            
            self.logger.info(
                "Oanda limit bracket order placed",
                order_id=oanda_order.get("id"),
                instrument=instrument,
                entry=limit_price,
                tp=take_profit_price,
                sl=stop_loss_price
            )
            
            return self._convert_order(oanda_order, instrument, qty, side, OrderType.LIMIT, time_in_force)
            
        except Exception as e:
            self.logger.error("Failed to place Oanda limit bracket order", error=str(e))
            raise
    
    def get_orders(self, account_id: Optional[str] = None) -> List[Order]:
        """Get all pending/open orders"""
        target_account = account_id or self.account_id
        if not target_account:
            return []
        
        try:
            result = self._make_request("GET", f"/accounts/{target_account}/pendingOrders")
            if "error" in result or "orders" not in result:
                return []
            
            orders = []
            for oanda_order in result["orders"]:
                try:
                    # Determine order type
                    order_type_str = oanda_order.get("type", "MARKET")
                    order_type = OrderType.MARKET
                    if "LIMIT" in order_type_str:
                        order_type = OrderType.LIMIT
                    elif "STOP" in order_type_str:
                        order_type = OrderType.STOP
                    
                    # Determine side from units
                    units = float(oanda_order.get("units", 0))
                    side = OrderSide.BUY if units > 0 else OrderSide.SELL
                    qty = abs(units)
                    
                    instrument = oanda_order.get("instrument", "")
                    symbol = instrument.replace("_", "/")
                    
                    # Get prices
                    limit_price = None
                    stop_price = None
                    if "price" in oanda_order:
                        limit_price = float(oanda_order["price"])
                    if "priceBound" in oanda_order:
                        stop_price = float(oanda_order["priceBound"])
                    
                    time_in_force = TimeInForce.GTC
                    if oanda_order.get("timeInForce") == "FOK":
                        time_in_force = TimeInForce.DAY
                    
                    # Parse createTime — Oanda returns Unix timestamps
                    # (due to Accept-Datetime-Format: UNIX header)
                    submitted_at = None
                    if oanda_order.get("createTime"):
                        try:
                            submitted_at = datetime.fromtimestamp(float(oanda_order["createTime"]))
                        except (ValueError, TypeError):
                            try:
                                submitted_at = datetime.fromisoformat(
                                    oanda_order["createTime"].replace("Z", "+00:00")
                                )
                            except Exception:
                                pass

                    order = Order(
                        order_id=oanda_order.get("id"),
                        symbol=symbol,
                        qty=qty,
                        side=side,
                        type=order_type,
                        status=OrderStatus.OPEN,
                        limit_price=limit_price,
                        stop_price=stop_price,
                        time_in_force=time_in_force,
                        submitted_at=submitted_at,
                        broker_data=oanda_order
                    )
                    orders.append(order)
                except Exception as e:
                    self.logger.warning(f"Failed to convert Oanda order: {e}")
                    continue
            
            return orders
            
        except Exception as e:
            self.logger.error("Failed to get Oanda orders", error=str(e))
            return []
    
    def cancel_order(self, order_id: str, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Cancel an order"""
        target_account = account_id or self.account_id
        if not target_account:
            return {"success": False, "error": "No account ID provided"}
        
        try:
            result = self._make_request("PUT", f"/accounts/{target_account}/orders/{order_id}/cancel")
            self.logger.info("Oanda order cancelled", order_id=order_id)
            return {"success": True, "order_id": order_id, "result": result}
        except Exception as e:
            self.logger.error("Failed to cancel Oanda order", error=str(e))
            return {"success": False, "error": str(e)}
    
    def close_trade_by_id(
        self,
        trade_id: str,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Close a specific trade by its ID.
        This is the correct method for closing bracket orders (trades with SL/TP).
        """
        target_account = account_id or self.account_id
        if not target_account:
            return {"success": False, "error": "No account ID provided"}
        
        try:
            # Close the trade - this automatically cancels associated SL/TP orders
            result = self._make_request("PUT", f"/accounts/{target_account}/trades/{trade_id}/close", data={})
            
            # Check if there's an error in the response
            if "error" in result:
                error_msg = result["error"]
                self.logger.error("Failed to close Oanda trade", trade_id=trade_id, error=error_msg)
                return {"success": False, "error": error_msg}
            
            self.logger.info("Oanda trade closed", trade_id=trade_id)
            
            # Extract P&L from the close transaction
            close_txn = result.get("orderFillTransaction") or result.get("orderCreateTransaction", {})
            final_pl = float(close_txn.get("pl", 0)) if close_txn else 0.0
            
            return {
                "success": True, 
                "trade_id": trade_id,
                "final_pnl": final_pl,
                "result": result
            }
        except Exception as e:
            self.logger.error("Failed to close Oanda trade", trade_id=trade_id, error=str(e))
            return {"success": False, "error": str(e)}
    
    def close_position(
        self,
        symbol: str,
        qty: Optional[float] = None,
        account_id: Optional[str] = None,
        trade_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Close a position.
        If trade_id is provided, closes the specific trade (recommended for bracket orders).
        Otherwise, attempts to close all positions for the symbol.
        """
        target_account = account_id or self.account_id
        if not target_account:
            return {"success": False, "error": "No account ID provided"}
        
        # If we have a trade ID, use the trade close endpoint (correct for bracket orders)
        if trade_id:
            return self.close_trade_by_id(trade_id, target_account)
        
        # Otherwise, try position close endpoint
        instrument = symbol.replace("/", "_") if "/" in symbol else symbol
        
        # First, try to get all open trades for this instrument and close them individually
        try:
            trades_result = self._make_request("GET", f"/accounts/{target_account}/openTrades", params={"instrument": instrument})
            trades = trades_result.get("trades", [])
            
            if trades:
                self.logger.info("Found open trades for instrument, closing individually", instrument=instrument, count=len(trades))
                results = []
                for trade in trades:
                    trade_id = trade.get("id")
                    close_result = self.close_trade_by_id(trade_id, target_account)
                    results.append(close_result)
                
                # Return success if all trades closed successfully
                all_success = all(r.get("success") for r in results)
                total_pnl = sum(r.get("final_pnl", 0) for r in results)
                
                return {
                    "success": all_success,
                    "symbol": instrument,
                    "trades_closed": len(results),
                    "final_pnl": total_pnl,
                    "results": results
                }
        except Exception as e:
            self.logger.warning("Could not fetch open trades, falling back to position close", error=str(e))
        
        # Fallback: use position close endpoint
        # Determine units to close
        if qty:
            data = {"longUnits": str(int(qty))} if qty > 0 else {"shortUnits": str(int(abs(qty)))}
        else:
            data = {"longUnits": "ALL", "shortUnits": "ALL"}
        
        try:
            result = self._make_request("PUT", f"/accounts/{target_account}/positions/{instrument}/close", data=data)
            
            # Check if there's an error in the response
            if "error" in result:
                error_msg = result["error"]
                
                # If position doesn't exist, it's already closed - treat as success
                if "CLOSEOUT_POSITION_DOESNT_EXIST" in error_msg or "does not exist" in error_msg:
                    self.logger.info("Oanda position already closed", instrument=instrument)
                    return {
                        "success": True, 
                        "symbol": instrument, 
                        "message": "Position was already closed",
                        "already_closed": True
                    }
                else:
                    # Other errors are actual failures
                    self.logger.error("Failed to close Oanda position", error=error_msg)
                    return {"success": False, "error": error_msg}
            
            self.logger.info("Oanda position closed", instrument=instrument)
            return {"success": True, "symbol": instrument, "result": result}
        except Exception as e:
            self.logger.error("Failed to close Oanda position", error=str(e))
            return {"success": False, "error": str(e)}
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get real-time quote"""
        target_account = self.account_id
        if not target_account:
            return {"error": "No account ID provided"}
        
        instrument = symbol.replace("/", "_") if "/" in symbol else symbol
        
        try:
            result = self._make_request("GET", f"/accounts/{target_account}/pricing", params={"instruments": instrument})
            
            if "error" in result or "prices" not in result:
                return {"error": result.get("error", "No price data")}
            
            price_data = result["prices"][0] if result["prices"] else {}
            
            bid = float(price_data.get("bids", [{}])[0].get("price", 0))
            ask = float(price_data.get("asks", [{}])[0].get("price", 0))
            
            return {
                "symbol": instrument,
                "bid": bid,
                "ask": ask,
                "last": (bid + ask) / 2,
                "timestamp": price_data.get("time")
            }
        except Exception as e:
            self.logger.error("Failed to get Oanda quote", symbol=symbol, error=str(e))
            return {"error": str(e)}
    
    def get_recent_candles(
        self,
        symbol: str,
        count: int = 60,
        granularity: str = "M1",
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent candlestick data from Oanda.

        Uses the /v3/instruments/{instrument}/candles endpoint.

        Args:
            symbol: Trading symbol (e.g. EUR_USD)
            count: Number of candles to fetch
            granularity: Candle granularity (M1, M5, M15, H1, etc.)

        Returns:
            List of dicts with keys: high, low, open, close, time
        """
        instrument = symbol.replace("/", "_") if "/" in symbol else symbol

        try:
            result = self._make_request(
                "GET",
                f"/instruments/{instrument}/candles",
                params={
                    "count": count,
                    "granularity": granularity,
                    "price": "M",  # mid-price candles
                },
            )

            if "error" in result or "candles" not in result:
                self.logger.warning(
                    "oanda_candles_fetch_failed",
                    symbol=symbol,
                    error=result.get("error", "No candle data"),
                )
                return []

            candles = []
            for c in result["candles"]:
                mid = c.get("mid", {})
                candles.append(
                    {
                        "high": float(mid.get("h", 0)),
                        "low": float(mid.get("l", 0)),
                        "open": float(mid.get("o", 0)),
                        "close": float(mid.get("c", 0)),
                        "time": c.get("time"),
                        "complete": c.get("complete", False),
                    }
                )
            return candles

        except Exception as e:
            self.logger.error(
                "oanda_candles_fetch_error", symbol=symbol, error=str(e)
            )
            return []

    def _convert_order(
        self,
        oanda_order: Dict,
        instrument: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType,
        time_in_force: TimeInForce
    ) -> Order:
        """Convert Oanda order to standard Order model"""
        # Parse timestamp - OANDA returns Unix timestamp (due to Accept-Datetime-Format: UNIX header)
        submitted_at = None
        if oanda_order.get("time"):
            try:
                # Try parsing as Unix timestamp first (string or float)
                timestamp = float(oanda_order["time"])
                submitted_at = datetime.fromtimestamp(timestamp)
            except (ValueError, TypeError):
                # Fallback: try ISO format
                try:
                    submitted_at = datetime.fromisoformat(oanda_order["time"].replace("Z", "+00:00"))
                except:
                    self.logger.warning("failed_to_parse_oanda_timestamp", time=oanda_order.get("time"))
                    submitted_at = None
        
        return Order(
            order_id=str(oanda_order.get("id", "unknown")),
            symbol=instrument,
            qty=qty,
            side=side,
            type=order_type,
            status=OrderStatus.FILLED if oanda_order.get("type") == "ORDER_FILL" else OrderStatus.ACCEPTED,
            filled_qty=qty if oanda_order.get("type") == "ORDER_FILL" else 0.0,
            filled_price=float(oanda_order.get("price", 0)) if oanda_order.get("price") else None,
            time_in_force=time_in_force,
            submitted_at=submitted_at,
            broker_data=oanda_order
        )
    
    def get_trade_details(self, trade_id: str, account_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get details for a specific trade by ID from Oanda.
        
        Uses /accounts/{accountID}/trades/{tradeSpecifier} endpoint.
        Critical for reconciliation: when a position is closed by bracket orders (SL/TP)
        between monitoring checks, we fetch the final realized P&L from the broker.
        
        Args:
            trade_id: Oanda trade ID
            account_id: Account ID (optional, uses default if not provided)
            
        Returns:
            Dict with trade details including realized P&L for closed trades
        """
        target_account = account_id or self.account_id
        if not target_account:
            return {"found": False, "error": "No account ID provided"}
        
        try:
            result = self._make_request(
                "GET", f"/accounts/{target_account}/trades/{trade_id}"
            )
            
            if "error" in result or "trade" not in result:
                # Trade might be closed — try the closed-trade-details endpoint
                # by checking recent transactions instead
                self.logger.info(
                    "trade_not_in_open_trades_checking_history",
                    trade_id=trade_id,
                )
                return self._get_closed_trade_details(trade_id, target_account)
            
            trade = result["trade"]
            state = trade.get("state", "OPEN").upper()
            unrealized_pl = float(trade.get("unrealizedPL", 0))
            realized_pl = float(trade.get("realizedPL", 0))
            
            # Parse open time
            open_time = None
            if trade.get("openTime"):
                try:
                    open_time = datetime.fromtimestamp(float(trade["openTime"]))
                except (ValueError, TypeError):
                    open_time = None
            
            return {
                "found": True,
                "state": "open" if state == "OPEN" else "closed",
                "realized_pl": realized_pl,
                "unrealized_pl": unrealized_pl,
                "close_time": None,  # Open trades don't have close time
                "instrument": trade.get("instrument", ""),
                "open_price": float(trade.get("price", 0)),
                "close_price": None,
                "units": float(trade.get("currentUnits", trade.get("initialUnits", 0))),
                "initial_units": float(trade.get("initialUnits", 0)),
                "stop_loss": trade.get("stopLossOrder", {}).get("price"),
                "take_profit": trade.get("takeProfitOrder", {}).get("price"),
                "broker_data": trade,
            }
            
        except Exception as e:
            self.logger.error(
                "get_trade_details_failed", trade_id=trade_id, error=str(e)
            )
            return {"found": False, "error": str(e)}
    
    def _get_closed_trade_details(self, trade_id: str, account_id: str) -> Dict[str, Any]:
        """
        Get details for a closed trade by searching recent transactions.
        
        When a trade is closed (by SL/TP bracket orders), it's no longer in /trades.
        We search recent ORDER_FILL transactions that reference this trade_id to get
        the final realized P&L.
        
        Args:
            trade_id: Oanda trade ID
            account_id: Oanda account ID
            
        Returns:
            Dict with trade details including realized P&L
        """
        try:
            # Fetch recent transactions (last 200) to find the close fill
            result = self._make_request(
                "GET",
                f"/accounts/{account_id}/transactions",
                params={
                    "count": 200,
                    "type": "ORDER_FILL",
                },
            )
            
            if "error" in result:
                self.logger.warning(
                    "transaction_fetch_failed",
                    trade_id=trade_id,
                    error=result.get("error"),
                )
                return {"found": False, "error": result.get("error")}
            
            # Get transaction IDs and fetch details
            transaction_ids = result.get("pages", [])
            
            # Try the simpler approach: fetch transactions in the ID range
            # Oanda returns a list of transaction pages (URLs)
            # Let's try fetching by trade ID using the trade endpoint with state filter
            
            # Alternative: check /accounts/{id}/trades/{tradeId} — closed trades are
            # still available if we use the "state" filter
            # But Oanda doesn't support fetching closed trades by ID directly.
            
            # Best approach: fetch recent ORDER_FILL transactions and find the one
            # that references our trade_id
            txn_result = self._make_request(
                "GET",
                f"/accounts/{account_id}/transactions",
                params={
                    "pageSize": 200,
                }
            )
            
            # Parse transaction pages to find relevant fills
            # Oanda returns paginated transaction IDs
            last_txn_id = txn_result.get("lastTransactionID")
            if not last_txn_id:
                return {"found": False, "error": "No transactions found"}
            
            # Fetch the last batch of transactions by ID range
            from_id = max(1, int(last_txn_id) - 200)
            range_result = self._make_request(
                "GET",
                f"/accounts/{account_id}/transactions/idrange",
                params={
                    "from": str(from_id),
                    "to": last_txn_id,
                },
            )
            
            transactions = range_result.get("transactions", [])
            
            # Look for ORDER_FILL transactions that reference our trade_id
            realized_pl = 0.0
            close_price = None
            close_time = None
            instrument = ""
            units_closed = 0.0
            found_close = False
            
            for txn in transactions:
                if txn.get("type") != "ORDER_FILL":
                    continue
                
                # Check if this fill closed our trade
                trades_closed = txn.get("tradesClosed", [])
                for tc in trades_closed:
                    if str(tc.get("tradeID")) == str(trade_id):
                        realized_pl += float(tc.get("realizedPL", 0))
                        units_closed += abs(float(tc.get("units", 0)))
                        close_price = float(txn.get("price", 0))
                        instrument = txn.get("instrument", "")
                        found_close = True
                        
                        # Parse close time
                        if txn.get("time"):
                            try:
                                close_time = datetime.fromtimestamp(
                                    float(txn["time"])
                                ).isoformat()
                            except (ValueError, TypeError):
                                close_time = txn.get("time")
                
                # Also check tradesReduced for partial closes
                trades_reduced = txn.get("tradesReduced", [])
                for tr in trades_reduced:
                    if str(tr.get("tradeID")) == str(trade_id):
                        realized_pl += float(tr.get("realizedPL", 0))
                        found_close = True
            
            if found_close:
                self.logger.info(
                    "found_closed_trade_details",
                    trade_id=trade_id,
                    realized_pl=realized_pl,
                    close_price=close_price,
                )
                return {
                    "found": True,
                    "state": "closed",
                    "realized_pl": realized_pl,
                    "unrealized_pl": 0.0,  # Closed trade has no unrealized P&L
                    "close_time": close_time,
                    "instrument": instrument,
                    "open_price": 0.0,  # Not available from fill transactions
                    "close_price": close_price,
                    "units": units_closed,
                    "initial_units": units_closed,
                    "broker_data": {"transactions": [t for t in transactions if any(
                        str(tc.get("tradeID")) == str(trade_id)
                        for tc in t.get("tradesClosed", []) + t.get("tradesReduced", [])
                    )]},
                }
            
            return {
                "found": False,
                "error": f"Trade {trade_id} not found in recent transactions",
            }
            
        except Exception as e:
            self.logger.error(
                "closed_trade_lookup_failed",
                trade_id=trade_id,
                error=str(e),
            )
            return {"found": False, "error": str(e)}

    def has_active_symbol(self, symbol: str, account_id: Optional[str] = None) -> bool:
        """
        Check if there is an active position or open order for a symbol.
        
        Oanda-specific implementation that handles underscore/slash normalization.
        Oanda uses EUR_USD format, while other systems may use EUR/USD.
        
        IMPORTANT: This method re-raises exceptions on API errors so that callers
        (like reconciliation) can distinguish between "no position" and "API failure".
        Swallowing errors could cause false reconciliation (marking active trades as closed).
        
        Args:
            symbol: Trading symbol (in any format: EUR_USD or EUR/USD)
            account_id: Account ID (optional)
            
        Returns:
            True if symbol has active position or open order, False otherwise
            
        Raises:
            Exception: On broker API errors (caller must handle)
        """
        # Normalize to Oanda format (EUR_USD)
        normalized_symbol = symbol.replace("/", "_") if "/" in symbol else symbol
        
        # Check for open position — let exceptions propagate
        position = self.get_position(normalized_symbol, account_id)
        if position and position.qty != 0:
            return True
        
        # Check for open orders — let exceptions propagate
        orders = self.get_orders(account_id)
        for order in orders:
            # Normalize order symbol for comparison
            order_normalized = order.symbol.replace("/", "_") if "/" in order.symbol else order.symbol
            if order_normalized == normalized_symbol:
                return True
        
        return False

