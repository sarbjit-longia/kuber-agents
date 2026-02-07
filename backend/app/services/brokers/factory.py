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
    
    # Tool type to broker type mapping (for UI integration)
    TOOL_TYPE_MAP = {
        "alpaca_broker": "alpaca",
        "oanda_broker": "oanda",
        "tradier_broker": "tradier",
    }
    
    @classmethod
    def get_supported_tool_types(cls) -> set:
        """
        Get all supported broker tool types.
        
        Returns:
            Set of tool type strings (e.g., {"alpaca_broker", "oanda_broker", "tradier_broker"})
        """
        return set(cls.TOOL_TYPE_MAP.keys())
    
    @classmethod
    def is_broker_tool(cls, tool_type: str) -> bool:
        """
        Check if a tool_type is a broker tool.
        
        Args:
            tool_type: Tool type string
            
        Returns:
            True if tool_type is a broker, False otherwise
        """
        return tool_type in cls.TOOL_TYPE_MAP
    
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
        
        # Use centralized mapping
        broker_type = cls.TOOL_TYPE_MAP.get(tool_type)
        if not broker_type:
            raise ValueError(f"Unknown broker tool type: {tool_type}")
        
        # Extract credentials - different brokers use different field names
        config = tool_config.get("config", {})
        
        # 🐛 FIX: Handle different field names for different brokers
        # Alpaca: api_key + secret_key
        # OANDA: api_token + account_id
        # Tradier: api_token + account_id
        if broker_type == "oanda" or broker_type == "tradier":
            api_key = config.get("api_token")  # OANDA/Tradier use "api_token"
        else:
            api_key = config.get("api_key")  # Alpaca uses "api_key"
        
        secret_key = config.get("secret_key")
        account_id = config.get("account_id")
        
        # Debug logging to help troubleshoot config issues
        logger.info(
            "broker_config_extracted",
            broker_type=broker_type,
            has_api_key=bool(api_key),
            has_account_id=bool(account_id),
            account_type=config.get("account_type"),
            config_keys=list(config.keys())
        )
        
        # Determine if paper trading
        account_type = config.get("account_type", "paper")
        paper = account_type == "paper" or config.get("use_paper", True)
        
        if not api_key:
            raise ValueError(
                f"API key not found in tool config for {broker_type}. "
                f"Check that 'api_token' (for OANDA/Tradier) or 'api_key' (for Alpaca) is configured in the tool. "
                f"Available config keys: {list(config.keys())}"
            )
        
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

