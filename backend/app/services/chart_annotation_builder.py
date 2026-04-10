"""
Chart Annotation Builder - Converts tool results into visual chart annotations

This service transforms ICT tool results (FVGs, liquidity, structure, etc.) into
a structured format that can be rendered on TradingView charts.
"""
import structlog
from typing import List, Dict, Any, Optional, Tuple
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
        trade_relevance = self._derive_trade_relevance(
            tool_results=tool_results,
            strategy_result=strategy_result,
            instructions=instructions,
        )

        # Build annotations from tool results
        annotations = {
            "shapes": [],      # Rectangles, circles, etc.
            "lines": [],       # Horizontal/vertical lines
            "arrows": [],      # Directional arrows
            "markers": [],     # Point markers (entry, exit)
            "zones": [],       # Shaded areas (premium/discount)
            "text": [],        # Text labels
            "position": None   # Structured trade position (entry/SL/TP)
        }
        
        # Keep only trade-relevant evidence on the chart. Broad context like
        # liquidity maps or premium/discount zones stays in reasoning, not visuals.
        self._add_relevant_fvg_annotations(annotations, trade_relevance["relevant_fvgs"])
        self._add_relevant_swing_annotations(annotations, trade_relevance["relevant_swings"])
        
        # Add trade decision markers
        self._add_trade_annotations(annotations, strategy_result, candles)
        
        # Build indicator data
        indicators = self._build_indicator_data(
            tool_results,
            trade_relevance["indicator_keys"],
        )
        
        # Build decision summary
        decision_summary = self._build_decision_summary(
            strategy_result,
            tool_results,
            instructions,
            trade_relevance,
        )
        
        chart_data = {
            "meta": {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "generated_at": datetime.utcnow().isoformat(),
                "candle_count": len(candles),
                "trade_relevance": trade_relevance["summary"],
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
    
    def _add_relevant_fvg_annotations(self, annotations: Dict, fvgs: List[Dict[str, Any]]) -> None:
        """Add only the FVGs directly tied to the trade thesis."""
        for fvg in fvgs:
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
                ),
                "relevance": "trade_entry_context",
            })

    def _add_relevant_swing_annotations(
        self,
        annotations: Dict,
        swings: List[Dict[str, Any]],
    ) -> None:
        """Add only swing points used for stop placement or target placement."""
        for swing in swings:
            role = swing.get("role", "swing")
            is_target = role == "target"
            color = "#22c55e" if is_target else "#ef4444"
            direction = "sell" if is_target else "buy"
            label = "Target Swing" if is_target else "Stop Swing"
            annotations["markers"].append({
                "time": swing.get("timestamp"),
                "price": swing["price"],
                "direction": direction,
                "text": label,
                "color": color,
                "role": role,
                "relevance": "trade_level_anchor",
            })

            annotations["lines"].append({
                "type": "horizontal",
                "price": swing["price"],
                "color": color,
                "width": 1,
                "style": "dotted",
                "label": {
                    "text": label,
                    "position": "right",
                    "color": color,
                },
                "relevance": "trade_level_anchor",
                "tooltip": f"{label} @ ${swing['price']:.2f}",
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

            # Structured position object for TradingView position/order lines
            annotations["position"] = {
                "action": strategy_result.action,
                "entry_price": strategy_result.entry_price,
                "stop_loss": strategy_result.stop_loss,
                "take_profit": strategy_result.take_profit,
                "confidence": strategy_result.confidence,
                "pattern": strategy_result.pattern_detected,
                "risk": round(risk, 5),
                "reward": round(reward, 5),
                "rr_ratio": round(rr_ratio, 2),
                "position_size": strategy_result.position_size,
            }
    
    def _build_indicator_data(
        self,
        tool_results: Dict[str, Any],
        indicator_keys: List[str],
    ) -> Dict[str, Any]:
        """Build indicator subplot data."""
        indicators = {}
        
        # RSI
        if "rsi" in indicator_keys and "rsi" in tool_results:
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
        if "macd" in indicator_keys and "macd" in tool_results:
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
        instructions: Optional[str],
        trade_relevance: Dict[str, Any],
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
                "subtitle": self._generate_subtitle(trade_relevance["summary"]["tools_used"]),
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

    def _generate_subtitle(self, tools_used: List[str]) -> str:
        """Generate a subtitle based on the evidence actually kept on the chart."""
        if len(tools_used) == 0:
            return "Trade Levels Focus"
        elif len(tools_used) <= 3:
            return " + ".join(tools_used) + " Used In Trade"
        else:
            return f"Trade Evidence ({len(tools_used)} factors)"

    def _derive_trade_relevance(
        self,
        tool_results: Dict[str, Any],
        strategy_result: StrategyResult,
        instructions: Optional[str],
    ) -> Dict[str, Any]:
        action = (strategy_result.action or "").upper()
        reasoning = (strategy_result.reasoning or "").lower()
        instructions_lower = (instructions or "").lower()

        relevant_fvgs = self._select_relevant_fvgs(tool_results.get("fvg_detector", {}), strategy_result)
        relevant_swings = self._select_relevant_swings(tool_results.get("market_structure", {}), strategy_result)
        indicator_keys = self._select_indicator_keys(tool_results, instructions_lower, reasoning)

        tools_used: List[str] = []
        if relevant_fvgs:
            tools_used.append("FVG")
        if relevant_swings:
            tools_used.append("Swing Levels")
        if "rsi" in indicator_keys:
            tools_used.append("RSI")
        if "macd" in indicator_keys:
            tools_used.append("MACD")

        if action in {"BUY", "SELL"} and not tools_used:
            tools_used.append("Trade Levels")

        return {
            "relevant_fvgs": relevant_fvgs,
            "relevant_swings": relevant_swings,
            "indicator_keys": indicator_keys,
            "summary": {
                "tools_used": tools_used,
                "fvg_count": len(relevant_fvgs),
                "swing_count": len(relevant_swings),
                "indicator_count": len(indicator_keys),
            },
        }

    def _select_indicator_keys(
        self,
        tool_results: Dict[str, Any],
        instructions: str,
        reasoning: str,
    ) -> List[str]:
        keys: List[str] = []
        if "rsi" in tool_results and ("rsi" in instructions or "rsi" in reasoning):
            keys.append("rsi")
        if "macd" in tool_results and ("macd" in instructions or "macd" in reasoning):
            keys.append("macd")
        return keys

    def _select_relevant_fvgs(
        self,
        fvg_result: Dict[str, Any],
        strategy_result: StrategyResult,
    ) -> List[Dict[str, Any]]:
        action = (strategy_result.action or "").upper()
        entry = strategy_result.entry_price
        if action not in {"BUY", "SELL"} or not entry:
            return []

        desired_type = "bullish" if action == "BUY" else "bearish"
        fvgs = [f for f in fvg_result.get("fvgs", []) if f.get("type") == desired_type]
        if not fvgs:
            return []

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for fvg in fvgs:
            low = float(fvg["low"])
            high = float(fvg["high"])
            midpoint = (low + high) / 2
            distance = min(abs(entry - low), abs(entry - high), abs(entry - midpoint))
            score = -distance
            if low <= entry <= high:
                score += 1000
            if not fvg.get("is_filled"):
                score += 25
            score -= float(fvg.get("fill_percentage", 0)) * 0.1
            scored.append((score, fvg))

        scored.sort(key=lambda item: item[0], reverse=True)
        best = scored[0][1]
        tolerance = self._price_tolerance(strategy_result)
        if min(abs(entry - best["low"]), abs(entry - best["high"]), abs(entry - ((best["low"] + best["high"]) / 2))) > tolerance:
            return []
        return [best]

    def _select_relevant_swings(
        self,
        structure_result: Dict[str, Any],
        strategy_result: StrategyResult,
    ) -> List[Dict[str, Any]]:
        action = (strategy_result.action or "").upper()
        if action not in {"BUY", "SELL"}:
            return []

        swings: List[Dict[str, Any]] = []
        tolerance = self._price_tolerance(strategy_result) * 1.5
        stop = strategy_result.stop_loss
        target = strategy_result.take_profit

        stop_candidates = structure_result.get("swing_lows" if action == "BUY" else "swing_highs", [])
        target_candidates = structure_result.get("swing_highs" if action == "BUY" else "swing_lows", [])

        stop_swing = self._closest_swing(stop_candidates, stop, tolerance)
        if stop_swing:
            swings.append({**stop_swing, "role": "stop"})

        target_swing = self._closest_swing(target_candidates, target, tolerance)
        if target_swing:
            swings.append({**target_swing, "role": "target"})

        return swings

    def _closest_swing(
        self,
        swings: List[Dict[str, Any]],
        reference_price: Optional[float],
        tolerance: float,
    ) -> Optional[Dict[str, Any]]:
        if not reference_price or not swings:
            return None

        best = min(swings, key=lambda swing: abs(float(swing["price"]) - reference_price))
        if abs(float(best["price"]) - reference_price) > tolerance:
            return None
        return best

    def _price_tolerance(self, strategy_result: StrategyResult) -> float:
        entry = float(strategy_result.entry_price or 0)
        stop = float(strategy_result.stop_loss or entry)
        target = float(strategy_result.take_profit or entry)
        risk = abs(entry - stop)
        reward = abs(target - entry)
        return max(risk, reward, max(entry * 0.0025, 0.15))
