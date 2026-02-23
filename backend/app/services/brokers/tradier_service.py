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

            # Try to parse the response body BEFORE raise_for_status so we
            # capture Tradier's error message (e.g. "Invalid Access Token")
            # even on 4xx / 5xx responses.
            if not response.ok:
                error_detail = f"{response.status_code} {response.reason}"
                try:
                    error_body = response.json()
                    # Tradier wraps errors in a "fault" key
                    fault = error_body.get("fault", {})
                    fault_msg = fault.get("faultstring", "")
                    if fault_msg:
                        error_detail = f"{response.status_code} - {fault_msg}"
                    elif "error" in error_body:
                        error_detail = f"{response.status_code} - {error_body['error']}"
                    else:
                        error_detail = f"{response.status_code} - {error_body}"
                except Exception:
                    error_detail = f"{response.status_code} - {response.text[:200]}"

                self.logger.error(
                    "tradier_api_error",
                    url=url,
                    method=method,
                    status_code=response.status_code,
                    error=error_detail,
                )
                return {"error": error_detail}

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
        Place a bracket order (market entry + TP + SL) using Tradier's native OTOCO order.

        Tradier supports One-Triggers-One-Cancels-Other (OTOCO) orders natively.
        The entry order triggers an OCO pair (take-profit limit + stop-loss stop),
        and filling either leg automatically cancels the other.

        See: https://docs.tradier.com/reference/advanced-orders
        """
        account = account_id or self.account_id
        if not account:
            raise ValueError("No account ID provided")

        exit_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY

        tradier_tif = {
            TimeInForce.DAY: "day",
            TimeInForce.GTC: "gtc",
            TimeInForce.IOC: "ioc",
            TimeInForce.FOK: "fok",
        }.get(time_in_force, "gtc")

        # Tradier OTOCO uses indexed form-data parameters:
        #   [0] = entry order (market)
        #   [1] = take-profit leg (limit)
        #   [2] = stop-loss leg (stop)
        order_data = {
            'class': 'otoco',
            'duration': tradier_tif,
            # Leg 0 – entry (market)
            'symbol[0]': symbol.upper(),
            'side[0]': side.value.lower(),
            'quantity[0]': str(int(qty)),
            'type[0]': 'market',
            # Leg 1 – take-profit (limit)
            'symbol[1]': symbol.upper(),
            'side[1]': exit_side.value.lower(),
            'quantity[1]': str(int(qty)),
            'type[1]': 'limit',
            'price[1]': str(take_profit_price),
            # Leg 2 – stop-loss (stop)
            'symbol[2]': symbol.upper(),
            'side[2]': exit_side.value.lower(),
            'quantity[2]': str(int(qty)),
            'type[2]': 'stop',
            'stop[2]': str(stop_loss_price),
        }

        try:
            result = self._make_request('POST', f'/v1/accounts/{account}/orders', data=order_data)

            if 'error' in result:
                raise Exception(result['error'])

            order_response = result.get("order", {})
            order_id = order_response.get("id", "unknown")

            self.logger.info(
                "Tradier OTOCO bracket order placed",
                order_id=order_id,
                symbol=symbol,
                side=side.value,
                qty=qty,
                tp=take_profit_price,
                sl=stop_loss_price,
            )

            return Order(
                order_id=str(order_id),
                symbol=symbol.upper(),
                qty=qty,
                side=side,
                type=OrderType.BRACKET,
                status=OrderStatus.ACCEPTED,
                filled_qty=0.0,
                limit_price=None,
                stop_price=None,
                time_in_force=time_in_force,
                submitted_at=datetime.utcnow(),
                broker_data=order_response,
            )

        except Exception as e:
            self.logger.error("Failed to place Tradier OTOCO bracket order", error=str(e))
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
        """
        Place a limit bracket order (limit entry + TP + SL) using Tradier's native OTOCO order.

        Tradier supports One-Triggers-One-Cancels-Other (OTOCO) orders natively.
        The limit entry order triggers an OCO pair (take-profit limit + stop-loss stop)
        once filled, and filling either exit leg automatically cancels the other.

        See: https://docs.tradier.com/reference/advanced-orders
        """
        account = account_id or self.account_id
        if not account:
            raise ValueError("No account ID provided")

        exit_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY

        tradier_tif = {
            TimeInForce.DAY: "day",
            TimeInForce.GTC: "gtc",
            TimeInForce.IOC: "ioc",
            TimeInForce.FOK: "fok",
        }.get(time_in_force, "gtc")

        # Tradier OTOCO uses indexed form-data parameters:
        #   [0] = entry order (limit)
        #   [1] = take-profit leg (limit)
        #   [2] = stop-loss leg (stop)
        order_data = {
            'class': 'otoco',
            'duration': tradier_tif,
            # Leg 0 – entry (limit)
            'symbol[0]': symbol.upper(),
            'side[0]': side.value.lower(),
            'quantity[0]': str(int(qty)),
            'type[0]': 'limit',
            'price[0]': str(limit_price),
            # Leg 1 – take-profit (limit)
            'symbol[1]': symbol.upper(),
            'side[1]': exit_side.value.lower(),
            'quantity[1]': str(int(qty)),
            'type[1]': 'limit',
            'price[1]': str(take_profit_price),
            # Leg 2 – stop-loss (stop)
            'symbol[2]': symbol.upper(),
            'side[2]': exit_side.value.lower(),
            'quantity[2]': str(int(qty)),
            'type[2]': 'stop',
            'stop[2]': str(stop_loss_price),
        }

        try:
            result = self._make_request('POST', f'/v1/accounts/{account}/orders', data=order_data)

            if 'error' in result:
                raise Exception(result['error'])

            order_response = result.get("order", {})
            order_id = order_response.get("id", "unknown")

            self.logger.info(
                "Tradier OTOCO limit bracket order placed",
                order_id=order_id,
                symbol=symbol,
                side=side.value,
                qty=qty,
                entry_price=limit_price,
                tp=take_profit_price,
                sl=stop_loss_price,
            )

            return Order(
                order_id=str(order_id),
                symbol=symbol.upper(),
                qty=qty,
                side=side,
                type=OrderType.BRACKET,
                status=OrderStatus.ACCEPTED,
                filled_qty=0.0,
                limit_price=limit_price,
                stop_price=None,
                time_in_force=time_in_force,
                submitted_at=datetime.utcnow(),
                broker_data=order_response,
            )

        except Exception as e:
            self.logger.error("Failed to place Tradier OTOCO limit bracket order", error=str(e))
            raise
    
    def get_orders(self, account_id: Optional[str] = None) -> List[Order]:
        """Get all open orders.

        Raises on API errors so that callers (e.g. ``has_active_symbol``,
        reconciliation) can distinguish between "no orders" and "API failure".
        Returning ``[]`` on errors previously caused false reconciliation —
        the caller assumed no orders existed when the API was simply unreachable.
        """
        account = account_id or self.account_id
        if not account:
            return []

        result = self._make_request('GET', f'/v1/accounts/{account}/orders')

        if "error" in result:
            error_msg = result.get("error", "Unknown API error")
            self.logger.error("Tradier API error getting orders", error=error_msg, account_id=account)
            raise Exception(f"Tradier API error: {error_msg}")

        if "orders" not in result:
            self.logger.error(
                "Tradier API returned unexpected response format for orders",
                response_keys=list(result.keys()),
            )
            raise Exception("Tradier API returned unexpected response format (missing 'orders' key)")

        orders_data = result["orders"]
        if orders_data is None or orders_data == "null":
            return []

        # Handle single order vs list
        if isinstance(orders_data, dict) and "order" in orders_data:
            order_list = orders_data["order"]
            if not isinstance(order_list, list):
                order_list = [order_list]
        else:
            # orders_data is not in expected format — genuinely no orders
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
    
    def cancel_order(self, order_id: str, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Cancel an order and verify the broker acknowledged the cancellation."""
        account = account_id or self.account_id
        if not account:
            return {"success": False, "error": "No account ID provided"}

        try:
            result = self._make_request('DELETE', f'/v1/accounts/{account}/orders/{order_id}')

            # Verify the response — _make_request returns {"error": ...} on failures
            if "error" in result:
                error_msg = result["error"]
                self.logger.error(
                    "tradier_cancel_order_failed",
                    order_id=order_id,
                    error=error_msg,
                )
                return {"success": False, "order_id": order_id, "error": error_msg}

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
        """Close a position and cancel any remaining bracket (OTOCO) legs.

        After placing a market order to close the position, this method cancels
        all remaining open orders for the symbol to prevent stale TP/SL legs
        from executing and opening an unintended short position.

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

            # Cancel any remaining open orders for this symbol (bracket TP/SL legs).
            # Without this, stale limit-sell (TP) or stop-sell (SL) orders remain
            # active on the broker and can execute later, opening a short position.
            cancelled_ids = []
            try:
                open_orders = self.get_orders(account_id)
                for open_order in open_orders:
                    if open_order.symbol.upper() == symbol.upper() and open_order.order_id != order.order_id:
                        cancel_result = self.cancel_order(open_order.order_id, account_id)
                        if cancel_result.get("success"):
                            cancelled_ids.append(open_order.order_id)
                        else:
                            self.logger.warning(
                                "tradier_failed_to_cancel_bracket_leg",
                                order_id=open_order.order_id,
                                symbol=symbol,
                                error=cancel_result.get("error"),
                            )
                if cancelled_ids:
                    self.logger.info(
                        "tradier_cancelled_bracket_legs_after_close",
                        symbol=symbol,
                        cancelled_order_ids=cancelled_ids,
                    )
            except Exception as cancel_err:
                # Log but don't fail the close — position is already closed
                self.logger.warning(
                    "tradier_bracket_leg_cleanup_failed",
                    symbol=symbol,
                    error=str(cancel_err),
                )

            return {
                "success": True,
                "order_id": order.order_id,
                "qty_closed": close_qty,
                "cancelled_bracket_legs": cancelled_ids,
            }

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

    def get_trade_details(
        self,
        trade_id: Optional[str] = None,
        order_id: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get details for a specific trade/order by ID from Tradier.

        Uses GET /v1/accounts/{account_id}/orders/{order_id} endpoint.
        Tradier doesn't have a "trade" concept like Oanda — all executions
        are tracked as orders. This method therefore **prefers** ``order_id``
        over ``trade_id`` (which is actually a Tradier position ID and cannot
        be used with the orders endpoint).

        For filled orders, P&L is calculated from the average fill price
        and the corresponding closing order's fill price if available.

        Args:
            trade_id: Tradier position ID — ignored when ``order_id`` is available.
            order_id: Tradier order ID (preferred).
            account_id: Account ID (optional, uses default if not provided).

        Returns:
            Dict with standardized trade details matching the BrokerService interface.
        """
        # Tradier needs the order_id; trade_id is only a position ID
        effective_id = order_id or trade_id
        if not effective_id:
            return {"found": False, "error": "No order_id or trade_id provided"}

        account = account_id or self.account_id
        if not account:
            return {"found": False, "error": "No account ID provided"}

        try:
            # Try fetching the order directly using the effective ID
            result = self._make_request(
                'GET', f'/v1/accounts/{account}/orders/{effective_id}'
            )

            if 'error' in result:
                self.logger.warning(
                    "tradier_order_not_found",
                    order_id=effective_id,
                    error=result.get('error'),
                )
                return {"found": False, "error": result.get('error', 'Order not found')}

            order_data = result.get("order", {})
            if not order_data:
                return {"found": False, "error": "Empty order response"}

            tradier_status = (order_data.get("status", "") or "").lower()
            order_class = (order_data.get("class", "") or "").lower()
            symbol = (order_data.get("symbol", "") or "").upper()
            qty = float(order_data.get("quantity", 0))
            exec_qty = float(order_data.get("exec_quantity", 0))
            avg_fill_price = float(order_data.get("avg_fill_price", 0)) if order_data.get("avg_fill_price") else None
            side = (order_data.get("side", "") or "").lower()  # "buy" or "sell"

            # ── OTOCO parent orders: extract entry data from legs ────────
            # Tradier OTOCO parent orders have symbol=null, side=null, and
            # avg_fill_price=null at the top level. The actual data lives on
            # the child "leg" orders. We must parse legs to find:
            #   1. Entry leg → symbol, side, avg_fill_price, qty
            #   2. Closing leg (if filled) → close_price, realized_pl
            legs = order_data.get("leg", [])
            if isinstance(legs, dict):
                legs = [legs]

            entry_leg = None
            closing_leg = None

            if order_class == "otoco" and legs:
                # For OTOCO, legs are indexed [0]=entry, [1]=TP, [2]=SL
                # But we identify them by role rather than position for safety.

                # First pass: find the entry leg (first filled leg, or leg[0])
                for leg in legs:
                    leg_status = (leg.get("status", "") or "").lower()
                    leg_fill = float(leg.get("avg_fill_price", 0)) if leg.get("avg_fill_price") else None
                    leg_side = (leg.get("side", "") or "").lower()

                    if leg_status == "filled" and leg_fill:
                        if entry_leg is None:
                            # First filled leg is the entry
                            entry_leg = leg
                        else:
                            # Subsequent filled leg on the opposite side is the closing leg
                            entry_side = (entry_leg.get("side", "") or "").lower()
                            if leg_side != entry_side:
                                closing_leg = leg
                                break

                # If we found an entry leg, use its data for the parent order fields
                if entry_leg:
                    if not symbol:
                        symbol = (entry_leg.get("symbol", "") or "").upper()
                    if not side:
                        side = (entry_leg.get("side", "") or "").lower()
                    if not avg_fill_price:
                        avg_fill_price = float(entry_leg.get("avg_fill_price", 0)) if entry_leg.get("avg_fill_price") else None
                    entry_exec_qty = float(entry_leg.get("exec_quantity", 0))
                    entry_qty = float(entry_leg.get("quantity", 0))
                    if not exec_qty:
                        exec_qty = entry_exec_qty
                    if not qty:
                        qty = entry_qty

                    self.logger.info(
                        "tradier_otoco_entry_from_leg",
                        symbol=symbol,
                        side=side,
                        avg_fill_price=avg_fill_price,
                        exec_qty=exec_qty,
                        entry_leg_id=entry_leg.get("id"),
                    )

            # Determine state
            if order_class == "otoco":
                # For OTOCO orders, "filled" at the parent level means all
                # legs have resolved (entry filled + one exit leg filled +
                # other cancelled). We check leg-level status below.
                if tradier_status == "filled":
                    state = "closed"
                elif tradier_status in ("open", "pending", "partially_filled"):
                    # Check if entry leg is filled but exit legs are still open
                    if entry_leg and not closing_leg:
                        state = "open"  # Entry filled, waiting for SL/TP
                    else:
                        state = "open"
                elif tradier_status in ("canceled", "cancelled", "rejected", "expired"):
                    state = "cancelled"
                else:
                    state = tradier_status
            else:
                if tradier_status == "filled":
                    state = "closed"
                elif tradier_status in ("open", "pending", "partially_filled"):
                    state = "open"
                elif tradier_status in ("canceled", "cancelled", "rejected", "expired"):
                    state = "cancelled"
                else:
                    state = tradier_status

            # For Tradier, to get the realized P&L we need to find the
            # closing order(s). Look at order history for the same symbol.
            realized_pl = 0.0
            close_price = None
            close_time = None

            # ── OTOCO / multileg P&L handling ────────────────────────────
            # If we already identified a closing leg during the entry-leg scan
            # above, use it directly. Otherwise scan legs again for any filled
            # closing order (handles edge cases where leg order isn't sequential).
            if avg_fill_price and legs:
                if closing_leg:
                    # Already found during entry-leg scan
                    close_price = float(closing_leg.get("avg_fill_price", 0))
                    leg_qty = float(closing_leg.get("exec_quantity", 0)) or float(closing_leg.get("quantity", 0))
                    if side == "buy":
                        realized_pl = (close_price - avg_fill_price) * min(exec_qty or qty, leg_qty)
                    else:
                        realized_pl = (avg_fill_price - close_price) * min(exec_qty or qty, leg_qty)
                    close_time = closing_leg.get("transaction_date") or closing_leg.get("create_date")

                    leg_type = (closing_leg.get("type", "") or "").lower()
                    exit_via = "take-profit" if leg_type == "limit" else (
                        "stop-loss" if leg_type == "stop" else leg_type
                    )
                    self.logger.info(
                        "tradier_otoco_leg_pnl",
                        symbol=symbol,
                        exit_via=exit_via,
                        entry_price=avg_fill_price,
                        close_price=close_price,
                        realized_pl=realized_pl,
                        leg_id=closing_leg.get("id"),
                    )
                elif order_class != "otoco":
                    # Non-OTOCO: legacy scan for closing leg in legs array
                    closing_side = "sell" if side == "buy" else "buy"
                    for leg in legs:
                        leg_status = (leg.get("status", "") or "").lower()
                        leg_side = (leg.get("side", "") or "").lower()
                        leg_fill = float(leg.get("avg_fill_price", 0)) if leg.get("avg_fill_price") else None

                        if leg_status == "filled" and leg_side == closing_side and leg_fill:
                            close_price = leg_fill
                            leg_qty = float(leg.get("exec_quantity", 0)) or float(leg.get("quantity", 0))
                            if side == "buy":
                                realized_pl = (close_price - avg_fill_price) * min(exec_qty or qty, leg_qty)
                            else:
                                realized_pl = (avg_fill_price - close_price) * min(exec_qty or qty, leg_qty)
                            close_time = leg.get("transaction_date") or leg.get("create_date")

                            leg_type = (leg.get("type", "") or "").lower()
                            exit_via = "take-profit" if leg_type == "limit" else (
                                "stop-loss" if leg_type == "stop" else leg_type
                            )
                            self.logger.info(
                                "tradier_otoco_leg_pnl",
                                symbol=symbol,
                                exit_via=exit_via,
                                entry_price=avg_fill_price,
                                close_price=close_price,
                                realized_pl=realized_pl,
                                leg_id=leg.get("id"),
                            )
                            break

            # Fallback: scan order history for a matching closing order
            # (only for non-OTOCO orders — OTOCO legs are self-contained)
            if close_price is None and avg_fill_price and order_class != "otoco":
                close_price, realized_pl, close_time = self._calculate_order_pnl(
                    account, symbol, effective_id, side, avg_fill_price, exec_qty or qty
                )

            # Extract timestamps
            created_at = order_data.get("create_date")
            transaction_date = order_data.get("transaction_date")

            # ── Build leg details for monitoring/tracking ────────────────
            leg_details = []
            if legs:
                for leg in legs:
                    leg_info = {
                        "leg_id": str(leg.get("id", "")),
                        "type": (leg.get("type", "") or "").lower(),
                        "side": (leg.get("side", "") or "").lower(),
                        "status": (leg.get("status", "") or "").lower(),
                        "symbol": (leg.get("symbol", "") or "").upper(),
                        "quantity": float(leg.get("quantity", 0)),
                        "avg_fill_price": float(leg.get("avg_fill_price", 0)) if leg.get("avg_fill_price") else None,
                        "stop_price": float(leg.get("stop_price", 0)) if leg.get("stop_price") else None,
                        "price": float(leg.get("price", 0)) if leg.get("price") else None,
                    }
                    leg_details.append(leg_info)

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
                "order_class": order_class,
                "legs": leg_details,
                "broker_data": order_data,
            }

        except Exception as e:
            self.logger.error(
                "get_trade_details_failed", order_id=effective_id, error=str(e)
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
        """
        Calculate realized P&L for a Tradier order by finding matching closing orders.

        Looks at the account's order history for filled orders on the opposite side
        of the same symbol that were placed after the entry order.

        Returns:
            Tuple of (close_price, realized_pl, close_time)
        """
        try:
            # Get recent order history for this account
            result = self._make_request(
                'GET', f'/v1/accounts/{account}/orders',
                params={'includeTags': 'true'}
            )

            if 'error' in result:
                self.logger.warning(
                    "tradier_order_history_fetch_failed",
                    error=result.get('error'),
                )
                return None, 0.0, None

            orders_data = result.get("orders", {})
            if not orders_data or orders_data == "null":
                return None, 0.0, None

            orders = orders_data.get("order", [])
            if isinstance(orders, dict):
                orders = [orders]

            # Sort by create_date ascending so we reliably find entry → closing
            # order sequence regardless of the order Tradier returns them.
            orders.sort(key=lambda o: o.get("create_date", ""))

            # Determine the closing side
            closing_side = "sell" if entry_side == "buy" else "buy"

            # Find filled orders on the closing side for the same symbol
            # that were created after the entry order
            closing_orders = []
            found_entry = False
            for order in orders:
                oid = str(order.get("id", ""))
                if oid == str(entry_order_id):
                    found_entry = True
                    continue

                if not found_entry:
                    continue  # Skip orders before our entry

                order_status = (order.get("status", "") or "").lower()
                order_side = (order.get("side", "") or "").lower()
                order_symbol = (order.get("symbol", "") or "").upper()

                if (
                    order_status == "filled"
                    and order_side == closing_side
                    and order_symbol == symbol
                ):
                    closing_orders.append(order)

            if not closing_orders:
                # Position may still be open or closed through a different mechanism
                # Try checking if there's still an open position
                try:
                    pos = self.get_position(symbol, account)
                    if pos:
                        # Position still open — no realized P&L yet
                        return None, 0.0, None
                except Exception:
                    pass

                # No position found and no closing orders — assume closed at market
                return None, 0.0, None

            # Use the most recent closing order
            closing_order = closing_orders[-1]
            close_price = float(closing_order.get("avg_fill_price", 0))
            close_time = closing_order.get("transaction_date") or closing_order.get("create_date")
            close_qty = float(closing_order.get("exec_quantity", 0)) or float(closing_order.get("quantity", 0))

            # Calculate P&L
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
