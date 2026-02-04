"""
Base Broker Service

Abstract base class defining the interface for broker integrations.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()


class OrderSide(str, Enum):
    """Order side enum"""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type enum"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    BRACKET = "bracket"  # Market order with TP/SL


class TimeInForce(str, Enum):
    """Time in force enum"""
    DAY = "day"
    GTC = "gtc"  # Good til cancelled
    IOC = "ioc"  # Immediate or cancel
    FOK = "fok"  # Fill or kill


class OrderStatus(str, Enum):
    """Order status enum"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Position(BaseModel):
    """Standard position model across all brokers"""
    symbol: str
    qty: float
    side: str  # "long" or "short"
    avg_entry_price: float
    current_price: float
    market_value: float
    cost_basis: float
    unrealized_pl: float
    unrealized_pl_percent: float
    broker_data: Dict[str, Any] = {}  # Original broker response


class Order(BaseModel):
    """Standard order model across all brokers"""
    order_id: str
    symbol: str
    qty: float
    side: OrderSide
    type: OrderType
    status: OrderStatus
    filled_qty: float = 0.0
    filled_price: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    broker_data: Dict[str, Any] = {}  # Original broker response


class BrokerService(ABC):
    """
    Abstract base class for broker integrations.
    
    All broker services must implement these methods.
    """
    
    def __init__(self, api_key: str, secret_key: str = None, account_id: str = None, paper: bool = True):
        """
        Initialize broker service.
        
        Args:
            api_key: API key/token
            secret_key: Secret key (if applicable)
            account_id: Account ID
            paper: Whether to use paper/demo trading
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.account_id = account_id
        self.paper = paper
        self.logger = logger.bind(broker=self.__class__.__name__, paper=paper)
    
    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to broker API.
        
        Returns:
            Dict with status and message
        """
        pass
    
    @abstractmethod
    def get_account_info(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get account information.
        
        Returns:
            Dict with account details (balance, buying_power, etc.)
        """
        pass
    
    @abstractmethod
    def get_positions(self, account_id: Optional[str] = None) -> List[Position]:
        """
        Get all open positions.
        
        Returns:
            List of Position objects
        """
        pass
    
    @abstractmethod
    def get_position(self, symbol: str, account_id: Optional[str] = None) -> Optional[Position]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Trading symbol
            account_id: Account ID (optional)
            
        Returns:
            Position object if exists, None otherwise
        """
        pass
    
    @abstractmethod
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
        """
        Place a trading order.
        
        Args:
            symbol: Trading symbol
            qty: Quantity
            side: Buy or sell
            order_type: Market, limit, stop, etc.
            limit_price: Limit price (for limit orders)
            stop_price: Stop price (for stop orders)
            time_in_force: How long order remains active
            account_id: Account ID (optional)
            
        Returns:
            Order object
        """
        pass
    
    @abstractmethod
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
        Place a bracket order (market entry + take profit + stop loss).
        
        Args:
            symbol: Trading symbol
            qty: Quantity
            side: Buy or sell
            take_profit_price: Take profit price
            stop_loss_price: Stop loss price
            time_in_force: How long order remains active
            account_id: Account ID (optional)
            
        Returns:
            Order object for the main order
        """
        pass
    
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
        Place a limit bracket order (limit entry + take profit + stop loss).
        
        This is a convenience method that calls place_order with limit price
        and OrderType.LIMIT. Brokers that support native limit brackets can override.
        
        Args:
            symbol: Trading symbol
            qty: Quantity
            side: Buy or sell
            limit_price: Entry limit price
            take_profit_price: Take profit price
            stop_loss_price: Stop loss price
            time_in_force: How long order remains active
            account_id: Account ID (optional)
            
        Returns:
            Order object for the main order
        """
        # Default implementation: place simple limit order
        # Brokers with native bracket support should override this
        return self.place_order(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            time_in_force=time_in_force,
            account_id=account_id
        )
    
    @abstractmethod
    def get_orders(self, account_id: Optional[str] = None) -> List[Order]:
        """
        Get all open/pending orders.
        
        Args:
            account_id: Account ID (optional)
            
        Returns:
            List of Order objects
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str, account_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Cancel an existing order.
        
        Args:
            order_id: Order ID to cancel
            account_id: Account ID (optional)
            
        Returns:
            Dict with cancellation status
        """
        pass
    
    @abstractmethod
    def close_position(
        self,
        symbol: str,
        qty: Optional[float] = None,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Close a position (all or partial).
        
        Args:
            symbol: Trading symbol
            qty: Quantity to close (None = close all)
            account_id: Account ID (optional)
            
        Returns:
            Dict with closure status
        """
        pass
    
    @abstractmethod
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get real-time quote for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dict with price data (bid, ask, last, etc.)
        """
        pass
    
    def is_paper_trading(self) -> bool:
        """Check if this is a paper trading account."""
        return self.paper

