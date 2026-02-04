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
                return []
            
            positions = []
            for pos in result["positions"]:
                converted = self._convert_position(pos)
                if converted:
                    positions.append(converted)
            
            return positions
            
        except Exception as e:
            self.logger.error("Failed to get Oanda positions", error=str(e))
            return []
    
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
            if "404" not in str(e):
                self.logger.warning("Failed to get Oanda position", symbol=symbol, error=str(e))
            return None
    
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
                        created_at=datetime.fromisoformat(oanda_order.get("createTime", "").replace("Z", "+00:00")) if oanda_order.get("createTime") else None,
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

