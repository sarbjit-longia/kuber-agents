"""
Tradier Broker Tool

Executes US stock and options trades via Tradier API.
"""
from typing import Any, Dict, Optional
import structlog

from app.tools.base import BaseTool, ToolError
from app.schemas.tool import ToolMetadata, ToolConfigSchema
from app.config import settings


logger = structlog.get_logger()


class TradierBrokerTool(BaseTool):
    """
    Tool for executing trades via Tradier brokerage API.
    
    Supports both sandbox and live trading accounts.
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            tool_type="tradier_broker",
            name="Tradier Broker",
            description="Execute US stock and options trades via Tradier API",
            category="broker",
            version="1.0.0",
            icon="account_balance_wallet",
            requires_credentials=True,
            config_schema=ToolConfigSchema(
                type="object",
                title="Tradier Broker Configuration",
                description="Configure Tradier API connection",
                properties={
                    "account_type": {
                        "type": "string",
                        "title": "Account Type",
                        "description": "Use sandbox or live trading account",
                        "enum": ["Sandbox", "Live"],
                        "default": "Sandbox"
                    },
                    "api_token": {
                        "type": "string",
                        "title": "API Token",
                        "description": "Tradier API access token (required)"
                    },
                    "account_id": {
                        "type": "string",
                        "title": "Account ID",
                        "description": "Tradier account ID (required)"
                    }
                },
                required=["account_type", "api_token", "account_id"]
            )
        )
    
    def _validate_config(self):
        """Validate Tradier configuration."""
        account_type = self.config.get("account_type", "Sandbox")
        if account_type not in ["Sandbox", "Live"]:
            raise ValueError("account_type must be 'Sandbox' or 'Live'")
        
        if not self.config.get("api_token"):
            raise ValueError("api_token is required")
        
        if not self.config.get("account_id"):
            raise ValueError("account_id is required")
    
    def execute(self, action: str, symbol: str, quantity: float, **kwargs) -> Dict[str, Any]:
        """
        Execute a stock trade order.
        
        Args:
            action: "buy" or "sell"
            symbol: Stock symbol (e.g., "AAPL", "TSLA")
            quantity: Number of shares
            **kwargs: Additional order parameters (limit_price, stop_price, etc.)
            
        Returns:
            Dict with order details
            
        Raises:
            ToolError: If order execution fails
        """
        try:
            from app.services.brokers.factory import broker_factory
            from app.services.brokers.base import OrderSide, OrderType
            
            # Get credentials
            if self.config.get("use_env_credentials", True):
                api_token = getattr(settings, "TRADIER_API_TOKEN", None)
                account_id = getattr(settings, "TRADIER_ACCOUNT_ID", None)
            else:
                api_token = self.config.get("api_token")
                account_id = self.config.get("account_id")
            
            if not api_token:
                raise ToolError("Tradier API token not configured")
            
            # Create broker service
            account_type = self.config.get("account_type", "sandbox")
            paper = account_type == "sandbox"
            
            broker = broker_factory.create(
                broker_type="tradier",
                api_key=api_token,
                account_id=account_id,
                paper=paper
            )
            
            # Convert action to OrderSide
            side = OrderSide.BUY if action.lower() == "buy" else OrderSide.SELL
            
            # Get order type
            order_type_str = self.config.get("order_type", "market")
            order_type = {
                "market": OrderType.MARKET,
                "limit": OrderType.LIMIT,
                "stop": OrderType.STOP,
                "stop_limit": OrderType.STOP_LIMIT
            }.get(order_type_str, OrderType.MARKET)
            
            # Execute order
            logger.info(
                "tradier_order_request",
                action=action,
                symbol=symbol,
                quantity=quantity,
                order_type=order_type_str,
                account_type=account_type
            )
            
            order = broker.place_order(
                symbol=symbol,
                qty=quantity,
                side=side,
                order_type=order_type,
                limit_price=kwargs.get("limit_price"),
                stop_price=kwargs.get("stop_price")
            )
            
            return {
                "success": True,
                "order_id": order.order_id,
                "symbol": order.symbol,
                "qty": order.qty,
                "side": order.side.value,
                "order_type": order.type.value,
                "status": order.status.value,
                "filled_price": order.filled_price,
                "account_type": account_type,
                "message": f"{action.upper()} order for {quantity} shares of {symbol} executed successfully"
            }
            
        except Exception as e:
            logger.error("tradier_order_failed", error=str(e), exc_info=True)
            raise ToolError(f"Tradier order execution failed: {e}")
    
    def get_account_info(self) -> Dict[str, Any]:
        """
        Get account information.
        
        Returns:
            Dict with account details
        """
        try:
            from app.services.brokers.factory import broker_factory
            
            # Get credentials
            if self.config.get("use_env_credentials", True):
                api_token = getattr(settings, "TRADIER_API_TOKEN", None)
                account_id = getattr(settings, "TRADIER_ACCOUNT_ID", None)
            else:
                api_token = self.config.get("api_token")
                account_id = self.config.get("account_id")
            
            if not api_token:
                return {"error": "Tradier API token not configured"}
            
            # Create broker service
            account_type = self.config.get("account_type", "sandbox")
            paper = account_type == "sandbox"
            
            broker = broker_factory.create(
                broker_type="tradier",
                api_key=api_token,
                account_id=account_id,
                paper=paper
            )
            
            return broker.get_account_info()
            
        except Exception as e:
            logger.error("tradier_account_info_failed", error=str(e))
            return {"error": str(e)}

