"""
Instruction Parser Service

Parses natural language instructions to extract configuration like timeframes.
"""
import re
from typing import List, Set
import structlog

logger = structlog.get_logger()


class InstructionParser:
    """
    Parse natural language instructions to extract trading parameters.
    
    This makes the system truly instruction-driven by automatically
    detecting required resources from user's natural language.
    """
    
    # Timeframe patterns (covers common formats)
    TIMEFRAME_PATTERNS = [
        r'\b(\d+[mhd])\b',  # 5m, 1h, 4h, 1d
        r'(\d+)[\s-]*(?:minute|min)s?\b',  # 5 minute, 5-minute, 30 minutes, 15 min
        r'(\d+)[\s-]*(?:hour)s?\b',  # 1 hour, 1-hour, 4 hours, 4-hours
        r'(\d+)[\s-]*(?:day)s?\b',  # 1 day, 1-day, 2 days
        r'\b(daily|weekly|monthly)\b',  # daily, weekly
    ]
    
    # Mapping of text to canonical timeframe format
    TIMEFRAME_MAPPING = {
        'daily': '1d',
        'weekly': '1w',
        'monthly': '1M',
        '1 minute': '1m', '1-minute': '1m',
        '5 minute': '5m', '5-minute': '5m',
        '15 minute': '15m', '15-minute': '15m',
        '30 minute': '30m', '30-minute': '30m',
        '1 hour': '1h', '1-hour': '1h',
        '4 hour': '4h', '4-hour': '4h',
        '12 hour': '12h', '12-hour': '12h',
        '24 hour': '1d', '24-hour': '1d',
    }
    
    @classmethod
    def extract_timeframes(cls, instructions: str) -> List[str]:
        """
        Extract timeframes mentioned in instructions.
        
        Examples:
            "Use RSI on 1h and 4h timeframes" -> ["1h", "4h"]
            "Analyze daily chart for bias" -> ["1d"]
            "Look for 5 minute entries" -> ["5m"]
        
        Args:
            instructions: Natural language instructions
            
        Returns:
            List of canonical timeframe strings (e.g., ["5m", "1h", "1d"])
        """
        if not instructions:
            return []
        
        timeframes: Set[str] = set()
        instructions_lower = instructions.lower()
        
        # Extract using patterns
        for pattern in cls.TIMEFRAME_PATTERNS:
            matches = re.finditer(pattern, instructions_lower, re.IGNORECASE)
            for match in matches:
                # Get the full matched text for context
                matched_text = match.group(0)
                
                # Normalize to canonical format
                canonical = cls._normalize_timeframe(matched_text)
                if canonical:
                    timeframes.add(canonical)
        
        # Sort timeframes by duration (smallest to largest)
        sorted_timeframes = sorted(
            list(timeframes),
            key=lambda x: cls._timeframe_to_minutes(x)
        )
        
        logger.debug(
            "timeframes_extracted_from_instructions",
            instructions_preview=instructions[:100],
            timeframes=sorted_timeframes
        )
        
        return sorted_timeframes
    
    @classmethod
    def _normalize_timeframe(cls, tf: str) -> str:
        """
        Normalize timeframe to canonical format.
        
        Args:
            tf: Timeframe string (e.g., "1h", "daily", "5 minute")
            
        Returns:
            Canonical timeframe string or empty if invalid
        """
        tf = tf.strip().lower()
        
        # Already in canonical format (e.g., "5m", "1h", "1d")
        if re.match(r'^\d+[mhdwM]$', tf):
            return tf
        
        # Look up in mapping
        if tf in cls.TIMEFRAME_MAPPING:
            return cls.TIMEFRAME_MAPPING[tf]
        
        # Parse text like "15 minute" -> "15m"
        minute_match = re.search(r'(\d+)\s*(?:minute|min)s?', tf)
        if minute_match:
            return f"{minute_match.group(1)}m"
        
        hour_match = re.search(r'(\d+)\s*(?:hour)s?', tf)
        if hour_match:
            return f"{hour_match.group(1)}h"
        
        day_match = re.search(r'(\d+)\s*(?:day)s?', tf)
        if day_match:
            return f"{day_match.group(1)}d"
        
        return ""
    
    @classmethod
    def _timeframe_to_minutes(cls, tf: str) -> int:
        """
        Convert timeframe to minutes for sorting.
        
        Args:
            tf: Canonical timeframe (e.g., "5m", "1h", "1d")
            
        Returns:
            Number of minutes
        """
        if not tf:
            return 0
        
        match = re.match(r'(\d+)([mhdwM])', tf)
        if not match:
            return 0
        
        value = int(match.group(1))
        unit = match.group(2)
        
        multipliers = {
            'm': 1,
            'h': 60,
            'd': 1440,
            'w': 10080,
            'M': 43200  # Approximate
        }
        
        return value * multipliers.get(unit, 0)


# Singleton instance
instruction_parser = InstructionParser()

