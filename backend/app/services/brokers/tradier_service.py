"""
Tradier Broker Service

Implementation using Tradier Brokerage REST API for US stocks and options.
Based on tested tradier_service.py from project root.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import requests

from app.services.brokers.base import (
    BrokerService, Position, Order, OrderSide, OrderType, TimeInForce, OrderStatus
)


class TradierBrokerService(BrokerService):
    """
    Tradier broker service using REST API.
    
    Supports US stocks and options trading.
    """
    
    def __init__(self, api_key: str, secret_key: str = None, account_id: str = None, paper: bool = True):
        super().__init__(api_key, secret_key, account_id, paper)
        
        # Tradier doesn't use secret_key, just access token
        self.api_token = api_key
        
        # Set base URLs
        if paper:
            self.base_url = "https://sandbox.tradier.com"
            self.stream_url = "https://sandbox.tradier.com"
        else:
            self.base_url = "https://api.tradier.com"
            self.stream_url = "https://stream.tradier.com"
        
        # Setup session
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json'
        })
        
        self.logger.info("Tradier broker initialized", account_id=account_id, paper=paper)

        # Prevent Celery tasks from hanging indefinitely on broker I/O
        # (connect_timeout, read_timeout) in seconds
        self._http_timeout = (5, 20)
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> Dict[str, Any]:
        """Make HTTP request to Tradier API"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=self._http_timeout)
            elif method.upper() == 'POST':
                response = self.session.post(url, params=params, data=data, timeout=self._http_timeout)
            elif method.upper() == 'PUT':
                response = self.session.put(url, params=params, data=data, timeout=self._http_timeout)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url, params=params, timeout=self._http_timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout as e:
            self.logger.error(f"Tradier API timeout: {e}")
            return {"error": f"Tradier API timeout: {str(e)}"}
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Tradier API request failed: {e}")
            return {"error": str(e)}
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to Tradier API"""
        try:
            result = self._make_request('GET', '/v1/user/profile')
            if 'error' not in result:
                return {
                    "status": "connected",
                    "message": "Tradier API connection successful",
                    "profile": result,
                    "paper_trading": self.paper
                }
            else:
                return {"status": "error", "error": result["error"]}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_account_info(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Get Tradier account information"""
        account = account_id or self.account_id
        if not account:
            return {"error": "No account ID provided"}
        
        try:
            result = self._make_request('GET', f'/v1/accounts/{account}')
            if "error" in result:
                return result
            
            account_data = result.get("account", {})
            balance_data = account_data.get("balance", {})
            
            # Tradier balance fields:
            #   total_equity    – total account value
            #   cash_available  – settled cash
            #   stock_buying_power – buying power for stock purchases
            #   option_buying_power – buying power for option purchases (often different)
            total_equity = float(balance_data.get("total_equity", 0))
            cash_available = float(balance_data.get("cash_available", 0))
            # Use stock_buying_power for stocks; fall back to option_buying_power, then total_equity
            stock_bp = balance_data.get("stock_buying_power")
            option_bp = balance_data.get("option_buying_power")
            buying_power = float(stock_bp or option_bp or total_equity or 0)
            
            self.logger.info(
                "tradier_account_info",
                total_equity=total_equity,
                cash_available=cash_available,
                buying_power=buying_power,
                raw_stock_bp=stock_bp,
                raw_option_bp=option_bp,
            )
            
            return {
                "account_id": account_data.get("account_number"),
                "status": account_data.get("status"),
                "type": account_data.get("type"),
                "balance": total_equity,
                "equity": total_equity,
                "cash": cash_available,
                "buying_power": buying_power,
                "portfolio_value": total_equity,
                "paper_trading": self.paper
            }
        except Exception as e:
            self.logger.error("Failed to get Tradier account info", error=str(e))
            return {"error": str(e)}
    
    def get_positions(self, account_id: Optional[str] = None) -> List[Position]:
        """
        Get all open positions.
        
        ⚠️ FIX #1: Raises exceptions on API errors instead of returning empty list.
        This allows callers to distinguish between "no positions" (empty list) and
        "API error" (exception), preventing premature trade cancellation.
        """
        account = account_id or self.account_id
        if not account:
            return []
        
        result = self._make_request('GET', f'/v1/accounts/{account}/positions')
        
        # Check for API errors in response
        if "error" in result:
            error_msg = result.get("error", "Unknown API error")
            self.logger.error("Tradier API error getting positions", error=error_msg, account_id=account)
            raise Exception(f"Tradier API error: {error_msg}")
        
        if "positions" not in result:
            # This is unusual - API returned success but no positions key
            # Could be a malformed response, treat as API error
            self.logger.error("Tradier API returned unexpected response format", response_keys=list(result.keys()))
            raise Exception("Tradier API returned unexpected response format (missing 'positions' key)")
        
        positions_data = result["positions"]
        if positions_data is None or positions_data == "null":
            # No positions is a valid state (empty account)
            return []
        
        # Handle single position vs list
        if isinstance(positions_data, dict) and "position" in positions_data:
            pos_list = positions_data["position"]
            if not isinstance(pos_list, list):
                pos_list = [pos_list]
        else:
            # positions_data is not in expected format
            return []
        
        positions = []
        for pos in pos_list:
            converted = self._convert_position(pos)
            if converted:
                positions.append(converted)
        
        return positions
    
    def get_position(self, symbol: str, account_id: Optional[str] = None) -> Optional[Position]:
        """Get position for specific symbol"""
        positions = self.get_positions(account_id)
        for pos in positions:
            if pos.symbol == symbol.upper():
                return pos
        return None
    
    def _convert_position(self, tradier_pos: Dict) -> Optional[Position]:
        """Convert Tradier position to standard Position model"""
        try:
            symbol = tradier_pos.get("symbol", "")
            qty = float(tradier_pos.get("quantity", 0))
            
            if qty == 0:
                return None
            
            side = "long" if qty > 0 else "short"
            qty = abs(qty)
            
            # Get current quote for market value
            quote = self.get_quote(symbol)
            current_price = quote.get("last", 0)
            
            # Calculate values
            cost_basis = float(tradier_pos.get("cost_basis", 0))
            market_value = qty * current_price
            unrealized_pl = market_value - cost_basis
            unrealized_pl_percent = (unrealized_pl / cost_basis * 100) if cost_basis > 0 else 0.0
            avg_entry_price = cost_basis / qty if qty > 0 else 0
            
            return Position(
                symbol=symbol,
                qty=qty,
                side=side,
                avg_entry_price=avg_entry_price,
                current_price=current_price,
                market_value=market_value,
                cost_basis=cost_basis,
                unrealized_pl=unrealized_pl,
                unrealized_pl_percent=unrealized_pl_percent,
                broker_data=tradier_pos
            )
            
        except Exception as e:
            self.logger.error("Failed to convert Tradier position", error=str(e))
            return None
    
    def _convert_order(self, tradier_order: Dict) -> Optional[Order]:
        """Convert Tradier order to standard Order model"""
        try:
            order_id = str(tradier_order.get("id", ""))
            if not order_id:
                return None
            
            symbol = tradier_order.get("symbol", "").upper()
            qty = float(tradier_order.get("quantity", 0))
            side_str = tradier_order.get("side", "").lower()
            side = OrderSide.BUY if side_str == "buy" else OrderSide.SELL
            
            # Map Tradier order type
            tradier_type = tradier_order.get("type", "").lower()
            if tradier_type == "market":
                order_type = OrderType.MARKET
            elif tradier_type == "limit":
                order_type = OrderType.LIMIT
            elif tradier_type == "stop":
                order_type = OrderType.STOP
            elif tradier_type == "stop_limit":
                order_type = OrderType.STOP_LIMIT
            else:
                order_type = OrderType.MARKET
            
            # Map Tradier status
            tradier_status = tradier_order.get("status", "").lower()
            if tradier_status in ["filled", "executed"]:
                status = OrderStatus.FILLED
            elif tradier_status in ["open", "pending"]:
                status = OrderStatus.OPEN
            elif tradier_status == "partially_filled":
                status = OrderStatus.PARTIALLY_FILLED
            elif tradier_status == "cancelled":
                status = OrderStatus.CANCELLED
            elif tradier_status == "rejected":
                status = OrderStatus.REJECTED
            else:
                status = OrderStatus.ACCEPTED
            
            # Map time in force
            tradier_tif = tradier_order.get("duration", "").lower()
            if tradier_tif == "gtc":
                time_in_force = TimeInForce.GTC
            elif tradier_tif == "day":
                time_in_force = TimeInForce.DAY
            elif tradier_tif == "ioc":
                time_in_force = TimeInForce.IOC
            elif tradier_tif == "fok":
                time_in_force = TimeInForce.FOK
            else:
                time_in_force = TimeInForce.DAY
            
            filled_qty = float(tradier_order.get("executed_quantity", 0))
            limit_price = float(tradier_order.get("price", 0)) if tradier_order.get("price") else None
            stop_price = float(tradier_order.get("stop", 0)) if tradier_order.get("stop") else None
            
            # Parse submitted_at timestamp if available
            submitted_at = None
            if tradier_order.get("created_at"):
                try:
                    from dateutil import parser
                    submitted_at = parser.parse(tradier_order["created_at"])
                except:
                    pass
            
            return Order(
                order_id=order_id,
                symbol=symbol,
                qty=qty,
                side=side,
                type=order_type,
                status=status,
                filled_qty=filled_qty,
                filled_price=limit_price if status == OrderStatus.FILLED else None,
                limit_price=limit_price,
                stop_price=stop_price,
                time_in_force=time_in_force,
                submitted_at=submitted_at or datetime.utcnow(),
                broker_data=tradier_order
            )
            
        except Exception as e:
            self.logger.error("Failed to convert Tradier order", error=str(e))
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
        account = account_id or self.account_id
        if not account:
            raise ValueError("No account ID provided")
        
        # Map order type
        tradier_type = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP: "stop",
            OrderType.STOP_LIMIT: "stop_limit"
        }.get(order_type, "market")
        
        # Map time in force
        tradier_tif = {
            TimeInForce.DAY: "day",
            TimeInForce.GTC: "gtc",
            TimeInForce.IOC: "ioc",
            TimeInForce.FOK: "fok"
        }.get(time_in_force, "day")
        
        # Validate parameters
        if order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and not limit_price:
            raise ValueError("limit_price required for limit orders")
        
        if order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and not stop_price:
            raise ValueError("stop_price required for stop orders")
        
        # Prepare order data
        order_data = {
            'class': 'equity',
            'symbol': symbol.upper(),
            'side': side.value.lower(),
            'quantity': str(int(qty)),
            'type': tradier_type,
            'duration': tradier_tif
        }
        
        if limit_price:
            order_data['price'] = str(limit_price)
        
        if stop_price:
            order_data['stop'] = str(stop_price)
        
        try:
            result = self._make_request('POST', f'/v1/accounts/{account}/orders', data=order_data)
            
            if 'error' in result:
                raise Exception(result['error'])
            
            order_response = result.get("order", {})
            order_id = order_response.get("id", "unknown")
            
            self.logger.info(
                "Tradier order placed",
                order_id=order_id,
                symbol=symbol,
                side=side.value,
                qty=qty
            )
            
            return Order(
                order_id=str(order_id),
                symbol=symbol.upper(),
                qty=qty,
                side=side,
                type=order_type,
                status=OrderStatus.ACCEPTED,
                filled_qty=0.0,
                limit_price=limit_price,
                stop_price=stop_price,
                time_in_force=time_in_force,
                submitted_at=datetime.utcnow(),
                broker_data=order_response
            )
            
        except Exception as e:
            self.logger.error("Failed to place Tradier order", error=str(e))
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
        """
        Place a bracket order (market entry + TP + SL).
        
        ⚠️ FIX #4: Implements actual TP/SL orders for Tradier.
        Note: Tradier doesn't support native bracket orders like Alpaca.
        We place the main market order, then immediately place TP/SL as separate limit/stop orders.
        These are NOT linked (not true OCO), but they provide exit protection.
        """
        account = account_id or self.account_id
        if not account:
            raise ValueError("No account ID provided")
        
        # Place main market order
        main_order = self.place_order(
            symbol, qty, side, OrderType.MARKET, time_in_force=time_in_force, account_id=account
        )
        
        # ⚠️ FIX #4: Place TP/SL orders after main order
        # Determine opposite side for exit orders
        exit_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY
        
        tp_order_id = None
        sl_order_id = None
        
        try:
            # Place take profit order (limit order at TP price)
            tp_order = self.place_order(
                symbol=symbol,
                qty=qty,
                side=exit_side,
                order_type=OrderType.LIMIT,
                limit_price=take_profit_price,
                time_in_force=time_in_force,
                account_id=account
            )
            tp_order_id = tp_order.order_id
            self.logger.info(
                "Tradier TP order placed",
                tp_order_id=tp_order_id,
                symbol=symbol,
                tp_price=take_profit_price
            )
        except Exception as e:
            self.logger.error(
                "Failed to place Tradier TP order",
                error=str(e),
                symbol=symbol,
                tp_price=take_profit_price
            )
            # Don't fail the entire bracket order if TP fails - main order is already placed
        
        try:
            # Place stop loss order (stop order at SL price)
            sl_order = self.place_order(
                symbol=symbol,
                qty=qty,
                side=exit_side,
                order_type=OrderType.STOP,
                stop_price=stop_loss_price,
                time_in_force=time_in_force,
                account_id=account
            )
            sl_order_id = sl_order.order_id
            self.logger.info(
                "Tradier SL order placed",
                sl_order_id=sl_order_id,
                symbol=symbol,
                sl_price=stop_loss_price
            )
        except Exception as e:
            self.logger.error(
                "Failed to place Tradier SL order",
                error=str(e),
                symbol=symbol,
                sl_price=stop_loss_price
            )
            # Don't fail the entire bracket order if SL fails - main order is already placed
        
        self.logger.info(
            "Tradier bracket order placed",
            main_order_id=main_order.order_id,
            tp_order_id=tp_order_id,
            sl_order_id=sl_order_id,
            symbol=symbol,
            tp=take_profit_price,
            sl=stop_loss_price
        )
        
        # Update order type to indicate it's a bracket
        main_order.type = OrderType.BRACKET
        
        # Store TP/SL order IDs in broker_data for reference
        if main_order.broker_data:
            main_order.broker_data["tp_order_id"] = tp_order_id
            main_order.broker_data["sl_order_id"] = sl_order_id
        else:
            main_order.broker_data = {
                "tp_order_id": tp_order_id,
                "sl_order_id": sl_order_id
            }
        
        return main_order
    
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
        """
        Place a limit bracket order (limit entry + TP + SL).
        
        ⚠️ FIX #4: For limit orders, we place the entry limit order first.
        TP/SL orders will be placed by monitoring once the limit order fills.
        This is because Tradier doesn't support conditional orders that activate on fill.
        """
        account = account_id or self.account_id
        if not account:
            raise ValueError("No account ID provided")
        
        # Place limit entry order
        limit_order = self.place_order(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            time_in_force=time_in_force,
            account_id=account
        )
        
        # Store TP/SL prices in broker_data so monitoring can place exit orders once limit fills
        if limit_order.broker_data:
            limit_order.broker_data["take_profit_price"] = take_profit_price
            limit_order.broker_data["stop_loss_price"] = stop_loss_price
            limit_order.broker_data["bracket_order"] = True
        else:
            limit_order.broker_data = {
                "take_profit_price": take_profit_price,
                "stop_loss_price": stop_loss_price,
                "bracket_order": True
            }
        
        self.logger.info(
            "Tradier limit bracket order placed",
            order_id=limit_order.order_id,
            symbol=symbol,
            entry_price=limit_price,
            tp=take_profit_price,
            sl=stop_loss_price,
            note="TP/SL orders will be placed by monitoring once limit order fills"
        )
        
        # Update order type to indicate it's a bracket
        limit_order.type = OrderType.BRACKET
        
        return limit_order
    
    def get_orders(self, account_id: Optional[str] = None) -> List[Order]:
        """Get all open orders"""
        account = account_id or self.account_id
        if not account:
            return []
        
        try:
            result = self._make_request('GET', f'/v1/accounts/{account}/orders')
            
            if "error" in result or "orders" not in result:
                return []
            
            orders_data = result["orders"]
            if orders_data is None or orders_data == "null":
                return []
            
            # Handle single order vs list
            if isinstance(orders_data, dict) and "order" in orders_data:
                order_list = orders_data["order"]
                if not isinstance(order_list, list):
                    order_list = [order_list]
            else:
                return []
            
            # Filter only open/pending orders
            orders = []
            for order_data in order_list:
                status = order_data.get("status", "").lower()
                if status in ["open", "pending", "partially_filled"]:
                    try:
                        converted = self._convert_order(order_data)
                        if converted:
                            orders.append(converted)
                    except Exception as e:
                        self.logger.warning(f"Failed to convert Tradier order: {e}")
                        continue
            
            return orders
            
        except Exception as e:
            self.logger.error("Failed to get Tradier orders", error=str(e))
            return []
    
    def cancel_order(self, order_id: str, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Cancel an order"""
        account = account_id or self.account_id
        if not account:
            return {"success": False, "error": "No account ID provided"}
        
        try:
            result = self._make_request('DELETE', f'/v1/accounts/{account}/orders/{order_id}')
            self.logger.info("Tradier order cancelled", order_id=order_id)
            return {"success": True, "order_id": order_id, "result": result}
        except Exception as e:
            self.logger.error("Failed to cancel Tradier order", error=str(e))
            return {"success": False, "error": str(e)}
    
    def close_position(
        self,
        symbol: str,
        qty: Optional[float] = None,
        account_id: Optional[str] = None,
        trade_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Close a position.
        
        Args:
            symbol: Trading symbol
            qty: Number of shares/units to close (None = close all)
            account_id: Override account ID
            trade_id: Ignored for Tradier (accepted for API compatibility with Oanda)
        """
        try:
            # Get current position
            pos = self.get_position(symbol, account_id)
            if not pos:
                return {"success": False, "error": f"Position not found for {symbol}"}
            
            # Determine closing qty
            close_qty = qty if qty else pos.qty
            
            # Determine opposite side
            close_side = OrderSide.SELL if pos.side == "long" else OrderSide.BUY
            
            # Place closing order
            order = self.place_order(
                symbol, close_qty, close_side, OrderType.MARKET, time_in_force=TimeInForce.DAY, account_id=account_id
            )
            
            self.logger.info("Tradier position closed", symbol=symbol, qty=close_qty)
            return {"success": True, "order_id": order.order_id, "qty_closed": close_qty}
            
        except Exception as e:
            self.logger.error("Failed to close Tradier position", symbol=symbol, error=str(e))
            return {"success": False, "error": str(e)}
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get real-time quote"""
        try:
            result = self._make_request('GET', '/v1/markets/quotes', params={'symbols': symbol.upper()})
            
            if 'error' in result or 'quotes' not in result:
                return {"error": result.get('error', 'No quote data')}
            
            quotes = result['quotes']
            if isinstance(quotes, dict) and 'quote' in quotes:
                quote_data = quotes['quote']
                if isinstance(quote_data, list):
                    quote_data = quote_data[0] if quote_data else {}
            else:
                return {"error": "Invalid quote format"}
            
            return {
                "symbol": symbol.upper(),
                "bid": float(quote_data.get("bid", 0)),
                "ask": float(quote_data.get("ask", 0)),
                "last": float(quote_data.get("last", 0)),
                "volume": quote_data.get("volume", 0),
                "timestamp": quote_data.get("trade_date")
            }
        except Exception as e:
            self.logger.error("Failed to get Tradier quote", symbol=symbol, error=str(e))
            return {"error": str(e)}

    # ─────────────────────────────────────────────────────────────
    # Trade details & P&L (required for reconciliation)
    # ─────────────────────────────────────────────────────────────

    def get_trade_details(
        self, trade_id: str, account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get details for a specific trade/order by ID from Tradier.

        Uses ``GET /v1/accounts/{account_id}/orders/{order_id}``.
        Tradier tracks all executions as *orders*; this method looks up the
        order, checks its status, and computes realized P&L when possible.
        """
        account = account_id or self.account_id
        if not account:
            return {"found": False, "error": "No account ID provided"}

        try:
            result = self._make_request(
                "GET", f"/v1/accounts/{account}/orders/{trade_id}"
            )

            if "error" in result:
                self.logger.warning(
                    "tradier_order_not_found",
                    trade_id=trade_id,
                    error=result.get("error"),
                )
                return {
                    "found": False,
                    "error": result.get("error", "Order not found"),
                }

            order_data = result.get("order", {})
            if not order_data:
                return {"found": False, "error": "Empty order response"}

            tradier_status = (order_data.get("status", "") or "").lower()
            symbol = order_data.get("symbol", "").upper()
            qty = float(order_data.get("quantity", 0))
            exec_qty = float(order_data.get("exec_quantity", 0))
            avg_fill_price = (
                float(order_data["avg_fill_price"])
                if order_data.get("avg_fill_price")
                else None
            )
            side = (order_data.get("side", "") or "").lower()

            if tradier_status == "filled":
                state = "closed"
            elif tradier_status in ("open", "pending", "partially_filled"):
                state = "open"
            elif tradier_status in (
                "canceled", "cancelled", "rejected", "expired",
            ):
                state = "cancelled"
            else:
                state = tradier_status

            realized_pl = 0.0
            close_price = None
            close_time = None

            if tradier_status == "filled" and avg_fill_price:
                close_price, realized_pl, close_time = self._calculate_order_pnl(
                    account, symbol, trade_id, side, avg_fill_price, exec_qty or qty
                )

            created_at = order_data.get("create_date")
            transaction_date = order_data.get("transaction_date")

            return {
                "found": True,
                "state": state,
                "realized_pl": realized_pl,
                "unrealized_pl": 0.0,
                "close_time": close_time or transaction_date,
                "instrument": symbol,
                "open_price": avg_fill_price or 0.0,
                "close_price": close_price,
                "units": exec_qty or qty,
                "initial_units": qty,
                "broker_data": order_data,
            }

        except Exception as e:
            self.logger.error(
                "get_trade_details_failed", trade_id=trade_id, error=str(e)
            )
            return {"found": False, "error": str(e)}

    def _calculate_order_pnl(
        self,
        account: str,
        symbol: str,
        entry_order_id: str,
        entry_side: str,
        entry_price: float,
        qty: float,
    ) -> tuple:
        """Calculate realized P&L by finding matching closing orders."""
        try:
            result = self._make_request(
                "GET",
                f"/v1/accounts/{account}/orders",
                params={"includeTags": "true"},
            )

            if "error" in result:
                self.logger.warning(
                    "tradier_order_history_fetch_failed",
                    error=result.get("error"),
                )
                return None, 0.0, None

            orders_data = result.get("orders", {})
            if not orders_data or orders_data == "null":
                return None, 0.0, None

            orders = orders_data.get("order", [])
            if isinstance(orders, dict):
                orders = [orders]

            closing_side = "sell" if entry_side == "buy" else "buy"

            closing_orders = []
            found_entry = False
            for order in orders:
                oid = str(order.get("id", ""))
                if oid == str(entry_order_id):
                    found_entry = True
                    continue
                if not found_entry:
                    continue

                o_status = (order.get("status", "") or "").lower()
                o_side = (order.get("side", "") or "").lower()
                o_symbol = (order.get("symbol", "") or "").upper()

                if (
                    o_status == "filled"
                    and o_side == closing_side
                    and o_symbol == symbol
                ):
                    closing_orders.append(order)

            if not closing_orders:
                try:
                    pos = self.get_position(symbol, account)
                    if pos:
                        return None, 0.0, None
                except Exception:
                    pass
                return None, 0.0, None

            closing_order = closing_orders[-1]
            close_price = float(closing_order.get("avg_fill_price", 0))
            close_time = (
                closing_order.get("transaction_date")
                or closing_order.get("create_date")
            )
            close_qty = float(
                closing_order.get("exec_quantity", 0)
            ) or float(closing_order.get("quantity", 0))

            if entry_side == "buy":
                realized_pl = (close_price - entry_price) * min(qty, close_qty)
            else:
                realized_pl = (entry_price - close_price) * min(qty, close_qty)

            self.logger.info(
                "tradier_pnl_calculated",
                symbol=symbol,
                entry_price=entry_price,
                close_price=close_price,
                qty=qty,
                realized_pl=realized_pl,
            )

            return close_price, realized_pl, close_time

        except Exception as e:
            self.logger.warning(
                "tradier_pnl_calculation_failed",
                symbol=symbol,
                entry_order_id=entry_order_id,
                error=str(e),
            )
            return None, 0.0, None
