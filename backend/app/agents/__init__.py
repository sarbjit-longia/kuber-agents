"""
Agents Package

This package contains all agent implementations and the agent registry.
"""
from app.agents.registry import registry, get_registry
from app.agents.base import BaseAgent, AgentError, InsufficientDataError, TriggerNotMetException
from app.agents.market_data_agent import MarketDataAgent
from app.agents.bias_agent import BiasAgent
from app.agents.strategy_agent import StrategyAgent
from app.agents.risk_manager_agent import RiskManagerAgent
from app.agents.trade_manager_agent import TradeManagerAgent

# Register all agents
registry.register(MarketDataAgent)
registry.register(BiasAgent)
registry.register(StrategyAgent)
registry.register(RiskManagerAgent)
registry.register(TradeManagerAgent)

__all__ = [
    "registry",
    "get_registry",
    "BaseAgent",
    "AgentError",
    "InsufficientDataError",
    "TriggerNotMetException",
    "MarketDataAgent",
    "BiasAgent",
    "StrategyAgent",
    "RiskManagerAgent",
    "TradeManagerAgent",
]
