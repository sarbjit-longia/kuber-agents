"""
Signal Bucket Definitions

Defines which signals are available in each subscription tier.
"""
from typing import List, Dict
from app.models.user import SubscriptionTier


# Signal bucket definitions
SIGNAL_BUCKETS: Dict[SubscriptionTier, List[str]] = {
    SubscriptionTier.FREE: [
        "external",  # External webhooks, TrendSpider, etc.
    ],
    
    SubscriptionTier.BASIC: [
        "external",
        "golden_cross",      # 50/200 SMA crossover
        "death_cross",       # 50/200 SMA crossover (bearish)
        "rsi_overbought",    # RSI > 70
        "rsi_oversold",      # RSI < 30
        "macd_crossover",    # MACD line crosses signal line
        "volume_spike",      # Volume > 2x average
    ],
    
    SubscriptionTier.PRO: [
        # Includes all BASIC signals
        "external",
        "golden_cross",
        "death_cross",
        "rsi_overbought",
        "rsi_oversold",
        "macd_crossover",
        "volume_spike",
        # Plus PRO signals
        "news_sentiment",    # AI-powered news sentiment
        "volatility_breakout", # Volatility spike
        "support_resistance", # Price touches S/R level
        "sector_rotation",   # Sector momentum shift
    ],
    
    SubscriptionTier.ENTERPRISE: [
        # All signals including enterprise-only
        "external",
        "golden_cross",
        "death_cross",
        "rsi_overbought",
        "rsi_oversold",
        "macd_crossover",
        "volume_spike",
        "news_sentiment",
        "volatility_breakout",
        "support_resistance",
        "sector_rotation",
        # Enterprise-only signals
        "dark_pool",         # Unusual dark pool activity
        "options_flow",      # Large options orders
        "insider_trading",   # Insider buying/selling
        "custom_ai",         # Custom AI signal
    ],
}


# Pipeline limits per tier
PIPELINE_LIMITS: Dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 2,
    SubscriptionTier.BASIC: 5,
    SubscriptionTier.PRO: 20,
    SubscriptionTier.ENTERPRISE: 999999,  # Effectively unlimited
}


# External signal rate limits (per day)
EXTERNAL_SIGNAL_LIMITS: Dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 100,
    SubscriptionTier.BASIC: 500,
    SubscriptionTier.PRO: 2000,
    SubscriptionTier.ENTERPRISE: 999999,  # Effectively unlimited
}


def get_available_signals(tier: SubscriptionTier) -> List[str]:
    """
    Get list of available signal types for a subscription tier.
    
    Args:
        tier: User's subscription tier
        
    Returns:
        List of signal type identifiers
    """
    return SIGNAL_BUCKETS.get(tier, SIGNAL_BUCKETS[SubscriptionTier.FREE])


def get_pipeline_limit(tier: SubscriptionTier) -> int:
    """
    Get maximum active pipelines for a subscription tier.
    
    Args:
        tier: User's subscription tier
        
    Returns:
        Maximum number of active pipelines
    """
    return PIPELINE_LIMITS.get(tier, PIPELINE_LIMITS[SubscriptionTier.FREE])


def get_external_signal_limit(tier: SubscriptionTier) -> int:
    """
    Get daily external signal trigger limit for a subscription tier.
    
    Args:
        tier: User's subscription tier
        
    Returns:
        Maximum external signal triggers per day
    """
    return EXTERNAL_SIGNAL_LIMITS.get(tier, EXTERNAL_SIGNAL_LIMITS[SubscriptionTier.FREE])


def has_signal_access(tier: SubscriptionTier, signal_type: str) -> bool:
    """
    Check if a user's tier has access to a specific signal type.
    
    Args:
        tier: User's subscription tier
        signal_type: Signal type to check
        
    Returns:
        True if user has access, False otherwise
    """
    available_signals = get_available_signals(tier)
    return signal_type in available_signals

