"""
Reasoning Chart Parser - Extract chart annotations from LLM reasoning

This service parses the LLM's natural language reasoning and extracts
visual patterns, levels, and zones to display on charts.
"""
import re
import structlog
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = structlog.get_logger()


class ReasoningChartParser:
    """
    Parses LLM reasoning text to extract tradeable patterns, levels, and zones
    for chart visualization.
    """
    
    # Pattern keywords to detect
    PATTERN_KEYWORDS = {
        'fvg': ['fair value gap', 'fvg', 'imbalance', 'gap'],
        'flag': ['bull flag', 'bear flag', 'flag pattern', 'bullish flag', 'bearish flag'],
        'triangle': ['ascending triangle', 'descending triangle', 'symmetrical triangle'],
        'wedge': ['rising wedge', 'falling wedge', 'wedge'],
        'channel': ['channel', 'ascending channel', 'descending channel'],
        'head_shoulders': ['head and shoulders', 'inverse head and shoulders', 'h&s'],
        'double_top_bottom': ['double top', 'double bottom'],
        'support_resistance': ['support', 'resistance', 'key level', 'horizontal level']
    }
    
    def __init__(self):
        """Initialize the parser."""
        pass
    
    def parse_reasoning_to_annotations(
        self,
        reasoning: str,
        strategy_action: str,
        entry_price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        candles: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Parse LLM reasoning and extract chart annotations.
        
        Args:
            reasoning: The LLM's natural language reasoning
            strategy_action: BUY/SELL/HOLD
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            candles: Historical candle data
            
        Returns:
            Dictionary with shapes, lines, markers, zones, text annotations
        """
        logger.info("parsing_llm_reasoning_for_charts", text_length=len(reasoning))
        
        annotations = {
            "shapes": [],
            "lines": [],
            "markers": [],
            "zones": [],
            "text": [],
            "arrows": []
        }
        
        # Extract price range from candles
        if candles:
            prices = [c['high'] for c in candles] + [c['low'] for c in candles]
            price_range = (min(prices), max(prices))
            latest_time = candles[-1].get('timestamp', candles[-1].get('time'))
        else:
            price_range = (entry_price * 0.9, entry_price * 1.1)
            latest_time = datetime.utcnow().isoformat()
        
        # 1. Extract FVGs (Fair Value Gaps)
        fvgs = self._extract_fvgs(reasoning, price_range)
        annotations['shapes'].extend(fvgs)
        
        # 2. Extract support/resistance levels
        levels = self._extract_levels(reasoning, price_range)
        annotations['lines'].extend(levels)
        
        # 3. Extract patterns (flags, triangles, etc.)
        patterns = self._extract_patterns(reasoning, price_range, latest_time)
        annotations['shapes'].extend(patterns)
        
        # 4. Extract zones (premium/discount)
        zones = self._extract_zones(reasoning, price_range)
        annotations['zones'].extend(zones)
        
        # 5. Extract reasoning bullets as text annotations
        reasoning_points = self._extract_reasoning_points(reasoning, latest_time)
        annotations['text'].extend(reasoning_points)
        
        # 6. Add bias/trend indicator
        bias_text = self._extract_bias(reasoning, latest_time)
        if bias_text:
            annotations['text'].append(bias_text)
        
        logger.info(
            "reasoning_parsed",
            shapes=len(annotations['shapes']),
            lines=len(annotations['lines']),
            zones=len(annotations['zones']),
            text=len(annotations['text'])
        )
        
        return annotations
    
    def _extract_fvgs(self, reasoning: str, price_range: Tuple[float, float]) -> List[Dict]:
        """Extract Fair Value Gap mentions from reasoning."""
        fvgs = []
        
        # Pattern: "FVG at $248-$250" or "bullish imbalance between 248 and 250"
        patterns = [
            r'(?:fvg|fair value gap|imbalance).*?(?:at|between|from)\s*\$?(\d+\.?\d*)\s*(?:to|-|and)\s*\$?(\d+\.?\d*)',
            r'(?:bullish|bearish)\s+(?:fvg|gap|imbalance).*?\$?(\d+\.?\d*)\s*(?:to|-|and)\s*\$?(\d+\.?\d*)',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, reasoning, re.IGNORECASE)
            for match in matches:
                try:
                    price1 = float(match.group(1))
                    price2 = float(match.group(2))
                    
                    # Validate prices are in range
                    if not (price_range[0] <= price1 <= price_range[1] * 1.1 and 
                           price_range[0] <= price2 <= price_range[1] * 1.1):
                        continue
                    
                    # Determine if bullish or bearish
                    context = reasoning[max(0, match.start()-50):match.end()+50].lower()
                    is_bullish = 'bullish' in context or 'buy' in context
                    
                    fvgs.append({
                        "type": "rectangle",
                        "price1": min(price1, price2),
                        "price2": max(price1, price2),
                        "color": "#22c55e" if is_bullish else "#ef4444",
                        "opacity": 0.25,
                        "border_color": "#22c55e" if is_bullish else "#ef4444",
                        "border_width": 2,
                        "border_style": "dashed",
                        "label": "🟢 FVG" if is_bullish else "🔴 FVG",
                        "source": "llm_reasoning"
                    })
                except (ValueError, IndexError):
                    continue
        
        return fvgs
    
    def _extract_levels(self, reasoning: str, price_range: Tuple[float, float]) -> List[Dict]:
        """Extract support/resistance levels from reasoning."""
        levels = []
        
        # Pattern: "support at $250", "resistance near 255", "key level 248.50"
        patterns = [
            r'(?:support|resistance|key level|horizontal level|price level).*?(?:at|near|around)\s*\$?(\d+\.?\d*)',
            r'\$?(\d+\.?\d*)\s+(?:support|resistance|level)',
        ]
        
        seen_prices = set()  # Avoid duplicates
        
        for pattern in patterns:
            matches = re.finditer(pattern, reasoning, re.IGNORECASE)
            for match in matches:
                try:
                    price = float(match.group(1))
                    
                    # Validate price is in reasonable range
                    if not (price_range[0] * 0.95 <= price <= price_range[1] * 1.05):
                        continue
                    
                    # Skip if already added
                    if price in seen_prices:
                        continue
                    seen_prices.add(price)
                    
                    # Determine type from context
                    context = reasoning[max(0, match.start()-30):match.end()+30].lower()
                    is_support = 'support' in context
                    is_resistance = 'resistance' in context
                    
                    if is_support or is_resistance:
                        levels.append({
                            "type": "horizontal",
                            "price": price,
                            "color": "#3b82f6" if is_support else "#ef4444",
                            "width": 1,
                            "style": "solid",
                            "label": f"{'📍 Support' if is_support else '🚫 Resistance'}: ${price:.2f}",
                            "source": "llm_reasoning"
                        })
                except (ValueError, IndexError):
                    continue
        
        return levels
    
    def _extract_patterns(
        self,
        reasoning: str,
        price_range: Tuple[float, float],
        latest_time: str
    ) -> List[Dict]:
        """Extract chart patterns (flags, triangles, etc.) from reasoning."""
        patterns = []
        
        # Detect pattern mentions
        text_lower = reasoning.lower()
        
        # Bull flag
        if any(kw in text_lower for kw in ['bull flag', 'bullish flag', 'flag pattern']):
            if 'bull' in text_lower:
                # Try to extract price range for the flag
                match = re.search(r'flag.*?(?:between|from)\s*\$?(\d+\.?\d*)\s*(?:to|-|and)\s*\$?(\d+\.?\d*)', 
                                text_lower)
                if match:
                    try:
                        price1 = float(match.group(1))
                        price2 = float(match.group(2))
                        
                        patterns.append({
                            "type": "rectangle",
                            "price1": min(price1, price2),
                            "price2": max(price1, price2),
                            "color": "#22c55e",
                            "opacity": 0.15,
                            "border_color": "#22c55e",
                            "border_width": 2,
                            "border_style": "solid",
                            "label": "🚩 Bull Flag",
                            "source": "llm_reasoning"
                        })
                    except (ValueError, IndexError):
                        pass
        
        # Bear flag
        if any(kw in text_lower for kw in ['bear flag', 'bearish flag']):
            match = re.search(r'flag.*?(?:between|from)\s*\$?(\d+\.?\d*)\s*(?:to|-|and)\s*\$?(\d+\.?\d*)', 
                            text_lower)
            if match:
                try:
                    price1 = float(match.group(1))
                    price2 = float(match.group(2))
                    
                    patterns.append({
                        "type": "rectangle",
                        "price1": min(price1, price2),
                        "price2": max(price1, price2),
                        "color": "#ef4444",
                        "opacity": 0.15,
                        "border_color": "#ef4444",
                        "border_width": 2,
                        "border_style": "solid",
                        "label": "🚩 Bear Flag",
                        "source": "llm_reasoning"
                    })
                except (ValueError, IndexError):
                    pass
        
        return patterns
    
    def _extract_zones(self, reasoning: str, price_range: Tuple[float, float]) -> List[Dict]:
        """Extract premium/discount zones from reasoning."""
        zones = []
        text_lower = reasoning.lower()
        
        # Pattern: "premium zone $255-$260" or "discount area between 240 and 245"
        zone_patterns = [
            r'(?:premium|expensive|overbought)\s+(?:zone|area|region).*?(?:at|between|from)\s*\$?(\d+\.?\d*)\s*(?:to|-|and)\s*\$?(\d+\.?\d*)',
            r'(?:discount|cheap|oversold)\s+(?:zone|area|region).*?(?:at|between|from)\s*\$?(\d+\.?\d*)\s*(?:to|-|and)\s*\$?(\d+\.?\d*)',
        ]
        
        for pattern in zone_patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                try:
                    price1 = float(match.group(1))
                    price2 = float(match.group(2))
                    
                    context = text_lower[max(0, match.start()-20):match.end()+20]
                    is_premium = 'premium' in context or 'expensive' in context or 'overbought' in context
                    
                    zones.append({
                        "price1": min(price1, price2),
                        "price2": max(price1, price2),
                        "color": "rgba(239, 68, 68, 0.15)" if is_premium else "rgba(34, 197, 94, 0.15)",
                        "label": "❤️ PREMIUM ZONE" if is_premium else "💚 DISCOUNT ZONE",
                        "source": "llm_reasoning"
                    })
                except (ValueError, IndexError):
                    continue
        
        return zones
    
    def _extract_reasoning_points(self, reasoning: str, latest_time: str) -> List[Dict]:
        """Extract key reasoning points as text annotations."""
        points = []
        
        # Split into sentences/bullet points
        lines = reasoning.split('\n')
        key_points = []
        
        for line in lines:
            line = line.strip()
            # Look for bullet points or numbered lists
            if any(line.startswith(prefix) for prefix in ['•', '-', '*', '1.', '2.', '3.', '✓', '✅', '🎯']):
                # Clean up
                cleaned = re.sub(r'^[•\-*\d\.✓✅🎯\s]+', '', line).strip()
                if len(cleaned) > 10 and len(cleaned) < 150:  # Reasonable length
                    key_points.append(cleaned)
        
        # Add up to 3 key points as overlay text
        for i, point in enumerate(key_points[:3]):
            points.append({
                "time": "latest",
                "position": f"bottom_left",
                "text": f"• {point}",
                "color": "#ffffff",
                "font_size": 10,
                "background": "rgba(0, 0, 0, 0.75)",
                "padding": 6,
                "offset_y": i * 30,  # Stack vertically
                "source": "llm_reasoning"
            })
        
        return points
    
    def _extract_bias(self, reasoning: str, latest_time: str) -> Optional[Dict]:
        """Extract overall market bias from reasoning."""
        text_lower = reasoning.lower()
        
        # Look for explicit bias statements
        if 'bullish bias' in text_lower or 'uptrend' in text_lower or 'bull market' in text_lower:
            return {
                "time": "latest",
                "position": "top_left",
                "text": "📈 BULLISH BIAS",
                "color": "#22c55e",
                "font_size": 14,
                "bold": True,
                "background": "rgba(0, 0, 0, 0.8)",
                "padding": 8,
                "source": "llm_reasoning"
            }
        elif 'bearish bias' in text_lower or 'downtrend' in text_lower or 'bear market' in text_lower:
            return {
                "time": "latest",
                "position": "top_left",
                "text": "📉 BEARISH BIAS",
                "color": "#ef4444",
                "font_size": 14,
                "bold": True,
                "background": "rgba(0, 0, 0, 0.8)",
                "padding": 8,
                "source": "llm_reasoning"
            }
        elif 'ranging' in text_lower or 'sideways' in text_lower or 'consolidation' in text_lower:
            return {
                "time": "latest",
                "position": "top_left",
                "text": "↔️ RANGING / CONSOLIDATION",
                "color": "#6b7280",
                "font_size": 14,
                "bold": True,
                "background": "rgba(0, 0, 0, 0.8)",
                "padding": 8,
                "source": "llm_reasoning"
            }
        
        return None


# Singleton instance
reasoning_chart_parser = ReasoningChartParser()

