"""
Strategy Tools Registry - Defines all available strategy tools for LLM function calling

This registry is SEPARATE from the existing tool registry and is used specifically
for LLM-powered instruction detection and auto-tool-discovery.
"""
from typing import Dict, Any


# Strategy Tool Registry with OpenAI function calling format
STRATEGY_TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    
    # ==================== ICT Tools ====================
    
    "fvg_detector": {
        "type": "function",
        "function": {
            "name": "fvg_detector",
            "description": "Detects Fair Value Gaps (FVG) in price action. A Fair Value Gap is a 3-candle pattern where the current candle's low is higher than the previous candle's high (bullish FVG) or vice versa (bearish FVG). Returns gap location, size, and filled/unfilled status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeframe": {
                        "type": "string",
                        "enum": ["5m", "15m", "1h", "4h", "D"],
                        "description": "Timeframe to analyze for FVGs"
                    },
                    "min_gap_pips": {
                        "type": "number",
                        "description": "Minimum gap size in pips to consider valid (default: 10)",
                        "default": 10
                    },
                    "lookback_periods": {
                        "type": "integer",
                        "description": "Number of candles to look back (default: 100)",
                        "default": 100
                    }
                },
                "required": ["timeframe"]
            }
        },
        "pricing": 0.01,  # $0.01 per call
        "category": "ict"
    },
    
    "liquidity_analyzer": {
        "type": "function",
        "function": {
            "name": "liquidity_analyzer",
            "description": "Identifies liquidity pools (swing highs/lows where stop losses cluster) and detects when liquidity is grabbed (price sweeps through these levels). Essential for ICT strategies that wait for liquidity grabs before entry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeframe": {
                        "type": "string",
                        "enum": ["1h", "4h", "D"],
                        "description": "Timeframe for liquidity analysis (higher timeframes = more significant liquidity)"
                    },
                    "lookback_periods": {
                        "type": "integer",
                        "description": "Number of candles to look back for swing points (default: 50)",
                        "default": 50
                    },
                    "swing_strength": {
                        "type": "integer",
                        "description": "Number of bars on each side to confirm swing (default: 3)",
                        "default": 3
                    }
                },
                "required": ["timeframe"]
            }
        },
        "pricing": 0.02,
        "category": "ict"
    },
    
    "market_structure": {
        "type": "function",
        "function": {
            "name": "market_structure",
            "description": "Analyzes market structure to identify Break of Structure (BOS) and Change of Character (CHoCH). BOS = price breaks the most recent swing high/low in the direction of trend. CHoCH = price breaks against trend, signaling potential reversal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeframe": {
                        "type": "string",
                        "enum": ["1h", "4h", "D"],
                        "description": "Timeframe for structure analysis"
                    },
                    "lookback_periods": {
                        "type": "integer",
                        "description": "Number of candles to analyze (default: 100)",
                        "default": 100
                    }
                },
                "required": ["timeframe"]
            }
        },
        "pricing": 0.015,
        "category": "ict"
    },
    
    "premium_discount": {
        "type": "function",
        "function": {
            "name": "premium_discount",
            "description": "Calculates premium/discount zones based on daily or weekly range. Premium = price above 50% (expensive, good for selling). Discount = price below 50% (cheap, good for buying). Also identifies Optimal Trade Entry (OTE) zones at 62-79% Fibonacci levels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "range_period": {
                        "type": "string",
                        "enum": ["daily", "weekly", "monthly"],
                        "description": "Period to calculate range from (daily recommended for intraday)"
                    },
                    "include_ote": {
                        "type": "boolean",
                        "description": "Include Optimal Trade Entry zones (62-79% fib) (default: true)",
                        "default": True
                    }
                },
                "required": ["range_period"]
            }
        },
        "pricing": 0.01,
        "category": "ict"
    },
    
    # ==================== Indicator Tools ====================
    
    "rsi": {
        "type": "function",
        "function": {
            "name": "rsi",
            "description": "Relative Strength Index (RSI) momentum indicator. Values above 70 indicate overbought conditions, below 30 indicate oversold. Useful for entry confirmation and divergence detection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeframe": {
                        "type": "string",
                        "enum": ["5m", "15m", "1h", "4h", "D"],
                        "description": "Timeframe for RSI calculation"
                    },
                    "period": {
                        "type": "integer",
                        "description": "RSI period (default: 14)",
                        "default": 14
                    }
                },
                "required": ["timeframe"]
            }
        },
        "pricing": 0.005,  # Cheap - cached from Data Plane
        "category": "indicator"
    },
    
    "sma_crossover": {
        "type": "function",
        "function": {
            "name": "sma_crossover",
            "description": "Simple Moving Average crossover detection. Identifies when fast SMA crosses above (bullish) or below (bearish) slow SMA. Classic trend-following signal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeframe": {
                        "type": "string",
                        "enum": ["5m", "15m", "1h", "4h", "D"],
                        "description": "Timeframe for SMA calculation"
                    },
                    "fast_period": {
                        "type": "integer",
                        "description": "Fast SMA period (default: 20)",
                        "default": 20
                    },
                    "slow_period": {
                        "type": "integer",
                        "description": "Slow SMA period (default: 50)",
                        "default": 50
                    }
                },
                "required": ["timeframe"]
            }
        },
        "pricing": 0.005,
        "category": "indicator"
    },
    
    "macd": {
        "type": "function",
        "function": {
            "name": "macd",
            "description": "Moving Average Convergence Divergence (MACD). Combines trend and momentum. Signal line crossovers indicate potential entries. Histogram shows momentum strength.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeframe": {
                        "type": "string",
                        "enum": ["5m", "15m", "1h", "4h", "D"],
                        "description": "Timeframe for MACD calculation"
                    }
                },
                "required": ["timeframe"]
            }
        },
        "pricing": 0.005,
        "category": "indicator"
    },
    
    "bollinger_bands": {
        "type": "function",
        "function": {
            "name": "bollinger_bands",
            "description": "Bollinger Bands volatility indicator. Price at upper band = overbought, at lower band = oversold. Band width indicates volatility. Useful for mean reversion and breakout strategies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeframe": {
                        "type": "string",
                        "enum": ["5m", "15m", "1h", "4h", "D"],
                        "description": "Timeframe for Bollinger Bands calculation"
                    },
                    "period": {
                        "type": "integer",
                        "description": "BB period (default: 20)",
                        "default": 20
                    },
                    "std_dev": {
                        "type": "number",
                        "description": "Standard deviations (default: 2.0)",
                        "default": 2.0
                    }
                },
                "required": ["timeframe"]
            }
        },
        "pricing": 0.005,
        "category": "indicator"
    },
    
    # ==================== Price Action Tools ====================
    
    "support_resistance": {
        "type": "function",
        "function": {
            "name": "support_resistance",
            "description": "Identifies key support and resistance levels based on historical price action. Detects horizontal levels where price has reversed multiple times.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeframe": {
                        "type": "string",
                        "enum": ["1h", "4h", "D"],
                        "description": "Timeframe for level detection"
                    },
                    "lookback_periods": {
                        "type": "integer",
                        "description": "Number of candles to analyze (default: 200)",
                        "default": 200
                    },
                    "min_touches": {
                        "type": "integer",
                        "description": "Minimum touches to confirm level (default: 2)",
                        "default": 2
                    }
                },
                "required": ["timeframe"]
            }
        },
        "pricing": 0.01,
        "category": "price_action"
    },
}


def get_strategy_tool_by_name(tool_name: str) -> Dict[str, Any]:
    """Get strategy tool definition by name."""
    return STRATEGY_TOOL_REGISTRY.get(tool_name)


def get_strategy_tools_by_category(category: str) -> Dict[str, Dict[str, Any]]:
    """Get all strategy tools in a category (ict, indicator, price_action)."""
    return {
        name: tool
        for name, tool in STRATEGY_TOOL_REGISTRY.items()
        if tool.get("category") == category
    }


def get_all_strategy_tool_names() -> list:
    """Get list of all available strategy tool names."""
    return list(STRATEGY_TOOL_REGISTRY.keys())


def get_strategy_tool_pricing(tool_name: str) -> float:
    """Get pricing for a strategy tool."""
    tool = STRATEGY_TOOL_REGISTRY.get(tool_name)
    return tool.get("pricing", 0.0) if tool else 0.0


def format_strategy_tools_for_openai() -> list:
    """
    Format strategy tools for OpenAI function calling API.
    
    Returns:
        List of tool definitions in OpenAI format
    """
    return [
        {
            "type": tool["type"],
            "function": tool["function"]
        }
        for tool in STRATEGY_TOOL_REGISTRY.values()
    ]

