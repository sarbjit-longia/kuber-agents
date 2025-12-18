"""
Tools Package

This package contains all tool implementations that agents can use.
"""
from app.tools.base import BaseTool, ToolError
from app.tools.market_data import MarketDataTool, MockMarketDataTool
from app.tools.registry import ToolRegistry, get_registry, register_tool
from app.tools.alpaca_broker import AlpacaBrokerTool
from app.tools.oanda_broker import OandaBrokerTool
from app.tools.tradier_broker import TradierBrokerTool
from app.tools.webhook_notifier import WebhookNotifierTool
from app.tools.email_notifier import EmailNotifierTool

# Register all tools
def _initialize_registry():
    """Initialize the tool registry with all available tools."""
    registry = get_registry()
    
    # Register market data tools
    registry.register(MarketDataTool)
    registry.register(MockMarketDataTool)  # Mock for testing/development
    
    # Register broker tools
    registry.register(AlpacaBrokerTool)
    registry.register(OandaBrokerTool)
    registry.register(TradierBrokerTool)
    
    # Register notifier tools
    registry.register(WebhookNotifierTool)
    registry.register(EmailNotifierTool)

# Initialize registry on import
_initialize_registry()

__all__ = [
    "BaseTool",
    "ToolError",
    "MarketDataTool",
    "MockMarketDataTool",
    "ToolRegistry",
    "get_registry",
    "register_tool",
    "AlpacaBrokerTool",
    "OandaBrokerTool",
    "TradierBrokerTool",
    "WebhookNotifierTool",
    "EmailNotifierTool",
]
