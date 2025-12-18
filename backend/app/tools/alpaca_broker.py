"""
Alpaca Broker Tool

Executes trades via Alpaca API.
"""
from typing import Any, Dict, Optional
import structlog

from app.tools.base import BaseTool, ToolError
from app.schemas.tool import ToolMetadata, ToolConfigSchema
from app.config import settings


logger = structlog.get_logger()


class AlpacaBrokerTool(BaseTool):
    """
    Tool for executing trades via Alpaca brokerage API.
    
    Supports both live and paper trading accounts.
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            tool_type="alpaca_broker",
            name="Alpaca Broker",
            description="Execute trades via Alpaca API (stocks, options, crypto)",
            category="broker",
            version="1.0.0",
            icon="account_balance",
            requires_credentials=True,
            config_schema=ToolConfigSchema(
                type="object",
                title="Alpaca Broker Configuration",
                description="Configure Alpaca API connection",
                properties={
                    "account_type": {
                        "type": "string",
                        "title": "Account Type",
                        "description": "Use paper (testing) or live trading account",
                        "enum": ["Paper", "Live"],
                        "default": "Paper"
                    },
                    "api_key": {
                        "type": "string",
                        "title": "API Key",
                        "description": "Alpaca API key (required)"
                    },
                    "secret_key": {
                        "type": "string",
                        "title": "Secret Key",
                        "description": "Alpaca secret key (required)"
                    }
                },
                required=["account_type", "api_key", "secret_key"]
            )
        )
    
    def _validate_config(self):
        """Validate Alpaca configuration."""
        account_type = self.config.get("account_type", "Paper")
        if account_type not in ["Paper", "Live"]:
            raise ValueError("account_type must be 'Paper' or 'Live'")
        
        if not self.config.get("api_key"):
            raise ValueError("api_key is required")
        
        if not self.config.get("secret_key"):
            raise ValueError("secret_key is required")
    
    def execute(self, action: str, symbol: str, quantity: float, **kwargs) -> Dict[str, Any]:
        """
        Execute a trade order.
        
        Args:
            action: "buy" or "sell"
            symbol: Trading symbol (e.g., "AAPL")
            quantity: Number of shares/units
            **kwargs: Additional order parameters (limit_price, stop_price, etc.)
            
        Returns:
            Dict with order details
            
        Raises:
            ToolError: If order execution fails
        """
        try:
            account_type = self.config.get("account_type", "paper")
            order_type = self.config.get("order_type", "market")
            time_in_force = self.config.get("time_in_force", "day")
            
            logger.info(
                "alpaca_order_request",
                action=action,
                symbol=symbol,
                quantity=quantity,
                order_type=order_type,
                account_type=account_type
            )
            
            # Mock execution for now (replace with actual Alpaca API call)
            # In production, you would use alpaca-py library:
            # from alpaca.trading.client import TradingClient
            # from alpaca.trading.requests import MarketOrderRequest
            # from alpaca.trading.enums import OrderSide, TimeInForce
            
            # For now, return mock success response
            return {
                "success": True,
                "order_id": "mock_order_123",
                "symbol": symbol,
                "qty": quantity,
                "side": action,
                "order_type": order_type,
                "time_in_force": time_in_force,
                "status": "accepted" if account_type == "paper" else "submitted",
                "account_type": account_type,
                "message": f"{action.upper()} order for {quantity} shares of {symbol} submitted successfully"
            }
            
        except Exception as e:
            logger.error("alpaca_order_failed", error=str(e), exc_info=True)
            raise ToolError(f"Alpaca order execution failed: {e}")
    
    def get_account_info(self) -> Dict[str, Any]:
        """
        Get account information.
        
        Returns:
            Dict with account details (cash, buying_power, positions, etc.)
        """
        # Mock account info
        return {
            "account_type": self.config.get("account_type", "paper"),
            "cash": 100000.00,
            "buying_power": 100000.00,
            "portfolio_value": 100000.00,
            "currency": "USD"
        }

