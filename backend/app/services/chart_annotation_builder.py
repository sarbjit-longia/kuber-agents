"""
Chart Annotation Builder - Converts tool results into visual chart annotations

This service transforms ICT tool results (FVGs, liquidity, structure, etc.) into
a structured format that can be rendered on TradingView charts.
"""
import structlog
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.schemas.pipeline_state import StrategyResult

logger = structlog.get_logger()


class ChartAnnotationBuilder:
    """Builds chart annotations from strategy tool results."""
    
    def __init__(self, symbol: str, timeframe: str):
        """
        Initialize chart builder.
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            timeframe: Primary strategy timeframe (e.g., "1h")
        """
        self.symbol = symbol
        self.timeframe = timeframe
    
    def build_chart_data(
        self,
        candles: List[Dict[str, Any]],
        tool_results: Dict[str, Any],
        strategy_result: StrategyResult,
        instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build complete chart data with annotations.
        
        Args:
            candles: OHLC candles for the chart
            tool_results: Results from all executed strategy tools
            strategy_result: Final strategy decision (BUY/SELL/HOLD)
            instructions: User's original strategy instructions
        
        Returns:
            Complete chart data structure for TradingView rendering
        """
        logger.info(
            "building_chart_data",
            symbol=self.symbol,
            timeframe=self.timeframe,
            num_candles=len(candles),
            num_tools=len(tool_results)
        )
        
        # Prepare candle data
        chart_candles = self._format_candles(candles)
        
        # Build annotations from tool results
        annotations = {
            "shapes": [],      # Rectangles, circles, etc.
            "lines": [],       # Horizontal/vertical lines
            "arrows": [],      # Directional arrows
            "markers": [],     # Point markers (entry, exit)
            "zones": [],       # Shaded areas (premium/discount)
            "text": []         # Text labels
        }
        
        # Add FVG annotations
        if "fvg_detector" in tool_results:
            self._add_fvg_annotations(annotations, tool_results["fvg_detector"])
        
        # Add liquidity annotations
        if "liquidity_analyzer" in tool_results:
            self._add_liquidity_annotations(annotations, tool_results["liquidity_analyzer"])
        
        # Add market structure annotations
        if "market_structure" in tool_results:
            self._add_structure_annotations(annotations, tool_results["market_structure"])
        
        # Add premium/discount zones
        if "premium_discount" in tool_results:
            self._add_zone_annotations(annotations, tool_results["premium_discount"])
        
        # Add trade decision markers
        self._add_trade_annotations(annotations, strategy_result, candles)
        
        # Build indicator data
        indicators = self._build_indicator_data(tool_results)
        
        # Build decision summary
        decision_summary = self._build_decision_summary(
            strategy_result,
            tool_results,
            instructions
        )
        
        chart_data = {
            "meta": {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "generated_at": datetime.utcnow().isoformat(),
                "candle_count": len(candles)
            },
            "candles": chart_candles,
            "annotations": annotations,
            "indicators": indicators,
            "decision": decision_summary
        }
        
        logger.info(
            "chart_data_built",
            shapes=len(annotations["shapes"]),
            lines=len(annotations["lines"]),
            arrows=len(annotations["arrows"]),
            markers=len(annotations["markers"])
        )
        
        return chart_data
    
    def _format_candles(self, candles: List[Dict]) -> List[Dict]:
        """Format candles for TradingView."""
        formatted = []
        
        for candle in candles:
            formatted.append({
                "time": candle.get("timestamp", candle.get("time")),
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"],
                "volume": candle.get("volume", 0)
            })
        
        return formatted
    
    def _add_fvg_annotations(self, annotations: Dict, fvg_result: Dict) -> None:
        """Add Fair Value Gap rectangles to chart."""
        fvgs = fvg_result.get("fvgs", [])
        
        for fvg in fvgs[-10:]:  # Show last 10 FVGs to avoid clutter
            color = "#22c55e" if fvg["type"] == "bullish" else "#ef4444"
            opacity = 0.2 if fvg["is_filled"] else 0.35
            
            annotations["shapes"].append({
                "type": "rectangle",
                "time1": fvg["formed_at"],
                "time2": fvg["formed_at"],  # Will extend to current time in frontend
                "price1": fvg["low"],
                "price2": fvg["high"],
                "color": color,
                "opacity": opacity,
                "border_color": color,
                "border_width": 1,
                "border_style": "dotted" if fvg["is_filled"] else "solid",
                "label": {
                    "text": f"{'↑' if fvg['type'] == 'bullish' else '↓'} FVG {fvg['gap_size_pips']:.1f}p",
                    "color": color,
                    "font_size": 10
                },
                "tooltip": (
                    f"{'Bullish' if fvg['type'] == 'bullish' else 'Bearish'} FVG\n"
                    f"Gap: {fvg['gap_size_pips']:.1f} pips\n"
                    f"Status: {'Filled' if fvg['is_filled'] else 'Unfilled'}\n"
                    f"Fill: {fvg['fill_percentage']:.0f}%"
                )
            })
    
    def _add_liquidity_annotations(self, annotations: Dict, liq_result: Dict) -> None:
        """Add liquidity levels and grabs to chart."""
        # Add active liquidity pools as horizontal lines
        pools = liq_result.get("active_liquidity_pools", {})
        
        # Buy-side liquidity (above current price)
        for level in pools.get("above", [])[:5]:  # Top 5
            annotations["lines"].append({
                "type": "horizontal",
                "price": level,
                "color": "#ef4444",
                "width": 1,
                "style": "dashed",
                "label": {
                    "text": "🔴 Sell-side Liq",
                    "position": "right"
                },
                "tooltip": f"Buy-side liquidity at ${level:.5f}"
            })
        
        # Sell-side liquidity (below current price)
        for level in pools.get("below", [])[:5]:  # Bottom 5
            annotations["lines"].append({
                "type": "horizontal",
                "price": level,
                "color": "#3b82f6",
                "width": 1,
                "style": "dashed",
                "label": {
                    "text": "🔵 Buy-side Liq",
                    "position": "right"
                },
                "tooltip": f"Sell-side liquidity at ${level:.5f}"
            })
        
        # Add liquidity grabs as markers
        for grab in liq_result.get("liquidity_grabs", [])[-5:]:  # Last 5 grabs
            if grab.get("reversed"):
                annotations["markers"].append({
                    "time": grab["grabbed_at"],
                    "position": "aboveBar" if grab["type"] == "buy_side" else "belowBar",
                    "color": "#f59e0b",
                    "shape": "arrowDown" if grab["type"] == "buy_side" else "arrowUp",
                    "text": f"Liq Grab ({grab['distance_pips']:.0f}p)",
                    "tooltip": (
                        f"{'Buy' if grab['type'] == 'buy_side' else 'Sell'}-side liquidity grab\n"
                        f"Level: ${grab['level']:.5f}\n"
                        f"Distance: {grab['distance_pips']:.1f} pips\n"
                        f"Reversed: Yes"
                    )
                })
    
    def _add_structure_annotations(self, annotations: Dict, structure_result: Dict) -> None:
        """Add market structure (BOS/CHoCH) arrows to chart."""
        events = structure_result.get("structure_events", [])
        
        for event in events[-10:]:  # Last 10 events
            is_bos = event["type"] == "BOS"
            is_bullish = event["direction"] == "bullish"
            
            color = "#22c55e" if is_bullish else "#ef4444"
            
            annotations["arrows"].append({
                "time": event["timestamp"],
                "price": event["level"],
                "direction": "up" if is_bullish else "down",
                "color": color,
                "size": "large" if is_bos else "medium",
                "label": {
                    "text": f"{'📈' if is_bullish else '📉'} {event['type']}",
                    "color": color
                },
                "tooltip": (
                    f"{event['type']} ({'Bullish' if is_bullish else 'Bearish'})\n"
                    f"Level: ${event['level']:.5f}\n"
                    f"{'Trend continuation' if is_bos else 'Potential reversal'}"
                )
            })
        
        # Add trend label
        trend = structure_result.get("trend", "ranging")
        trend_emoji = {"bullish": "📈", "bearish": "📉", "ranging": "↔️"}.get(trend, "")
        
        annotations["text"].append({
            "time": "latest",  # Position at latest candle
            "position": "top_left",
            "text": f"{trend_emoji} Trend: {trend.upper()}",
            "color": "#22c55e" if trend == "bullish" else "#ef4444" if trend == "bearish" else "#6b7280",
            "font_size": 14,
            "bold": True,
            "background": "rgba(0, 0, 0, 0.7)",
            "padding": 8
        })
    
    def _add_zone_annotations(self, annotations: Dict, pd_result: Dict) -> None:
        """Add premium/discount zones as shaded areas."""
        zones = pd_result.get("zones", {})
        
        # Discount zone (0-30%)
        if "discount" in zones:
            annotations["zones"].append({
                "price1": zones["discount"]["low"],
                "price2": zones["discount"]["high"],
                "color": "rgba(34, 197, 94, 0.15)",
                "label": {
                    "text": "💚 DISCOUNT ZONE (0-30%)",
                    "position": "left",
                    "color": "#22c55e"
                },
                "tooltip": "Ideal area for BUY entries (price is cheap)"
            })
        
        # Equilibrium zone (40-60%)
        if "equilibrium" in zones:
            annotations["zones"].append({
                "price1": zones["equilibrium"]["low"],
                "price2": zones["equilibrium"]["high"],
                "color": "rgba(107, 114, 128, 0.10)",
                "label": {
                    "text": "⚖️ EQUILIBRIUM (40-60%)",
                    "position": "left",
                    "color": "#6b7280"
                },
                "tooltip": "Fair value area (wait for better price)"
            })
        
        # Premium zone (70-100%)
        if "premium" in zones:
            annotations["zones"].append({
                "price1": zones["premium"]["low"],
                "price2": zones["premium"]["high"],
                "color": "rgba(239, 68, 68, 0.15)",
                "label": {
                    "text": "❤️ PREMIUM ZONE (70-100%)",
                    "position": "left",
                    "color": "#ef4444"
                },
                "tooltip": "Ideal area for SELL entries (price is expensive)"
            })
        
        # Add current price level indicator
        current_zone = pd_result.get("zone", "equilibrium")
        price_level = pd_result.get("price_level_percent", 50)
        
        annotations["text"].append({
            "time": "latest",
            "position": "top_right",
            "text": f"Price @ {price_level:.0f}% ({current_zone.upper()})",
            "color": "#22c55e" if current_zone == "discount" else "#ef4444" if current_zone == "premium" else "#6b7280",
            "font_size": 12,
            "background": "rgba(0, 0, 0, 0.7)",
            "padding": 6
        })
    
    def _add_trade_annotations(
        self,
        annotations: Dict,
        strategy_result: StrategyResult,
        candles: List[Dict]
    ) -> None:
        """Add trade entry, SL, TP markers."""
        if strategy_result.action == "HOLD":
            return
        
        latest_time = candles[-1].get("timestamp") if candles else None
        if not latest_time:
            return
        
        is_buy = strategy_result.action == "BUY"
        entry_color = "#22c55e" if is_buy else "#ef4444"
        
        # Entry marker (large circle)
        annotations["markers"].append({
            "time": latest_time,
            "price": strategy_result.entry_price,
            "position": "belowBar" if is_buy else "aboveBar",
            "color": entry_color,
            "shape": "circle",
            "size": "large",
            "text": f"{'🟢' if is_buy else '🔴'} ENTRY",
            "tooltip": (
                f"{strategy_result.action} @ ${strategy_result.entry_price:.2f}\n"
                f"Confidence: {strategy_result.confidence * 100:.0f}%\n"
                f"Pattern: {strategy_result.pattern_detected}"
            )
        })
        
        # Stop Loss line
        if strategy_result.stop_loss:
            annotations["lines"].append({
                "type": "horizontal",
                "price": strategy_result.stop_loss,
                "color": "#ef4444",
                "width": 2,
                "style": "solid",
                "label": {
                    "text": f"🛑 SL: ${strategy_result.stop_loss:.2f}",
                    "position": "right",
                    "color": "#ef4444"
                },
                "tooltip": f"Stop Loss: ${strategy_result.stop_loss:.2f}"
            })
        
        # Take Profit line
        if strategy_result.take_profit:
            annotations["lines"].append({
                "type": "horizontal",
                "price": strategy_result.take_profit,
                "color": "#22c55e",
                "width": 2,
                "style": "solid",
                "label": {
                    "text": f"🎯 TP: ${strategy_result.take_profit:.2f}",
                    "position": "right",
                    "color": "#22c55e"
                },
                "tooltip": f"Take Profit: ${strategy_result.take_profit:.2f}"
            })
        
        # Risk/Reward box
        if strategy_result.stop_loss and strategy_result.take_profit:
            risk = abs(strategy_result.entry_price - strategy_result.stop_loss)
            reward = abs(strategy_result.take_profit - strategy_result.entry_price)
            rr_ratio = reward / risk if risk > 0 else 0
            
            annotations["text"].append({
                "time": latest_time,
                "position": "bottom_right",
                "text": f"R:R = 1:{rr_ratio:.2f}",
                "color": "#22c55e" if rr_ratio >= 2 else "#f59e0b",
                "font_size": 14,
                "bold": True,
                "background": "rgba(0, 0, 0, 0.8)",
                "padding": 8
            })
    
    def _build_indicator_data(self, tool_results: Dict[str, Any]) -> Dict[str, Any]:
        """Build indicator subplot data."""
        indicators = {}
        
        # RSI
        if "rsi" in tool_results:
            rsi_data = tool_results["rsi"]
            indicators["rsi"] = {
                "type": "rsi",
                "values": rsi_data.get("values", []),
                "current": rsi_data.get("current_rsi"),
                "is_oversold": rsi_data.get("is_oversold", False),
                "is_overbought": rsi_data.get("is_overbought", False),
                "zones": {"overbought": 70, "oversold": 30},
                "signal": "OVERSOLD - Buy signal" if rsi_data.get("is_oversold") else "OVERBOUGHT - Sell signal" if rsi_data.get("is_overbought") else "Neutral"
            }
        
        # MACD
        if "macd" in tool_results:
            macd_data = tool_results["macd"]
            indicators["macd"] = {
                "type": "macd",
                "macd_line": macd_data.get("values", {}).get("macd", []),
                "signal_line": macd_data.get("values", {}).get("signal", []),
                "histogram": macd_data.get("values", {}).get("histogram", []),
                "is_bullish_crossover": macd_data.get("is_bullish_crossover", False),
                "is_bearish_crossover": macd_data.get("is_bearish_crossover", False)
            }
        
        return indicators
    
    def _build_decision_summary(
        self,
        strategy_result: StrategyResult,
        tool_results: Dict[str, Any],
        instructions: Optional[str]
    ) -> Dict[str, Any]:
        """Build decision summary with reasoning steps."""
        reasoning_steps = []
        conditions_met = 0
        conditions_total = 0
        
        # Analyze each tool result and build reasoning
        if "fvg_detector" in tool_results:
            fvg = tool_results["fvg_detector"]
            conditions_total += 1
            if strategy_result.action == "BUY" and fvg.get("latest_bullish_fvg"):
                conditions_met += 1
                fvg_data = fvg["latest_bullish_fvg"]
                reasoning_steps.append(
                    f"✅ Bullish FVG at ${fvg_data['low']:.5f}-${fvg_data['high']:.5f} "
                    f"({fvg_data['gap_size_pips']:.1f} pips, {'filled' if fvg_data['is_filled'] else 'unfilled'})"
                )
            elif strategy_result.action == "SELL" and fvg.get("latest_bearish_fvg"):
                conditions_met += 1
                fvg_data = fvg["latest_bearish_fvg"]
                reasoning_steps.append(
                    f"✅ Bearish FVG at ${fvg_data['low']:.5f}-${fvg_data['high']:.5f} "
                    f"({fvg_data['gap_size_pips']:.1f} pips, {'filled' if fvg_data['is_filled'] else 'unfilled'})"
                )
            else:
                reasoning_steps.append("⚠️ No relevant FVG detected")
        
        if "premium_discount" in tool_results:
            pd = tool_results["premium_discount"]
            conditions_total += 1
            zone = pd.get("zone", "equilibrium")
            price_level = pd.get("price_level_percent", 50)
            
            if (strategy_result.action == "BUY" and zone == "discount") or \
               (strategy_result.action == "SELL" and zone == "premium"):
                conditions_met += 1
                reasoning_steps.append(
                    f"✅ Price in {zone.upper()} zone ({price_level:.0f}% of range) - "
                    f"{'ideal for buys' if zone == 'discount' else 'ideal for sells'}"
                )
            else:
                reasoning_steps.append(
                    f"⚠️ Price in {zone.upper()} zone ({price_level:.0f}%) - "
                    f"{'wait for better price' if zone == 'equilibrium' else 'not ideal'}"
                )
        
        if "rsi" in tool_results:
            rsi = tool_results["rsi"]
            conditions_total += 1
            current_rsi = rsi.get("current_rsi", 50)
            
            if (strategy_result.action == "BUY" and rsi.get("is_oversold")) or \
               (strategy_result.action == "SELL" and rsi.get("is_overbought")):
                conditions_met += 1
                reasoning_steps.append(
                    f"✅ RSI {current_rsi:.1f} ({'oversold' if rsi.get('is_oversold') else 'overbought'}) - "
                    f"{'buy signal' if rsi.get('is_oversold') else 'sell signal'}"
                )
            else:
                reasoning_steps.append(f"⚠️ RSI {current_rsi:.1f} (neutral)")
        
        if "market_structure" in tool_results:
            structure = tool_results["market_structure"]
            trend = structure.get("trend", "ranging")
            conditions_total += 1
            
            if (strategy_result.action == "BUY" and trend == "bullish") or \
               (strategy_result.action == "SELL" and trend == "bearish"):
                conditions_met += 1
                reasoning_steps.append(f"✅ Market structure: {trend.upper()} trend confirmed")
            else:
                reasoning_steps.append(f"⚠️ Market structure: {trend.upper()} (caution)")
        
        # Final decision
        if strategy_result.action != "HOLD":
            reasoning_steps.append(
                f"\n🎯 {strategy_result.action} SIGNAL: "
                f"{conditions_met}/{conditions_total} conditions met "
                f"({strategy_result.confidence * 100:.0f}% confidence)"
            )
        else:
            reasoning_steps.append(
                f"\n⏸️ HOLD: Conditions not met ({conditions_met}/{conditions_total})"
            )
        
        return {
            "action": strategy_result.action,
            "entry_price": strategy_result.entry_price,
            "stop_loss": strategy_result.stop_loss,
            "take_profit": strategy_result.take_profit,
            "confidence": strategy_result.confidence,
            "pattern": strategy_result.pattern_detected,
            "reasoning": strategy_result.reasoning,
            "reasoning_steps": reasoning_steps,
            "conditions_met": conditions_met,
            "conditions_total": conditions_total,
            "instructions": instructions,
            "summary": {
                "title": f"{strategy_result.action} Signal - ICT Strategy",
                "subtitle": self._generate_subtitle(tool_results),
                "confidence_score": int(strategy_result.confidence * 100),
                "conditions_met": conditions_met,
                "conditions_total": conditions_total
            }
        }
    
    @staticmethod
    def add_post_trade_annotations(
        chart_data: Dict[str, Any],
        trade_execution: Optional[Dict[str, Any]],
        trade_outcome: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Add post-trade markers (fill price, exit price) to existing chart data.

        Args:
            chart_data: Existing chart data with annotations
            trade_execution: Trade execution data with filled_price
            trade_outcome: Trade outcome data with exit_price, pnl, exit_reason

        Returns:
            Enriched chart data with post-trade annotations
        """
        if not chart_data or "annotations" not in chart_data:
            return chart_data

        annotations = chart_data["annotations"]
        candles = chart_data.get("candles", [])
        latest_time = candles[-1].get("time") if candles else None

        # Fill price marker
        if trade_execution and trade_execution.get("filled_price"):
            filled_price = trade_execution["filled_price"]

            annotations["markers"].append({
                "time": latest_time,
                "price": filled_price,
                "position": "aboveBar",
                "color": "#eab308",
                "shape": "diamond",
                "size": "large",
                "text": f"FILL @ ${filled_price:.2f}",
                "tooltip": (
                    f"Order filled at ${filled_price:.2f}\n"
                    f"Qty: {trade_execution.get('filled_quantity', 'N/A')}"
                ),
            })

            annotations["lines"].append({
                "type": "horizontal",
                "price": filled_price,
                "color": "#eab308",
                "width": 1,
                "style": "dashed",
                "label": {
                    "text": f"Fill: ${filled_price:.2f}",
                    "position": "right",
                    "color": "#eab308",
                },
                "tooltip": f"Actual fill price: ${filled_price:.2f}",
            })

        # Exit price marker
        if trade_outcome and trade_outcome.get("exit_price"):
            exit_price = trade_outcome["exit_price"]
            pnl = trade_outcome.get("pnl", 0)
            exit_reason = trade_outcome.get("exit_reason", "closed")
            is_profit = pnl >= 0 if pnl is not None else True
            color = "#22c55e" if is_profit else "#ef4444"

            annotations["markers"].append({
                "time": latest_time,
                "price": exit_price,
                "position": "belowBar" if is_profit else "aboveBar",
                "color": color,
                "shape": "square",
                "size": "large",
                "text": f"EXIT @ ${exit_price:.2f} ({exit_reason})",
                "tooltip": (
                    f"Exit at ${exit_price:.2f}\n"
                    f"P&L: ${pnl:.2f}\n"
                    f"Reason: {exit_reason}"
                ),
            })

        return chart_data

    def _generate_subtitle(self, tool_results: Dict[str, Any]) -> str:
        """Generate a subtitle based on which tools were used."""
        tools_used = []
        
        if "fvg_detector" in tool_results:
            tools_used.append("FVG")
        if "premium_discount" in tool_results:
            tools_used.append("Zones")
        if "liquidity_analyzer" in tool_results:
            tools_used.append("Liquidity")
        if "market_structure" in tool_results:
            tools_used.append("Structure")
        if "rsi" in tool_results:
            tools_used.append("RSI")
        if "macd" in tool_results:
            tools_used.append("MACD")
        
        if len(tools_used) == 0:
            return "Price Action Strategy"
        elif len(tools_used) <= 3:
            return " + ".join(tools_used) + " Confluence"
        else:
            return f"Multi-Factor Analysis ({len(tools_used)} indicators)"

