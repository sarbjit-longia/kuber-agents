"""
Alpaca Broker Service

Real implementation using Alpaca Trading API (alpaca-py).
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.services.brokers.base import (
    BrokerService, Position, Order, OrderSide, OrderType, TimeInForce, OrderStatus
)


class AlpacaBrokerService(BrokerService):
    """
    Alpaca broker service using alpaca-py library.
    
    Supports stocks, options, and crypto.
    """
    
    def __init__(self, api_key: str, secret_key: str, account_id: str = None, paper: bool = True):
        super().__init__(api_key, secret_key, account_id, paper)
        
        try:
            from alpaca.trading.client import TradingClient
            
            # Initialize Alpaca client
            self.client = TradingClient(
                api_key=api_key,
                secret_key=secret_key,
                paper=paper
            )
            
            # Get account info on init
            account = self.client.get_account()
            self.account_id = account.account_number
            
            self.logger.info("Alpaca broker initialized", account_id=self.account_id, paper=paper)
            
        except ImportError:
            raise ImportError("alpaca-py library not installed. Install with: pip install alpaca-py")
        except Exception as e:
            self.logger.error("Failed to initialize Alpaca broker", error=str(e))
            raise
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to Alpaca API"""
        try:
            account = self.client.get_account()
            return {
                "success": True,
                "status": "connected",
                "message": "Alpaca API connection successful",
                "account_status": account.status,
                "paper_trading": self.paper
            }
        except Exception as e:
            self.logger.error("Alpaca connection test failed", error=str(e))
            return {
                "success": False,
                "status": "error",
                "error": str(e)
            }
    
    def get_account_info(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Get Alpaca account information"""
        try:
            account = self.client.get_account()
            return {
                "account_id": account.account_number,
                "status": account.status,
                "currency": account.currency,
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
                "equity": float(account.equity),
                "last_equity": float(account.last_equity),
                "pattern_day_trader": account.pattern_day_trader,
                "trading_blocked": account.trading_blocked,
                "paper_trading": self.paper
            }
        except Exception as e:
            self.logger.error("Failed to get Alpaca account info", error=str(e))
            return {"error": str(e)}
    
    def get_positions(self, account_id: Optional[str] = None) -> List[Position]:
        """Get all open positions"""
        try:
            positions = self.client.get_all_positions()
            return [self._convert_position(pos) for pos in positions]
        except Exception as e:
            self.logger.error("Failed to get Alpaca positions", error=str(e))
            return []
    
    def get_position(self, symbol: str, account_id: Optional[str] = None) -> Optional[Position]:
        """Get position for specific symbol"""
        try:
            pos = self.client.get_open_position(symbol)
            return self._convert_position(pos)
        except Exception as e:
            # Position not found is expected, don't log as error
            if "404" not in str(e):
                self.logger.warning("Failed to get Alpaca position", symbol=symbol, error=str(e))
            return None
    
    def _convert_position(self, alpaca_pos) -> Position:
        """Convert Alpaca position to standard Position model"""
        qty = float(alpaca_pos.qty)
        avg_entry = float(alpaca_pos.avg_entry_price)
        current = float(alpaca_pos.current_price)
        market_value = float(alpaca_pos.market_value)
        cost_basis = float(alpaca_pos.cost_basis)
        unrealized_pl = float(alpaca_pos.unrealized_pl)
        unrealized_pl_percent = float(alpaca_pos.unrealized_plpc) * 100
        
        return Position(
            symbol=alpaca_pos.symbol,
            qty=qty,
            side="long" if qty > 0 else "short",
            avg_entry_price=avg_entry,
            current_price=current,
            market_value=market_value,
            cost_basis=cost_basis,
            unrealized_pl=unrealized_pl,
            unrealized_pl_percent=unrealized_pl_percent,
            broker_data={
                "asset_id": alpaca_pos.asset_id,
                "exchange": alpaca_pos.exchange,
                "asset_class": alpaca_pos.asset_class,
                "qty_available": alpaca_pos.qty_available
            }
        )
    
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
        try:
            from alpaca.trading.requests import (
                MarketOrderRequest, LimitOrderRequest, StopOrderRequest, StopLimitOrderRequest
            )
            from alpaca.trading.enums import OrderSide as AlpacaOrderSide, TimeInForce as AlpacaTimeInForce
            
            # Convert enums
            alpaca_side = AlpacaOrderSide.BUY if side == OrderSide.BUY else AlpacaOrderSide.SELL
            alpaca_tif = self._convert_time_in_force(time_in_force)
            
            # Build order request based on type
            if order_type == OrderType.MARKET:
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=alpaca_side,
                    time_in_force=alpaca_tif
                )
            elif order_type == OrderType.LIMIT:
                if not limit_price:
                    raise ValueError("limit_price required for limit orders")
                order_data = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=alpaca_side,
                    time_in_force=alpaca_tif,
                    limit_price=limit_price
                )
            elif order_type == OrderType.STOP:
                if not stop_price:
                    raise ValueError("stop_price required for stop orders")
                order_data = StopOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=alpaca_side,
                    time_in_force=alpaca_tif,
                    stop_price=stop_price
                )
            elif order_type == OrderType.STOP_LIMIT:
                if not limit_price or not stop_price:
                    raise ValueError("limit_price and stop_price required for stop-limit orders")
                order_data = StopLimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=alpaca_side,
                    time_in_force=alpaca_tif,
                    limit_price=limit_price,
                    stop_price=stop_price
                )
            else:
                raise ValueError(f"Unsupported order type: {order_type}")
            
            # Submit order
            alpaca_order = self.client.submit_order(order_data)
            
            self.logger.info(
                "Alpaca order placed",
                order_id=alpaca_order.id,
                symbol=symbol,
                side=side.value,
                qty=qty,
                type=order_type.value
            )
            
            return self._convert_order(alpaca_order)
            
        except Exception as e:
            self.logger.error("Failed to place Alpaca order", error=str(e))
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
        """Place a bracket order (entry + TP + SL)"""
        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide as AlpacaOrderSide, OrderClass
            
            alpaca_side = AlpacaOrderSide.BUY if side == OrderSide.BUY else AlpacaOrderSide.SELL
            alpaca_tif = self._convert_time_in_force(time_in_force)
            
            # Bracket order
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                time_in_force=alpaca_tif,
                order_class=OrderClass.BRACKET,
                take_profit={"limit_price": take_profit_price},
                stop_loss={"stop_price": stop_loss_price}
            )
            
            alpaca_order = self.client.submit_order(order_data)
            
            self.logger.info(
                "Alpaca bracket order placed",
                order_id=alpaca_order.id,
                symbol=symbol,
                side=side.value,
                qty=qty,
                tp=take_profit_price,
                sl=stop_loss_price
            )
            
            return self._convert_order(alpaca_order)
            
        except Exception as e:
            self.logger.error("Failed to place Alpaca bracket order", error=str(e))
            raise
    
    def get_orders(self, account_id: Optional[str] = None) -> List[Order]:
        """Get all open orders"""
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            
            request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            alpaca_orders = self.client.get_orders(filter=request)
            
            return [self._convert_order(order) for order in alpaca_orders]
            
        except Exception as e:
            self.logger.error("Failed to get Alpaca orders", error=str(e))
            return []
    
    def cancel_order(self, order_id: str, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Cancel an order"""
        try:
            self.client.cancel_order_by_id(order_id)
            self.logger.info("Alpaca order cancelled", order_id=order_id)
            return {"success": True, "order_id": order_id, "status": "cancelled"}
        except Exception as e:
            self.logger.error("Failed to cancel Alpaca order", order_id=order_id, error=str(e))
            return {"success": False, "error": str(e)}
    
    def close_position(
        self,
        symbol: str,
        qty: Optional[float] = None,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Close a position"""
        try:
            if qty:
                # Close partial position - need to create opposite order
                pos = self.get_position(symbol)
                if not pos:
                    return {"success": False, "error": "Position not found"}
                
                # Determine opposite side
                side = OrderSide.SELL if pos.side == "long" else OrderSide.BUY
                
                # Place closing order
                order = self.place_order(symbol, qty, side, OrderType.MARKET, time_in_force=TimeInForce.DAY)
                return {"success": True, "order_id": order.order_id, "qty_closed": qty}
            else:
                # Close entire position
                self.client.close_position(symbol)
                self.logger.info("Alpaca position closed", symbol=symbol)
                return {"success": True, "symbol": symbol, "status": "closed"}
                
        except Exception as e:
            self.logger.error("Failed to close Alpaca position", symbol=symbol, error=str(e))
            return {"success": False, "error": str(e)}
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get real-time quote"""
        try:
            from alpaca.data.requests import StockLatestQuoteRequest
            from alpaca.data.historical import StockHistoricalDataClient
            
            # Create data client (separate from trading client)
            data_client = StockHistoricalDataClient(self.api_key, self.secret_key)
            
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quote = data_client.get_stock_latest_quote(request)
            
            quote_data = quote[symbol]
            
            return {
                "symbol": symbol,
                "bid": float(quote_data.bid_price),
                "ask": float(quote_data.ask_price),
                "bid_size": quote_data.bid_size,
                "ask_size": quote_data.ask_size,
                "last": (float(quote_data.bid_price) + float(quote_data.ask_price)) / 2,
                "timestamp": quote_data.timestamp
            }
        except Exception as e:
            self.logger.error("Failed to get Alpaca quote", symbol=symbol, error=str(e))
            return {"error": str(e)}
    
    def _convert_order(self, alpaca_order) -> Order:
        """Convert Alpaca order to standard Order model"""
        return Order(
            order_id=str(alpaca_order.id),
            symbol=alpaca_order.symbol,
            qty=float(alpaca_order.qty) if alpaca_order.qty else 0.0,
            side=OrderSide.BUY if str(alpaca_order.side) == "buy" else OrderSide.SELL,
            type=self._convert_order_type(str(alpaca_order.type)),
            status=self._convert_order_status(str(alpaca_order.status)),
            filled_qty=float(alpaca_order.filled_qty) if alpaca_order.filled_qty else 0.0,
            filled_price=float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else None,
            limit_price=float(alpaca_order.limit_price) if alpaca_order.limit_price else None,
            stop_price=float(alpaca_order.stop_price) if alpaca_order.stop_price else None,
            time_in_force=self._convert_tif_from_alpaca(str(alpaca_order.time_in_force)),
            submitted_at=alpaca_order.submitted_at,
            filled_at=alpaca_order.filled_at,
            broker_data={
                "client_order_id": alpaca_order.client_order_id,
                "asset_class": alpaca_order.asset_class,
                "order_class": str(alpaca_order.order_class) if alpaca_order.order_class else None
            }
        )
    
    def _convert_time_in_force(self, tif: TimeInForce):
        """Convert standard TimeInForce to Alpaca enum"""
        from alpaca.trading.enums import TimeInForce as AlpacaTimeInForce
        
        mapping = {
            TimeInForce.DAY: AlpacaTimeInForce.DAY,
            TimeInForce.GTC: AlpacaTimeInForce.GTC,
            TimeInForce.IOC: AlpacaTimeInForce.IOC,
            TimeInForce.FOK: AlpacaTimeInForce.FOK
        }
        return mapping.get(tif, AlpacaTimeInForce.DAY)
    
    def _convert_tif_from_alpaca(self, tif: str) -> TimeInForce:
        """Convert Alpaca TIF string to standard TimeInForce"""
        mapping = {
            "day": TimeInForce.DAY,
            "gtc": TimeInForce.GTC,
            "ioc": TimeInForce.IOC,
            "fok": TimeInForce.FOK
        }
        return mapping.get(tif.lower(), TimeInForce.DAY)
    
    def _convert_order_type(self, order_type_str: str) -> OrderType:
        """Convert Alpaca order type string to standard OrderType"""
        mapping = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "stop": OrderType.STOP,
            "stop_limit": OrderType.STOP_LIMIT
        }
        return mapping.get(order_type_str.lower(), OrderType.MARKET)
    
    def _convert_order_status(self, status_str: str) -> OrderStatus:
        """Convert Alpaca order status string to standard OrderStatus"""
        mapping = {
            "new": OrderStatus.PENDING,
            "accepted": OrderStatus.ACCEPTED,
            "filled": OrderStatus.FILLED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "rejected": OrderStatus.REJECTED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED
        }
        return mapping.get(status_str.lower(), OrderStatus.PENDING)

