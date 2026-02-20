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
    OPEN = "open"  # Order is active/working on the broker (e.g. limit order waiting to fill)
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
    
    def get_recent_candles(
        self,
        symbol: str,
        count: int = 60,
        granularity: str = "M1",
    ) -> List[Dict[str, Any]]:
        """
        Get recent candlestick data for a symbol.

        Used by the monitoring loop to check if candle highs/lows breached
        stop-loss or take-profit levels that the spot-price check may have
        missed (e.g., price spiked between checks, or before monitoring
        started).

        Args:
            symbol: Trading symbol
            count: Number of candles to fetch (default 60 = last 1 hour of M1)
            granularity: Candle granularity (M1, M5, H1, etc.)

        Returns:
            List of dicts, each with at least: high, low, open, close, time.
            Empty list if not supported by the broker.
        """
        # Default implementation — brokers that support candles should override
        return []

    @abstractmethod
    def get_trade_details(
        self,
        trade_id: Optional[str] = None,
        order_id: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get details for a specific trade, including realized P&L for closed trades.

        The caller passes **both** ``trade_id`` (the position/trade identifier)
        and ``order_id`` (the order identifier) when available.  Each broker
        implementation decides which identifier is meaningful:

        * **Oanda** — uses ``trade_id`` (Oanda trade specifier).
        * **Tradier** — uses ``order_id`` (Tradier order ID; ``trade_id`` is a
          position ID which cannot be queried for P&L).
        * **Alpaca** — uses ``order_id`` (Alpaca order UUID).

        This is critical for reconciliation: when a position is closed by
        bracket orders (SL/TP) between monitoring checks, we need to fetch the
        final realized P&L from the broker rather than relying solely on the
        last monitoring snapshot.

        Every broker MUST implement this method.

        Args:
            trade_id: Position / trade identifier (meaningful for Oanda).
            order_id: Order identifier (meaningful for Tradier & Alpaca).
            account_id: Account ID (optional).

        Returns:
            Dict with trade details:
                - found (bool): Whether the trade was found
                - state (str): "open" or "closed"
                - realized_pl (float): Realized P&L (0 if open or not found)
                - unrealized_pl (float): Unrealized P&L (0 if closed or not found)
                - close_time (str|None): ISO timestamp when trade was closed
                - instrument (str): Trading symbol
                - open_price (float): Entry price
                - close_price (float|None): Exit price (if closed)
                - units (float): Position size
                - broker_data (dict): Raw broker response

        Raises:
            NotImplementedError: If broker subclass has not implemented this method
        """
        pass
    
    def is_paper_trading(self) -> bool:
        """Check if this is a paper trading account."""
        return self.paper
    
    def has_active_symbol(self, symbol: str, account_id: Optional[str] = None) -> bool:
        """
        Check if there is an active position or open order for a symbol.
        
        This method abstracts broker-specific symbol normalization and checking logic.
        Each broker implementation can override this if they need custom logic.
        
        IMPORTANT: This method re-raises exceptions on API errors so that callers
        (like reconciliation) can distinguish between "no position" and "API failure".
        Swallowing errors could cause false reconciliation (marking active trades as closed).
        
        Args:
            symbol: Trading symbol (in any format)
            account_id: Account ID (optional)
            
        Returns:
            True if symbol has active position or open order, False otherwise
            
        Raises:
            Exception: On broker API errors (caller must handle)
        """
        # Check for open position using broker's get_position method
        # (which handles broker-specific symbol normalization)
        # Let exceptions propagate — callers must distinguish "no position" from "API failure".
        position = self.get_position(symbol, account_id)
        if position and position.qty != 0:
            return True
        
        # Check for open orders
        orders = self.get_orders(account_id)
        
        normalized_symbol = symbol.upper()
        
        for order in orders:
            # Simple string comparison - works for most brokers
            if order.symbol.upper() == normalized_symbol:
                return True
        
        return False

