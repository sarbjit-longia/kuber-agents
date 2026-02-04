"""
Signal API Endpoints

Endpoints for signal metadata and recent signals.
"""
from typing import List, Dict, Any
from fastapi import APIRouter

from app.schemas.signal import SignalType as SignalTypeEnum

router = APIRouter()


# Signal type metadata mapping
SIGNAL_TYPE_METADATA = {
    # Traditional Technical Indicators
    "golden_cross": {
        "name": "Golden Cross",
        "description": "50-day SMA crosses above 200-day SMA (bullish)",
        "icon": "trending_up",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Rare (weeks per ticker)"
    },
    "death_cross": {
        "name": "Death Cross",
        "description": "50-day SMA crosses below 200-day SMA (bearish)",
        "icon": "trending_down",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Rare (weeks per ticker)"
    },
    "rsi_oversold": {
        "name": "RSI Oversold",
        "description": "RSI below 30 (oversold condition)",
        "icon": "show_chart",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "rsi_overbought": {
        "name": "RSI Overbought",
        "description": "RSI above 70 (overbought condition)",
        "icon": "show_chart",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "macd_bullish": {
        "name": "MACD Bullish Cross",
        "description": "MACD line crosses above signal line",
        "icon": "moving",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "macd_bearish": {
        "name": "MACD Bearish Cross",
        "description": "MACD line crosses below signal line",
        "icon": "moving",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "volume_spike": {
        "name": "Volume Spike",
        "description": "Trading volume significantly above average",
        "icon": "bar_chart",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "ema_bullish_crossover": {
        "name": "EMA Bullish Crossover",
        "description": "Fast EMA crosses above slow EMA",
        "icon": "trending_up",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "ema_bearish_crossover": {
        "name": "EMA Bearish Crossover",
        "description": "Fast EMA crosses below slow EMA",
        "icon": "trending_down",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "adx_strong_trend": {
        "name": "ADX Strong Trend",
        "description": "ADX above 25 indicating strong trend",
        "icon": "arrow_upward",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "adx_weak_trend": {
        "name": "ADX Weak Trend",
        "description": "ADX below 20 indicating weak/ranging market",
        "icon": "horizontal_rule",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    # ICT Concepts
    "fvg_bullish": {
        "name": "Bullish Fair Value Gap",
        "description": "Price gap indicating institutional buying",
        "icon": "align_vertical_top",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "fvg_bearish": {
        "name": "Bearish Fair Value Gap",
        "description": "Price gap indicating institutional selling",
        "icon": "align_vertical_bottom",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "order_block_bullish": {
        "name": "Bullish Order Block",
        "description": "Institutional buying zone identified",
        "icon": "grid_view",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "order_block_bearish": {
        "name": "Bearish Order Block",
        "description": "Institutional selling zone identified",
        "icon": "grid_view",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "break_of_structure_bullish": {
        "name": "Bullish Break of Structure",
        "description": "Price breaks above previous high",
        "icon": "north",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "break_of_structure_bearish": {
        "name": "Bearish Break of Structure",
        "description": "Price breaks below previous low",
        "icon": "south",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "liquidity_sweep_bullish": {
        "name": "Bullish Liquidity Sweep",
        "description": "Price sweeps lows then reverses up",
        "icon": "water_drop",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "liquidity_sweep_bearish": {
        "name": "Bearish Liquidity Sweep",
        "description": "Price sweeps highs then reverses down",
        "icon": "water_drop",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "choch_bullish": {
        "name": "Bullish Change of Character",
        "description": "Market structure shift to bullish",
        "icon": "change_circle",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "swing_point_break_bullish": {
        "name": "Bullish Swing Point Break",
        "description": "Price breaks above swing high",
        "icon": "analytics",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "swing_point_break_bearish": {
        "name": "Bearish Swing Point Break",
        "description": "Price breaks below swing low",
        "icon": "analytics",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    # Volume Analysis
    "accumulation_signal": {
        "name": "Accumulation Signal",
        "description": "A/D line rising indicating accumulation",
        "icon": "add_circle",
        "category": "volume",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "distribution_signal": {
        "name": "Distribution Signal",
        "description": "A/D line falling indicating distribution",
        "icon": "remove_circle",
        "category": "volume",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "poc_break_bullish": {
        "name": "Bullish POC Break",
        "description": "Price breaks above Volume Profile POC",
        "icon": "layers",
        "category": "volume",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "poc_break_bearish": {
        "name": "Bearish POC Break",
        "description": "Price breaks below Volume Profile POC",
        "icon": "layers",
        "category": "volume",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    # Multi-Timeframe
    "htf_trend_aligned_bullish": {
        "name": "HTF Bullish Trend Alignment",
        "description": "Multiple higher timeframes aligned bullish",
        "icon": "stacked_line_chart",
        "category": "multi-timeframe",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    # Additional Oscillators
    "cci_oversold": {
        "name": "CCI Oversold",
        "description": "CCI below -100",
        "icon": "speed",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "cci_overbought": {
        "name": "CCI Overbought",
        "description": "CCI above +100",
        "icon": "speed",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "cci_bullish_zero_cross": {
        "name": "CCI Bullish Zero Cross",
        "description": "CCI crosses above zero",
        "icon": "trending_up",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "cci_bearish_zero_cross": {
        "name": "CCI Bearish Zero Cross",
        "description": "CCI crosses below zero",
        "icon": "trending_down",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "willr_oversold": {
        "name": "Williams %R Oversold",
        "description": "Williams %R below -80",
        "icon": "percent",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "willr_overbought": {
        "name": "Williams %R Overbought",
        "description": "Williams %R above -20",
        "icon": "percent",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "willr_bullish_momentum": {
        "name": "Williams %R Bullish Momentum",
        "description": "Williams %R showing bullish momentum",
        "icon": "north_east",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "willr_bearish_momentum": {
        "name": "Williams %R Bearish Momentum",
        "description": "Williams %R showing bearish momentum",
        "icon": "south_east",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "mfi_oversold": {
        "name": "MFI Oversold",
        "description": "Money Flow Index below 20",
        "icon": "attach_money",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "mfi_overbought": {
        "name": "MFI Overbought",
        "description": "Money Flow Index above 80",
        "icon": "attach_money",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "atr_volatility_spike": {
        "name": "ATR Volatility Spike",
        "description": "Average True Range spiking up",
        "icon": "bolt",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "atr_volatility_compression": {
        "name": "ATR Volatility Compression",
        "description": "Average True Range compressing",
        "icon": "compress",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    # Bollinger Bands
    "bbands_upper_breakout": {
        "name": "Bollinger Bands Upper Breakout",
        "description": "Price breaks above upper Bollinger Band",
        "icon": "north",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "bbands_lower_breakout": {
        "name": "Bollinger Bands Lower Breakout",
        "description": "Price breaks below lower Bollinger Band",
        "icon": "south",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "bbands_upper_bounce": {
        "name": "Bollinger Bands Upper Bounce",
        "description": "Price bounces off upper Bollinger Band",
        "icon": "keyboard_return",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "bbands_lower_bounce": {
        "name": "Bollinger Bands Lower Bounce",
        "description": "Price bounces off lower Bollinger Band",
        "icon": "keyboard_return",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    # Stochastic
    "stoch_bullish": {
        "name": "Stochastic Bullish",
        "description": "Stochastic oversold and turning up",
        "icon": "trending_up",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "stoch_bearish": {
        "name": "Stochastic Bearish",
        "description": "Stochastic overbought and turning down",
        "icon": "trending_down",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    # Stochastic RSI
    "stochrsi_oversold": {
        "name": "Stochastic RSI Oversold",
        "description": "Stochastic RSI below 20",
        "icon": "show_chart",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "stochrsi_overbought": {
        "name": "Stochastic RSI Overbought",
        "description": "Stochastic RSI above 80",
        "icon": "show_chart",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "stochrsi_bullish_cross": {
        "name": "Stochastic RSI Bullish Cross",
        "description": "Stochastic RSI %K crosses above %D",
        "icon": "call_made",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "stochrsi_bearish_cross": {
        "name": "Stochastic RSI Bearish Cross",
        "description": "Stochastic RSI %K crosses below %D",
        "icon": "call_received",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    # AROON
    "aroon_uptrend": {
        "name": "AROON Uptrend",
        "description": "AROON Up above 70, Down below 30",
        "icon": "trending_up",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "aroon_downtrend": {
        "name": "AROON Downtrend",
        "description": "AROON Down above 70, Up below 30",
        "icon": "trending_down",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "aroon_bullish_cross": {
        "name": "AROON Bullish Cross",
        "description": "AROON Up crosses above AROON Down",
        "icon": "moving",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "aroon_bearish_cross": {
        "name": "AROON Bearish Cross",
        "description": "AROON Down crosses above AROON Up",
        "icon": "moving",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "aroon_consolidation": {
        "name": "AROON Consolidation",
        "description": "Both AROON Up and Down below 50 (ranging market)",
        "icon": "horizontal_rule",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    # OBV
    "obv_bullish_divergence": {
        "name": "OBV Bullish Divergence",
        "description": "Price makes lower low but OBV makes higher low",
        "icon": "divergence",
        "category": "volume",
        "is_free": True,
        "typical_frequency": "Rare (weeks per ticker)"
    },
    "obv_bearish_divergence": {
        "name": "OBV Bearish Divergence",
        "description": "Price makes higher high but OBV makes lower high",
        "icon": "divergence",
        "category": "volume",
        "is_free": True,
        "typical_frequency": "Rare (weeks per ticker)"
    },
    "obv_bullish_breakout": {
        "name": "OBV Bullish Breakout",
        "description": "OBV breaks above resistance",
        "icon": "north",
        "category": "volume",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "obv_bearish_breakdown": {
        "name": "OBV Bearish Breakdown",
        "description": "OBV breaks below support",
        "icon": "south",
        "category": "volume",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    # SAR
    "sar_bullish_reversal": {
        "name": "SAR Bullish Reversal",
        "description": "Parabolic SAR flips below price (bullish)",
        "icon": "u_turn_left",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "sar_bearish_reversal": {
        "name": "SAR Bearish Reversal",
        "description": "Parabolic SAR flips above price (bearish)",
        "icon": "u_turn_right",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    # ICT Additional
    "choch_bearish": {
        "name": "Bearish Change of Character",
        "description": "Market structure shift to bearish",
        "icon": "change_circle",
        "category": "ict",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    # Multi-Timeframe Additional
    "htf_trend_aligned_bearish": {
        "name": "HTF Bearish Trend Alignment",
        "description": "Multiple higher timeframes aligned bearish",
        "icon": "stacked_line_chart",
        "category": "multi-timeframe",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    # Generic
    "news": {
        "name": "News Event",
        "description": "Significant news or fundamental event",
        "icon": "article",
        "category": "fundamental",
        "is_free": False,
        "typical_frequency": "Multiple per day"
    },
    "breakout": {
        "name": "Generic Breakout",
        "description": "Price breaks out of established range",
        "icon": "open_in_full",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per week"
    },
    "price_level": {
        "name": "Key Price Level",
        "description": "Price reaches significant level",
        "icon": "linear_scale",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "volatility": {
        "name": "Volatility Event",
        "description": "Unusual volatility detected",
        "icon": "scatter_plot",
        "category": "technical",
        "is_free": True,
        "typical_frequency": "Multiple per day"
    },
    "external": {
        "name": "External Signal",
        "description": "Signal from external source/webhook",
        "icon": "input",
        "category": "other",
        "is_free": True,
        "typical_frequency": "Varies"
    },
}

# Default metadata for signal types not in the mapping
DEFAULT_METADATA = {
    "name": "Unknown Signal",
    "description": "Signal type not yet documented",
    "icon": "help",
    "category": "other",
    "is_free": True,
    "typical_frequency": "Varies"
}


@router.get("/signals/types")
async def get_available_signal_types() -> List[Dict[str, Any]]:
    """
    Get all available signal generator types.
    
    This endpoint returns metadata about all signal types defined in the SignalType enum.
    Dynamically builds the list from the enum to ensure it's always up to date.
    
    Returns:
        List of signal type metadata
    """
    signal_types = []
    
    for signal_enum in SignalTypeEnum:
        signal_value = signal_enum.value
        
        # Get metadata from mapping or use default
        metadata = SIGNAL_TYPE_METADATA.get(signal_value, DEFAULT_METADATA.copy())
        
        signal_types.append({
            "signal_type": signal_value,
            "name": metadata["name"],
            "description": metadata["description"],
            "icon": metadata["icon"],
            "category": metadata["category"],
            "is_free": metadata["is_free"],
            "typical_frequency": metadata["typical_frequency"]
        })
    
    return signal_types
