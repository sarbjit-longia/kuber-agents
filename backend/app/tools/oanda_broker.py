"""
Oanda Broker Tool

Executes forex and CFD trades via Oanda API.
"""
from typing import Any, Dict, Optional
import structlog

from app.tools.base import BaseTool, ToolError
from app.schemas.tool import ToolMetadata, ToolConfigSchema
from app.config import settings


logger = structlog.get_logger()


class OandaBrokerTool(BaseTool):
    """
    Tool for executing forex trades via Oanda brokerage API.
    
    Supports both demo and live trading accounts.
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            tool_type="oanda_broker",
            name="Oanda Broker",
            description="Execute forex and CFD trades via Oanda API",
            category="broker",
            version="1.0.0",
            icon="currency_exchange",
            requires_credentials=True,
            config_schema=ToolConfigSchema(
                type="object",
                title="Oanda Broker Configuration",
                description="Configure Oanda API connection",
                properties={
                    "account_type": {
                        "type": "string",
                        "title": "Account Type",
                        "description": "Use practice (demo) or live trading account",
                        "enum": ["Practice", "Live"],
                        "default": "Practice"
                    },
                    "api_token": {
                        "type": "string",
                        "title": "API Token",
                        "description": "Oanda personal access token (required)"
                    },
                    "account_id": {
                        "type": "string",
                        "title": "Account ID",
                        "description": "Oanda account ID (e.g., 101-004-12345678-001) (required)"
                    }
                },
                required=["account_type", "api_token", "account_id"]
            )
        )
    
    def _validate_config(self):
        """Validate Oanda configuration."""
        account_type = self.config.get("account_type", "Practice")
        if account_type not in ["Practice", "Live"]:
            raise ValueError("account_type must be 'Practice' or 'Live'")
        
        if not self.config.get("api_token"):
            raise ValueError("api_token is required")
        
        if not self.config.get("account_id"):
            raise ValueError("account_id is required")
    
    def execute(self, action: str, symbol: str, quantity: float, **kwargs) -> Dict[str, Any]:
        """
        Execute a forex trade order.
        
        Args:
            action: "buy" or "sell"
            symbol: Instrument (e.g., "EUR_USD", "GBP/USD")
            quantity: Number of units
            **kwargs: Additional order parameters (take_profit, stop_loss, etc.)
            
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
                api_token = getattr(settings, "OANDA_API_TOKEN", None)
                account_id = getattr(settings, "OANDA_ACCOUNT_ID", None)
            else:
                api_token = self.config.get("api_token")
                account_id = self.config.get("account_id")
            
            if not api_token:
                raise ToolError("Oanda API token not configured")
            
            # Create broker service
            account_type = self.config.get("account_type", "demo")
            paper = account_type == "demo"
            
            broker = broker_factory.create(
                broker_type="oanda",
                api_key=api_token,
                account_id=account_id,
                paper=paper
            )
            
            # Convert action to OrderSide
            side = OrderSide.BUY if action.lower() == "buy" else OrderSide.SELL
            
            # Execute order
            logger.info(
                "oanda_order_request",
                action=action,
                symbol=symbol,
                quantity=quantity,
                account_type=account_type
            )
            
            order = broker.place_order(
                symbol=symbol,
                qty=quantity,
                side=side,
                order_type=OrderType.MARKET
            )
            
            return {
                "success": True,
                "order_id": order.order_id,
                "symbol": order.symbol,
                "qty": order.qty,
                "side": order.side.value,
                "status": order.status.value,
                "filled_price": order.filled_price,
                "account_type": account_type,
                "message": f"{action.upper()} order for {quantity} units of {symbol} executed successfully"
            }
            
        except Exception as e:
            logger.error("oanda_order_failed", error=str(e), exc_info=True)
            raise ToolError(f"Oanda order execution failed: {e}")
    
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
                api_token = getattr(settings, "OANDA_API_TOKEN", None)
                account_id = getattr(settings, "OANDA_ACCOUNT_ID", None)
            else:
                api_token = self.config.get("api_token")
                account_id = self.config.get("account_id")
            
            if not api_token:
                return {"error": "Oanda API token not configured"}
            
            # Create broker service
            account_type = self.config.get("account_type", "demo")
            paper = account_type == "demo"
            
            broker = broker_factory.create(
                broker_type="oanda",
                api_key=api_token,
                account_id=account_id,
                paper=paper
            )
            
            return broker.get_account_info()
            
        except Exception as e:
            logger.error("oanda_account_info_failed", error=str(e))
            return {"error": str(e)}

