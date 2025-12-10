"""
Signal API Endpoints

Endpoints for signal metadata and recent signals.
"""
from typing import List, Dict, Any
from fastapi import APIRouter

from app.schemas.signal import SignalType as SignalTypeEnum

router = APIRouter()


@router.get("/signals/types")
async def get_available_signal_types() -> List[Dict[str, Any]]:
    """
    Get all available signal generator types.
    
    This endpoint returns metadata about available signal generators
    that users can subscribe to in their pipelines.
    
    Returns:
        List of signal type metadata
    """
    return [
        {
            "signal_type": SignalTypeEnum.MOCK.value,
            "name": "Mock Signal (Testing)",
            "description": "Random test signals for development and testing",
            "generator": "mock_generator",
            "is_free": True,
            "typical_frequency": "~1 signal per minute",
            "requires_confidence_filter": False,
            "default_confidence": None,
            "icon": "bug_report",
            "category": "testing"
        },
        {
            "signal_type": SignalTypeEnum.GOLDEN_CROSS.value,
            "name": "Golden Cross",
            "description": "Detects when 50-day SMA crosses above 200-day SMA (bullish signal)",
            "generator": "golden_cross_generator",
            "is_free": True,
            "typical_frequency": "Rare (days to weeks per ticker)",
            "requires_confidence_filter": True,
            "default_confidence": 85,
            "icon": "trending_up",
            "category": "technical"
        },
        # Future signal types will be added here:
        # {
        #     "signal_type": "news_sentiment",
        #     "name": "News Sentiment",
        #     "description": "Financial news sentiment analysis",
        #     "generator": "news_sentiment_generator",
        #     "is_free": False,
        #     "typical_frequency": "Multiple per day",
        #     "requires_confidence_filter": True,
        #     "default_confidence": 70,
        #     "icon": "article",
        #     "category": "fundamental"
        # },
        # {
        #     "signal_type": "rsi_oversold",
        #     "name": "RSI Oversold",
        #     "description": "RSI below 30 (oversold condition)",
        #     "generator": "rsi_generator",
        #     "is_free": True,
        #     "typical_frequency": "Multiple per week",
        #     "requires_confidence_filter": False,
        #     "default_confidence": None,
        #     "icon": "show_chart",
        #     "category": "technical"
        # }
    ]

