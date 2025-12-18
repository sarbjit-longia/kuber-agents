# Multi-Broker Integration

## Overview

Implemented a **unified broker abstraction layer** supporting three major brokers:
1. **Alpaca** - US stocks, options, and crypto
2. **Oanda** - Forex and CFD trading
3. **Tradier** - US stocks and options

All brokers use real, tested API implementations based on sample code from the project root.

---

## Architecture

### **Abstraction Layer Pattern**

Similar to the market data provider pattern, the broker integration uses a factory pattern with a common interface:

```python
BrokerService (ABC)
├── AlpacaBrokerService (using alpaca-py)
├── OandaBrokerService (using Oanda v3 REST API)
└── TradierBrokerService (using Tradier REST API)
```

### **Key Components**

1. **Base Interface** (`backend/app/services/brokers/base.py`)
   - Abstract base class defining standard methods
   - Common data models (Position, Order, OrderSide, OrderType, etc.)
   - Unified API across all brokers

2. **Broker Services** (`backend/app/services/brokers/`)
   - `alpaca_service.py` - Real Alpaca Trading API integration
   - `oanda_service.py` - Real Oanda v3 REST API integration
   - `tradier_service.py` - Real Tradier REST API integration

3. **Factory** (`backend/app/services/brokers/factory.py`)
   - Creates broker instances based on configuration
   - Supports tool config parsing
   - Lists available brokers with capabilities

4. **Tools** (`backend/app/tools/`)
   - `alpaca_broker.py` - Alpaca broker tool
   - `oanda_broker.py` - Oanda broker tool (NEW)
   - `tradier_broker.py` - Tradier broker tool (NEW)

5. **Trade Manager Agent** (`backend/app/agents/trade_manager_agent.py`)
   - Updated to use real broker APIs
   - Supports all three brokers seamlessly
   - Real position monitoring
   - Actual trade execution

---

## Broker Service Interface

All brokers implement these standard methods:

### **Connection & Account**
```python
test_connection() -> Dict[str, Any]
get_account_info(account_id: Optional[str] = None) -> Dict[str, Any]
```

### **Position Management**
```python
get_positions(account_id: Optional[str] = None) -> List[Position]
get_position(symbol: str, account_id: Optional[str] = None) -> Optional[Position]
close_position(symbol: str, qty: Optional[float] = None, account_id: Optional[str] = None) -> Dict[str, Any]
```

### **Order Execution**
```python
place_order(
    symbol: str,
    qty: float,
    side: OrderSide,
    order_type: OrderType = OrderType.MARKET,
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    time_in_force: TimeInForce = TimeInForce.DAY,
    account_id: Optional[str] = None
) -> Order

place_bracket_order(
    symbol: str,
    qty: float,
    side: OrderSide,
    take_profit_price: float,
    stop_loss_price: float,
    time_in_force: TimeInForce = TimeInForce.GTC,
    account_id: Optional[str] = None
) -> Order

cancel_order(order_id: str, account_id: Optional[str] = None) -> Dict[str, Any]
```

### **Market Data**
```python
get_quote(symbol: str) -> Dict[str, Any]
```

---

## Standard Data Models

### **Position**
```python
class Position(BaseModel):
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
```

### **Order**
```python
class Order(BaseModel):
    order_id: str
    symbol: str
    qty: float
    side: OrderSide  # BUY or SELL
    type: OrderType  # MARKET, LIMIT, STOP, STOP_LIMIT, BRACKET
    status: OrderStatus  # PENDING, ACCEPTED, FILLED, etc.
    filled_qty: float = 0.0
    filled_price: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    broker_data: Dict[str, Any] = {}
```

---

## Broker-Specific Details

### **1. Alpaca** (`alpaca-py` library)

**Features:**
- Real-time stock, options, and crypto trading
- Official Python SDK
- Paper and live trading support
- Bracket orders with automatic TP/SL

**Configuration:**
```python
{
    "account_type": "paper" | "live",
    "api_key": "your_api_key",
    "secret_key": "your_secret_key",
    "order_type": "market" | "limit" | "stop" | "stop_limit",
    "time_in_force": "day" | "gtc" | "ioc" | "fok"
}
```

**Symbol Format:** Standard US tickers (e.g., "AAPL", "TSLA")

**Environment Variables:**
```bash
ALPACA_API_KEY=your_api_key
ALPACA_SECRET_KEY=your_secret_key
```

---

### **2. Oanda** (REST API v3)

**Features:**
- Forex and CFD trading
- Demo and live accounts
- TP/SL on fill support
- Multiple currency pairs

**Configuration:**
```python
{
    "account_type": "demo" | "live",
    "api_token": "your_personal_access_token",
    "account_id": "101-004-12345678-001"
}
```

**Symbol Format:** Underscore-separated pairs (e.g., "EUR_USD", "GBP_USD")
- Automatically converted from slash format if provided

**Environment Variables:**
```bash
OANDA_API_TOKEN=your_personal_access_token
OANDA_ACCOUNT_ID=your_account_id
```

**Special Notes:**
- Uses units (positive for buy, negative for sell)
- Supports fractional units
- Separate long/short position tracking

---

### **3. Tradier** (REST API)

**Features:**
- US stocks and options
- Sandbox and live accounts
- Clean REST API
- Real-time quotes

**Configuration:**
```python
{
    "account_type": "sandbox" | "live",
    "api_token": "your_access_token",
    "account_id": "your_account_id",
    "order_type": "market" | "limit" | "stop" | "stop_limit",
    "time_in_force": "day" | "gtc" | "ioc" | "fok"
}
```

**Symbol Format:** Standard US tickers (e.g., "AAPL", "SPY")

**Environment Variables:**
```bash
TRADIER_API_TOKEN=your_access_token
TRADIER_ACCOUNT_ID=your_account_id
```

**Special Notes:**
- Supports OCO (One-Cancels-Other) orders
- Bracket order = main order + separate TP/SL orders

---

## Usage Examples

### **Creating a Broker Service**

```python
from app.services.brokers.factory import broker_factory

# Via factory
alpaca = broker_factory.create(
    broker_type="alpaca",
    api_key="your_key",
    secret_key="your_secret",
    paper=True
)

oanda = broker_factory.create(
    broker_type="oanda",
    api_key="your_token",
    account_id="your_account",
    paper=True
)

tradier = broker_factory.create(
    broker_type="tradier",
    api_key="your_token",
    account_id="your_account",
    paper=True
)
```

### **From Tool Configuration**

```python
from app.services.brokers.factory import broker_factory

tool_config = {
    "tool_type": "alpaca_broker",
    "config": {
        "api_key": "your_key",
        "secret_key": "your_secret",
        "account_type": "paper"
    }
}

broker = broker_factory.from_tool_config(tool_config)
```

### **Executing Trades**

```python
from app.services.brokers.base import OrderSide, OrderType

# Market order
order = broker.place_order(
    symbol="AAPL",
    qty=100,
    side=OrderSide.BUY,
    order_type=OrderType.MARKET
)

# Bracket order (with TP/SL)
order = broker.place_bracket_order(
    symbol="AAPL",
    qty=100,
    side=OrderSide.BUY,
    take_profit_price=185.00,
    stop_loss_price=175.00
)
```

### **Checking Positions**

```python
# Get all positions
positions = broker.get_positions()

for pos in positions:
    print(f"{pos.symbol}: {pos.qty} @ ${pos.avg_entry_price}")
    print(f"  P&L: ${pos.unrealized_pl} ({pos.unrealized_pl_percent:.2f}%)")

# Check specific position
position = broker.get_position("AAPL")
if position:
    print(f"Have position: {position.qty} shares")
else:
    print("No position")
```

### **Closing Positions**

```python
# Close entire position
result = broker.close_position("AAPL")

# Close partial position
result = broker.close_position("AAPL", qty=50)
```

---

## Trade Manager Integration

The **Trade Manager Agent** now uses real broker APIs:

### **Duplicate Position Detection**
```python
def _has_duplicate_position(self, state, broker_tool) -> bool:
    broker = broker_factory.from_tool_config(broker_tool)
    position = broker.get_position(state.symbol)
    return position is not None
```

### **Real Trade Execution**
```python
def _execute_broker_trade(self, state, strategy, risk, broker_tool):
    broker = broker_factory.from_tool_config(broker_tool)
    
    # Place bracket order
    order = broker.place_bracket_order(
        symbol=state.symbol,
        qty=risk.position_size,
        side=OrderSide.BUY if strategy.action == "BUY" else OrderSide.SELL,
        take_profit_price=take_profit,
        stop_loss_price=stop_loss
    )
    
    # Store in state
    state.trade_execution = TradeExecution(
        order_id=order.order_id,
        status=order.status.value,
        filled_price=order.filled_price,
        ...
    )
```

### **Position Monitoring**
```python
def _get_position(self, symbol, broker_tool) -> Optional[Dict]:
    broker = broker_factory.from_tool_config(broker_tool)
    position = broker.get_position(symbol)
    
    if position:
        return {
            "symbol": position.symbol,
            "qty": position.qty,
            "unrealized_pl": position.unrealized_pl,
            "unrealized_pl_percent": position.unrealized_pl_percent,
            ...
        }
    return None
```

---

## Testing

### **Connection Tests**

Each broker service has a `test_connection()` method:

```python
# Test Alpaca
result = alpaca.test_connection()
# {'status': 'connected', 'message': 'Alpaca API connection successful', ...}

# Test Oanda
result = oanda.test_connection()
# {'status': 'connected', 'accounts_count': 1, 'paper_trading': True}

# Test Tradier
result = tradier.test_connection()
# {'status': 'connected', 'profile': {...}, 'paper_trading': True}
```

### **Paper Trading**

All brokers support paper/demo accounts for safe testing:

```python
# Alpaca paper trading
alpaca = broker_factory.create("alpaca", api_key=..., paper=True)

# Oanda demo account
oanda = broker_factory.create("oanda", api_key=..., paper=True)

# Tradier sandbox
tradier = broker_factory.create("tradier", api_key=..., paper=True)
```

---

## Configuration

### **Environment Variables** (`.env`)

```bash
# Alpaca
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret

# Oanda
OANDA_API_TOKEN=your_oanda_token
OANDA_ACCOUNT_ID=your_oanda_account

# Tradier
TRADIER_API_TOKEN=your_tradier_token
TRADIER_ACCOUNT_ID=your_tradier_account
```

### **Tool Configuration** (UI)

When attaching a broker tool to the Trade Manager Agent:

1. Select broker: "Alpaca Broker" | "Oanda Broker" | "Tradier Broker"
2. Configure account type: Paper/Demo or Live
3. Provide credentials (or use environment variables)
4. Set order preferences (order type, time in force)

---

## Dependencies

Added to `requirements.txt`:

```python
# Broker APIs
alpaca-py>=0.43.0  # Alpaca Trading API
requests>=2.31.0   # For Oanda and Tradier REST APIs
```

---

## Files Created/Modified

### **New Files:**

**Broker Services:**
- `backend/app/services/brokers/__init__.py`
- `backend/app/services/brokers/base.py` (Abstract base class)
- `backend/app/services/brokers/alpaca_service.py` (Real Alpaca API)
- `backend/app/services/brokers/oanda_service.py` (Real Oanda API)
- `backend/app/services/brokers/tradier_service.py` (Real Tradier API)
- `backend/app/services/brokers/factory.py` (Broker factory)

**Broker Tools:**
- `backend/app/tools/oanda_broker.py` (NEW)
- `backend/app/tools/tradier_broker.py` (NEW)

### **Modified Files:**

- `backend/app/agents/trade_manager_agent.py` - Uses real broker APIs
- `backend/app/tools/__init__.py` - Registered new broker tools
- `backend/requirements.txt` - Added `requests` dependency
- `docs/BROKER_INTEGRATION.md` - This file

---

## Benefits

✅ **Unified Interface** - One API for all brokers
✅ **Real Trading** - Actual broker integration, not simulations
✅ **Paper Trading** - Safe testing with demo accounts
✅ **Position Monitoring** - Real-time position status from brokers
✅ **Duplicate Prevention** - Checks broker before each trade
✅ **Multi-Asset Support** - Stocks, options, crypto, forex
✅ **Extensible** - Easy to add more brokers
✅ **Type-Safe** - Pydantic models with validation
✅ **Well-Tested** - Based on tested sample code from project root

---

## Future Enhancements

1. **Interactive Brokers** - Add IB integration
2. **Crypto Exchanges** - Coinbase, Binance, Kraken
3. **Options Strategies** - Multi-leg option orders
4. **Portfolio Rebalancing** - Automatic position sizing
5. **Risk Limits** - Per-broker risk checks
6. **Audit Trail** - Store all broker responses
7. **WebSocket Streaming** - Real-time position updates
8. **Commission Tracking** - Actual cost from broker APIs

---

## Summary

**This implementation provides:**

- **Production-ready** broker integrations for Alpaca, Oanda, and Tradier
- **Unified abstraction layer** for easy multi-broker support
- **Real API calls** replacing mock simulations
- **Position-aware trading** preventing duplicates
- **Seamless agent integration** with Trade Manager
- **Extensible architecture** for adding more brokers

**The system can now execute real trades, monitor positions, and manage risk across multiple brokers and asset classes!** 🚀

