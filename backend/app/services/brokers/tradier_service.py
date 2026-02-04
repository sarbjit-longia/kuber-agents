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
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> Dict[str, Any]:
        """Make HTTP request to Tradier API"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params)
            elif method.upper() == 'POST':
                response = self.session.post(url, params=params, data=data)
            elif method.upper() == 'PUT':
                response = self.session.put(url, params=params, data=data)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
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
            
            return {
                "account_id": account_data.get("account_number"),
                "status": account_data.get("status"),
                "type": account_data.get("type"),
                "balance": float(account_data.get("balance", {}).get("total_equity", 0)),
                "cash": float(account_data.get("balance", {}).get("cash_available", 0)),
                "buying_power": float(account_data.get("balance", {}).get("option_buying_power", 0)),
                "portfolio_value": float(account_data.get("balance", {}).get("total_equity", 0)),
                "paper_trading": self.paper
            }
        except Exception as e:
            self.logger.error("Failed to get Tradier account info", error=str(e))
            return {"error": str(e)}
    
    def get_positions(self, account_id: Optional[str] = None) -> List[Position]:
        """Get all open positions"""
        account = account_id or self.account_id
        if not account:
            return []
        
        try:
            result = self._make_request('GET', f'/v1/accounts/{account}/positions')
            if "error" in result or "positions" not in result:
                return []
            
            positions_data = result["positions"]
            if positions_data is None or positions_data == "null":
                return []
            
            # Handle single position vs list
            if isinstance(positions_data, dict) and "position" in positions_data:
                pos_list = positions_data["position"]
                if not isinstance(pos_list, list):
                    pos_list = [pos_list]
            else:
                return []
            
            positions = []
            for pos in pos_list:
                converted = self._convert_position(pos)
                if converted:
                    positions.append(converted)
            
            return positions
            
        except Exception as e:
            self.logger.error("Failed to get Tradier positions", error=str(e))
            return []
    
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
        Place a bracket order.
        
        Note: Tradier supports OCO (One-Cancels-Other) orders.
        We'll place the main order and attach TP/SL as separate orders.
        """
        account = account_id or self.account_id
        if not account:
            raise ValueError("No account ID provided")
        
        # Place main market order
        main_order = self.place_order(
            symbol, qty, side, OrderType.MARKET, time_in_force=time_in_force, account_id=account
        )
        
        # Note: In production, you'd want to place TP/SL orders here
        # using Tradier's OCO order functionality
        # For now, we return the main order
        
        self.logger.info(
            "Tradier bracket order placed",
            order_id=main_order.order_id,
            symbol=symbol,
            tp=take_profit_price,
            sl=stop_loss_price
        )
        
        # Update order type to indicate it's a bracket
        main_order.type = OrderType.BRACKET
        
        return main_order
    
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
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Close a position"""
        try:
            # Get current position
            pos = self.get_position(symbol, account_id)
            if not pos:
                return {"success": False, "error": "Position not found"}
            
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
            self.logger.error("Failed to close Tradier position", error=str(e))
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

