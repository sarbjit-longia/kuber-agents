"""
Broker Factory

Creates broker service instances based on configuration.
Similar to market data provider factory pattern.
"""
from typing import Dict, Any, Optional
import structlog

from app.services.brokers.base import BrokerService
from app.services.brokers.alpaca_service import AlpacaBrokerService
from app.services.brokers.oanda_service import OandaBrokerService
from app.services.brokers.tradier_service import TradierBrokerService

logger = structlog.get_logger()


class BrokerFactory:
    """
    Factory for creating broker service instances.
    
    Supports:
    - Alpaca (stocks, options, crypto)
    - Oanda (forex)
    - Tradier (stocks, options)
    """
    
    _brokers: Dict[str, type] = {
        "alpaca": AlpacaBrokerService,
        "oanda": OandaBrokerService,
        "tradier": TradierBrokerService,
    }
    
    @classmethod
    def create(
        cls,
        broker_type: str,
        api_key: str,
        secret_key: Optional[str] = None,
        account_id: Optional[str] = None,
        paper: bool = True,
        **kwargs
    ) -> BrokerService:
        """
        Create a broker service instance.
        
        Args:
            broker_type: Type of broker ("alpaca", "oanda", "tradier")
            api_key: API key/token
            secret_key: Secret key (if applicable)
            account_id: Account ID (if applicable)
            paper: Whether to use paper/demo trading
            **kwargs: Additional broker-specific parameters
            
        Returns:
            BrokerService instance
            
        Raises:
            ValueError: If broker type is not supported
        """
        broker_type_lower = broker_type.lower()
        
        if broker_type_lower not in cls._brokers:
            raise ValueError(
                f"Unsupported broker type: {broker_type}. "
                f"Supported types: {', '.join(cls._brokers.keys())}"
            )
        
        broker_class = cls._brokers[broker_type_lower]
        
        logger.info(
            "creating_broker_service",
            broker_type=broker_type,
            paper=paper,
            account_id=account_id
        )
        
        return broker_class(
            api_key=api_key,
            secret_key=secret_key,
            account_id=account_id,
            paper=paper
        )
    
    @classmethod
    def from_tool_config(cls, tool_config: Dict[str, Any]) -> BrokerService:
        """
        Create broker service from tool configuration.
        
        Args:
            tool_config: Tool configuration dict with broker settings
            
        Returns:
            BrokerService instance
        """
        # Determine broker type from tool_type
        tool_type = tool_config.get("tool_type", "")
        
        # Map tool types to broker types
        broker_map = {
            "alpaca_broker": "alpaca",
            "oanda_broker": "oanda",
            "tradier_broker": "tradier",
        }
        
        broker_type = broker_map.get(tool_type)
        if not broker_type:
            raise ValueError(f"Unknown broker tool type: {tool_type}")
        
        # Extract credentials
        config = tool_config.get("config", {})
        api_key = config.get("api_key")
        secret_key = config.get("secret_key")
        account_id = config.get("account_id")
        
        # Determine if paper trading
        account_type = config.get("account_type", "paper")
        paper = account_type == "paper" or config.get("use_paper", True)
        
        if not api_key:
            raise ValueError(f"API key not found in tool config for {broker_type}")
        
        return cls.create(
            broker_type=broker_type,
            api_key=api_key,
            secret_key=secret_key,
            account_id=account_id,
            paper=paper
        )
    
    @classmethod
    def list_supported_brokers(cls) -> Dict[str, Dict[str, Any]]:
        """
        List all supported brokers with their capabilities.
        
        Returns:
            Dict of broker info
        """
        return {
            "alpaca": {
                "name": "Alpaca",
                "description": "US stocks, options, and crypto trading",
                "requires_secret_key": True,
                "supports_paper_trading": True,
                "asset_classes": ["stocks", "options", "crypto"]
            },
            "oanda": {
                "name": "Oanda",
                "description": "Forex and CFD trading",
                "requires_secret_key": False,
                "supports_paper_trading": True,
                "asset_classes": ["forex", "cfd"]
            },
            "tradier": {
                "name": "Tradier",
                "description": "US stocks and options trading",
                "requires_secret_key": False,
                "supports_paper_trading": True,
                "asset_classes": ["stocks", "options"]
            }
        }


# Singleton instance for easy access
broker_factory = BrokerFactory()

