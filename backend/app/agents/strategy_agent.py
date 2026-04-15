"""
Strategy Agent V2 - Instruction-driven trade strategy generation

This agent reads natural language instructions and automatically uses appropriate tools
to generate trading strategies.
"""
import structlog
import json
import re
from typing import Dict, Any, List, Optional, Tuple

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.agents.prompts import load_kb_context, load_prompt
from app.schemas.pipeline_state import PipelineState, StrategyResult, AgentMetadata, AgentConfigSchema
from app.services.langfuse_service import trace_agent_execution
from app.tools.openai_tools import build_openai_tools
from app.services.chart_annotation_builder import ChartAnnotationBuilder
from app.services.model_registry import model_registry
from app.services.agent_runner import AgentRunner
from app.services.llm_provider import create_openai_client, get_llm_provider, resolve_chat_model
from app.config import settings
from app.database import SessionLocal
from app.services.skill_registry import skill_registry

logger = structlog.get_logger()


class StrategyAgent(BaseAgent):
    """
    Strategy Agent - Generates trade strategies using LLM + tools
    
    This agent is instruction-driven: it reads natural language instructions
    and automatically selects appropriate tools to generate trading strategies.
    
    Example Instructions:
        "Look for bull flag patterns on 5m timeframe. Enter on breakout with 2:1 R/R"
        "Trade FVG imbalances. Wait for price to fill the gap then enter in direction of trend"
        "Use RSI oversold/overbought with support/resistance for entries"
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        db = SessionLocal()
        try:
            model_choices = model_registry.get_model_choices_for_schema(db)
        except Exception:
            logger.warning("strategy_agent_model_choices_fallback", exc_info=True)
            model_choices = ["gpt-4o"]
        finally:
            db.close()

        return AgentMetadata(
            agent_type="strategy_agent",
            name="AI Strategy Agent",
            description="Generates trading strategies using AI analysis and technical tools",
            category="analysis",
            version="2.0.0",
            icon="psychology",
            pricing_rate=0.15,
            is_free=False,
            requires_timeframes=["5m"],  # Always need 5m for intraday analysis
            supported_tools=[
                # Analysis tools - Strategy Agent can use any technical indicator
                "rsi", "macd", "sma_crossover", "bollinger_bands",
                "fvg_detector", "order_block_detector", "session_context_analyzer",
                "liquidity_analyzer", "market_structure", "premium_discount"
            ],
            default_tools=[
                "fvg_detector", "liquidity_analyzer", "market_structure_analyzer",
                "premium_discount_analyzer", "rsi_calculator", "macd_calculator", "sma_crossover"
            ],
            supports_skills=True,
            supported_skill_categories=["ict", "bias", "confluence"],
            config_schema=AgentConfigSchema(
                type="object",
                title="Strategy Agent Configuration",
                properties={
                    "instructions": {
                        "type": "string",
                        "title": "Strategy Instructions",
                        "description": "Natural language instructions for generating trade strategies. Specify the timeframe(s) you want to analyze (e.g., '5m', '15m', '1h').",
                        "default": "Analyze the 5m chart and identify high-probability trade setups. Look for clear patterns (flags, triangles, FVGs) with defined support/resistance. Generate BUY or SELL signals with specific entry, stop loss, and take profit levels."
                    },
                    "model": {
                        "type": "string",
                        "title": "AI Model",
                        "description": "LLM model to use from the configured provider",
                        "enum": model_choices,
                        "default": "gpt-4o" if "gpt-4o" in model_choices else (model_choices[0] if model_choices else "gpt-4o")
                    }
                },
                required=["instructions"]
            ),
            can_initiate_trades=True,
            can_close_positions=False
        )

    def __init__(self, agent_id: str, config: Dict[str, Any]):
        super().__init__(agent_id, config)

        model_name = config.get("model", settings.OPENAI_MODEL)
        self.logger.info(
            "using_llm_provider provider=%s model=%s",
            get_llm_provider(),
            model_name,
        )
        self.model = model_name
        self.runner = AgentRunner(model=model_name, temperature=0.7, timeout=45)
    
    def process(self, state: PipelineState) -> PipelineState:
        """Generate trading strategy using LLM + tools."""
        
        trace = trace_agent_execution(
            execution_id=str(state.execution_id),
            agent_type=self.metadata.agent_type,
            agent_id=self.agent_id,
            pipeline_id=str(state.pipeline_id),
            user_id=str(state.user_id),
        )
        
        self.log(state, "Starting strategy generation with instruction-driven approach")
        
        if not self.validate_input(state):
            raise InsufficientDataError("Strategy agent requires market data")
        
        # ── Deterministic regime + setup evaluation (TP-006/TP-007/TP-011) ──
        # Run before the LLM so the LLM receives the deterministic spec as context
        # and is used only for explanation/ranking, not for mechanical decisions.
        det_spec = self._run_deterministic_evaluation(state)
        if det_spec is not None:
            self.log(
                state,
                f"🎯 Deterministic setup found: {det_spec.strategy_family} "
                f"→ {det_spec.action} (confidence={det_spec.confidence:.2f})"
            )

        # CHECK BIAS: If bias is NEUTRAL and no deterministic setup fired, skip strategy
        if state.biases:
            preferred_tf = state.timeframes[0] if getattr(state, "timeframes", None) else None
            bias = state.biases.get(preferred_tf) if preferred_tf else None
            if not bias:
                bias = next(iter(state.biases.values()), None)

            if bias and bias.bias == "NEUTRAL" and det_spec is None:
                self.log(state, "⚠️  Bias is NEUTRAL and no deterministic setup — HOLD")

                state.strategy = StrategyResult(
                    action="HOLD",
                    confidence=0.0,
                    entry_price=state.market_data.current_price if state.market_data else 0.0,
                    stop_loss=None,
                    take_profit=None,
                    position_size=None,
                    reasoning=(
                        f"**Market Bias: NEUTRAL**\n\n"
                        f"No strategy generated because the bias analysis determined the market is NEUTRAL "
                        f"with {bias.confidence:.0%} confidence, and no deterministic setup qualified.\n\n"
                        f"**Bias Reasoning:**\n{bias.reasoning}\n\n"
                        f"**Action:** HOLD and wait for a clear directional bias or a setup signal."
                    ),
                    pattern_detected="",
                )

                self.record_report(
                    state,
                    title="Strategy Decision",
                    summary="HOLD - Market bias is NEUTRAL, no setup found",
                    status="completed",
                    data={
                        "Decision": "HOLD",
                        "Reason": "Bias NEUTRAL + no deterministic setup",
                        "Bias Confidence": f"{bias.confidence:.0%}",
                    },
                )

                self.log(state, "✓ Strategy: HOLD (bias NEUTRAL, no setup)")
                return state
        
        try:
            # Get configuration
            instructions = self.config.get("instructions", "").strip()
            if not instructions:
                instructions = self.metadata.config_schema.properties["instructions"]["default"]
            
            # Parse timeframe from instructions (instruction-driven!)
            from app.services.instruction_parser import instruction_parser
            extracted_timeframes = instruction_parser.extract_timeframes(instructions)
            
            # Use the smallest (fastest) timeframe as primary execution timeframe
            # If none specified in instructions, use the smallest AVAILABLE timeframe
            if extracted_timeframes:
                strategy_tf = extracted_timeframes[0]
            elif state.market_data and state.market_data.timeframes:
                # Use smallest available timeframe from state
                available_tfs = sorted(state.market_data.timeframes.keys(), 
                                      key=lambda x: instruction_parser._timeframe_to_minutes(x))
                strategy_tf = available_tfs[0] if available_tfs else "1d"
            else:
                strategy_tf = "1d"  # Final fallback
            
            self.log(state, f"Strategy timeframe (from instructions): {strategy_tf}")
            if extracted_timeframes:
                self.log(state, f"All timeframes: {extracted_timeframes}")
            self.log(state, f"Using instructions: {instructions[:100]}...")
            
            # Determine if this is a forex pair (needs 5 decimal precision for pips)
            is_forex = '_' in state.symbol  # EUR_USD, GBP_USD, etc.
            price_precision = 5 if is_forex else 2
            
            # Get safe current price
            safe_current_price = (
                float(state.market_data.current_price)
                if state.market_data and state.market_data.current_price is not None
                else 0.0
            )
            
            # Prepare context with proper precision
            market_context = self._prepare_market_context(state, strategy_tf, price_precision)
            bias_context = self._prepare_bias_context(state)
            
            # Get candle data for tools that need it
            candles = state.get_timeframe_data(strategy_tf)

            # Fallback: if exact timeframe not found, try all available timeframes
            if not candles and state.market_data and state.market_data.timeframes:
                available_tfs = list(state.market_data.timeframes.keys())
                self.log(state, f"No candles for '{strategy_tf}', available timeframes: {available_tfs}")
                for tf_key in available_tfs:
                    tf_data = state.market_data.timeframes[tf_key]
                    if tf_data and len(tf_data) > 0:
                        candles = tf_data
                        self.log(state, f"Using fallback timeframe '{tf_key}' with {len(candles)} candles")
                        break

            candle_dicts = [
                {
                    "timestamp": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume
                }
                for c in candles
            ] if candles else []

            manual_tool_map = {
                "rsi": "rsi_calculator",
                "macd": "macd_calculator",
                "market_structure": "market_structure_analyzer",
                "premium_discount": "premium_discount_analyzer",
            }
            manual_runtime_tools = [
                manual_tool_map.get(tool.get("tool_type"), tool.get("tool_type"))
                for tool in self.config.get("tools", [])
                if tool.get("enabled", True) and tool.get("tool_type")
            ]
            resolved_skills = skill_registry.resolve_for_agent(
                agent_type=self.metadata.agent_type,
                attachments=self.config.get("skills", []),
                base_runtime_tools=list(dict.fromkeys(self.get_metadata().default_tools + manual_runtime_tools)),
            )
            if resolved_skills["skills"]:
                self.log(
                    state,
                    "Active skills: " + ", ".join(skill.name for skill in resolved_skills["skills"]),
                )

            # Load base tools plus any skill-recommended runtime tools.
            tools = build_openai_tools(
                resolved_skills["runtime_tools"],
                ticker=state.symbol,
                candles=candle_dicts if candle_dicts else None
            )

            self.log(state, f"Available tools ({len(tools)}): {[t.name for t in tools]}, candles: {len(candle_dicts)}")
            
            # STAGE 1: Call tools directly to get analysis data
            tool_results_text, tool_results_data = self._call_tools_and_format(tools, state, candle_dicts, price_precision)
            
            # STAGE 2: Run a single direct LLM call using the precomputed tool output.
            skill_prompt = ""
            if resolved_skills["instruction_fragments"]:
                skill_prompt = "\n\nACTIVE SKILLS:\n- " + "\n- ".join(resolved_skills["instruction_fragments"])

            kb_context = load_kb_context(self.metadata.agent_type)
            kb_prompt = f"{kb_context}\n\n" if kb_context else ""

            system_prompt = kb_prompt + load_prompt("strategy_agent_system") + skill_prompt + f"""

You are executing a trade strategy for {state.symbol}.

CORE PRINCIPLES:
1. You follow user instructions LITERALLY - if they say "enter anytime", you enter without complex analysis
2. You USE THE PROVIDED BIAS - do NOT re-analyze or invent your own bias, use what's given in "Market Bias" section
3. You ALWAYS provide all three prices: entry, stop loss, AND take profit (never leave any blank)
4. You format output as valid JSON only
5. You keep reasoning concise unless user asks for detailed analysis

Your job is to EXECUTE the user's strategy using the data provided, not second-guess it or re-analyze the market."""

            user_prompt = f"""Execute the following trading strategy for {state.symbol}.

═══════════════════════════════════════════════════════════
USER'S TRADING INSTRUCTIONS:
═══════════════════════════════════════════════════════════
{instructions}

═══════════════════════════════════════════════════════════
MARKET DATA (for your reference):
═══════════════════════════════════════════════════════════
Symbol: {state.symbol}
Timeframe: {strategy_tf}
Current Price: {safe_current_price:.{price_precision}f}
Asset Type: {'FOREX (1 pip = 0.0001)' if is_forex else 'STOCK/CRYPTO'}

{market_context}

Bias: {bias_context}

Technical Analysis:
{tool_results_text}

Attached Skills:
{', '.join(skill.skill_id for skill in resolved_skills['skills']) if resolved_skills['skills'] else 'None'}

═══════════════════════════════════════════════════════════
YOUR TASK:
═══════════════════════════════════════════════════════════
Read the user's instructions above and execute them.
- Use the BIAS shown above (do NOT re-analyze to determine bias)
- If user wants simple entries, keep it simple
- If user wants detailed analysis, provide detailed analysis
- ALWAYS provide entry_price, stop_loss, AND take_profit (never leave any blank)

{'CRITICAL FOREX PIP CALCULATIONS:' if is_forex else ''}
{'''1 pip = 0.0001
10 pips = 10 × 0.0001 = 0.0010
20 pips = 20 × 0.0001 = 0.0020
100 pips = 100 × 0.0001 = 0.0100

For SELL: stop_loss = entry + (pips × 0.0001), take_profit = entry - (pips × 0.0001)
For BUY: stop_loss = entry - (pips × 0.0001), take_profit = entry + (pips × 0.0001)''' if is_forex else ''}

CRITICAL: Your FINAL response must be ONLY a valid JSON object, nothing else.

═══════════════════════════════════════════════════════════
OUTPUT FORMAT (CRITICAL):
═══════════════════════════════════════════════════════════
Respond with ONLY a valid JSON object. No other text.

JSON STRUCTURE:
{{
    "action": "BUY|SELL|HOLD",
    "entry_price": <number>,
    "stop_loss": <number>,
    "take_profit": <number>,
    "confidence": <0.0-1.0>,
    "pattern_detected": "pattern name or leave empty if not applicable",
    "reasoning": "Your explanation as a single quoted string. Keep it concise unless user asks for detailed analysis."
}}

JSON RULES:
- ALL prices must be numbers (not strings)
- "reasoning" is a single JSON string (use \\n for line breaks)
- NEVER leave entry_price, stop_loss, or take_profit blank/null
- Calculate stop_loss and take_profit using the pip values from user instructions

Remember: Follow the user's instructions literally. Keep reasoning brief unless they ask for detailed analysis."""
            
            self.log(state, "Executing strategy generation...")
            final_output = self.runner.run(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                trace=trace,
                max_iterations=1,
            ).content
            
            # Log raw result for debugging
            self.log(state, f"📝 Raw LLM result length: {len(final_output)} characters")
            self.log(state, f"📝 Raw LLM result preview: {final_output[:500]}...")
            
            # Use final_output for parsing
            result = final_output
            
            # Parse result
            strategy_result = self._parse_strategy_result(result, state)
            
            # Log parsed reasoning
            self.log(state, f"📝 Parsed reasoning length: {len(strategy_result.reasoning)} characters")
            self.log(state, f"📝 Parsed reasoning preview: {strategy_result.reasoning[:200] if strategy_result.reasoning else 'EMPTY'}")
            
            # Update state
            state.strategy = strategy_result

            # Attach deterministic spec if one was found (TP-011).
            # When a deterministic spec exists and conflicts with the LLM:
            #   - use deterministic price levels (reproducible, trusted)
            #   - keep LLM reasoning for explanation value
            if det_spec is not None:
                state.strategy.strategy_spec = det_spec
                if det_spec.action != "HOLD":
                    # Override mechanical levels with deterministic values
                    state.strategy.entry_price = det_spec.entry_price or state.strategy.entry_price
                    state.strategy.stop_loss   = det_spec.stop_loss   or state.strategy.stop_loss
                    state.strategy.take_profit = det_spec.take_profit or state.strategy.take_profit
                    state.strategy.action      = det_spec.action
                    self.log(state, f"🎯 Deterministic levels applied from {det_spec.strategy_family}")

            self.log(
                state,
                f"✓ Strategy: {strategy_result.action} @ ${strategy_result.entry_price:.2f} "
                f"(confidence: {strategy_result.confidence:.0%})"
            )

            # Record structured report for UI (executive + drill-down)
            reasoning = getattr(strategy_result, "reasoning", "No detailed analysis provided.")
            pattern = getattr(strategy_result, "pattern_detected", "")
            
            # Use LLM synthesis to clean reasoning (falls back to regex if needed)
            formatted_reasoning = self._synthesize_reasoning_with_llm(reasoning)
            
            # Build human-readable summary
            action_text = f"**Decision:** {strategy_result.action}"
            confidence_text = f"**Confidence:** {strategy_result.confidence:.0%}"
            
            trade_levels = []
            if strategy_result.entry_price:
                trade_levels.append(f"**Entry:** ${strategy_result.entry_price:.{price_precision}f}")
            if strategy_result.stop_loss:
                trade_levels.append(f"**Stop Loss:** ${strategy_result.stop_loss:.{price_precision}f}")
            if strategy_result.take_profit:
                trade_levels.append(f"**Take Profit:** ${strategy_result.take_profit:.{price_precision}f}")
            
            # Calculate risk/reward if we have levels
            rr_text = ""
            if strategy_result.entry_price and strategy_result.stop_loss and strategy_result.take_profit:
                risk = abs(strategy_result.entry_price - strategy_result.stop_loss)
                reward = abs(strategy_result.take_profit - strategy_result.entry_price)
                if risk > 0:
                    rr_ratio = reward / risk
                    rr_text = f"\n**Risk/Reward Ratio:** {rr_ratio:.2f}:1"
            
            report_data = {
                "Decision": strategy_result.action,
                "Confidence": f"{strategy_result.confidence:.0%}",
                "Timeframe": strategy_tf,
            }
            
            if pattern:
                report_data["Pattern Detected"] = pattern
            
            if trade_levels:
                report_data["Trade Levels"] = " | ".join(trade_levels)
            
            # Add formatted reasoning as the main content
            report_data["Analysis & Reasoning"] = formatted_reasoning
            
            self.record_report(
                state,
                title="Strategy Decision",
                summary=(
                    f"{strategy_result.action} {state.symbol} "
                    f"(confidence {strategy_result.confidence:.0%})"
                ),
                data=report_data,
            )
            
            # Generate chart visualization
            self.log(state, "Generating strategy chart visualization...")
            try:
                chart_builder = ChartAnnotationBuilder(
                    symbol=state.symbol,
                    timeframe=strategy_tf
                )
                
                if candle_dicts:
                    # Build chart from tool results
                    chart_data = chart_builder.build_chart_data(
                        candles=candle_dicts,
                        tool_results=tool_results_data,
                        strategy_result=strategy_result,
                        instructions=instructions
                    )
                    
                    state.execution_artifacts["strategy_chart"] = chart_data
                    
                    total = sum(
                        len(chart_data['annotations'].get(k, []))
                        for k in ['shapes', 'lines', 'markers', 'zones', 'text', 'arrows']
                    )
                    self.log(state, f"✓ Chart generated with {total} annotations")
                else:
                    self.add_warning(state, f"Chart generation skipped - no candle data available for {strategy_tf} timeframe. Ensure Market Data Agent is configured to fetch this timeframe.")
                    
            except Exception as e:
                self.add_warning(state, f"Chart generation failed: {str(e)}")
            
            # Track cost using model registry
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                model_id = self.config.get("model", "gpt-4")
                # Base cost for strategy agent (chart generation, etc.)
                base_cost = 0.02
                # Calculate total cost based on model
                total_cost = model_registry.calculate_agent_cost(
                    model_id=model_id,
                    db=db,
                    base_cost=base_cost,
                    estimated_input_tokens=1500,  # Typical strategy prompt
                    estimated_output_tokens=500   # Typical strategy response
                )
                self.track_cost(state, total_cost)
                # Prometheus metrics
                from app.telemetry import llm_calls_total, llm_tokens_total, llm_cost_dollars
                llm_calls_total.labels(model=model_id, agent_type="strategy_agent").inc()
                llm_tokens_total.labels(model=model_id, direction="input").inc(1500)
                llm_tokens_total.labels(model=model_id, direction="output").inc(500)
                llm_cost_dollars.labels(model=model_id, agent_type="strategy_agent").inc(total_cost)
            finally:
                db.close()

            return state
            
        except Exception as e:
            error_msg = f"Strategy generation failed: {str(e)}"
            self.add_error(state, error_msg)
            logger.exception("strategy_agent_failed", error=str(e))
            raise AgentProcessingError(error_msg) from e
    
    def _select_relevant_tools(self, instructions: str, available_tool_names: set) -> set:
        """
        Match instruction keywords against each tool's strategy_keywords in the registry
        to select only the tools relevant to the user's strategy.

        Falls back to a safe default set (fvg_detector + market_structure_analyzer) when
        no keywords match, so the agent always has something to work with.
        """
        from app.tools.strategy_tools_registry import STRATEGY_TOOL_REGISTRY

        # Registry keys differ from CrewAI tool names for two ICT tools — map them here.
        REGISTRY_TO_CREWAI: Dict[str, str] = {
            "fvg_detector": "fvg_detector",
            "order_block_detector": "order_block_detector",
            "session_context_analyzer": "session_context_analyzer",
            "liquidity_analyzer": "liquidity_analyzer",
            "market_structure": "market_structure_analyzer",
            "premium_discount": "premium_discount_analyzer",
        }

        instructions_lower = instructions.lower()
        matched: set = set()

        for registry_key, crewai_name in REGISTRY_TO_CREWAI.items():
            if crewai_name not in available_tool_names:
                continue
            spec = STRATEGY_TOOL_REGISTRY.get(registry_key, {})
            keywords = spec.get("strategy_keywords", [])
            if any(kw in instructions_lower for kw in keywords):
                matched.add(crewai_name)

        if not matched:
            # No keywords matched — use defaults to prevent empty analysis
            defaults = {"fvg_detector", "market_structure_analyzer"} & available_tool_names
            logger.info("no_tool_keywords_matched", defaults=sorted(defaults))
            return defaults

        logger.info("instruction_matched_tools", tools=sorted(matched))
        return matched

    def _call_tools_and_format(self, tools: List[Any], state: PipelineState, candles: List[Dict], price_precision: int = 2) -> Tuple[str, Dict[str, Any]]:
        """Call tools directly and format their results as text for the LLM prompt.

        Returns:
            Tuple of (formatted_text_for_llm, structured_tool_results_for_chart)
        """
        import asyncio
        from app.tools.strategy_tools.fvg_detector import FVGDetector
        from app.tools.strategy_tools.liquidity_analyzer import LiquidityAnalyzer
        from app.tools.strategy_tools.market_structure import MarketStructureAnalyzer
        from app.tools.strategy_tools.order_block_detector import OrderBlockDetector
        from app.tools.strategy_tools.premium_discount import PremiumDiscountAnalyzer
        from app.tools.strategy_tools.session_context_analyzer import SessionContextAnalyzer

        collected_results: Dict[str, Any] = {}

        if not tools or not candles:
            text = self._compute_technical_analysis(state, candles, price_precision)
            # Still compute indicators even without tools
            collected_results.update(
                self._compute_indicator_results(candles, self.config.get("instructions", ""))
            )
            return text, collected_results

        results_lines = []
        tool_names = {t.name for t in tools}

        # Select only tools relevant to the user's instructions
        instructions = self.config.get("instructions", "")
        relevant_tool_names = self._select_relevant_tools(instructions, tool_names)
        self.log(state, f"Tools selected for instructions: {sorted(relevant_tool_names)}")

        # Helper to run async tool functions synchronously
        def _run_async(coro):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        # Call ICT tools directly (bypassing CrewAI wrappers for structured dict results)
        if "fvg_detector" in relevant_tool_names:
            try:
                self.log(state, "Calling tool: fvg_detector")
                detector = FVGDetector(timeframe="5m", min_gap_pips=5)
                result = _run_async(detector.detect(candles))
                if result and isinstance(result, dict):
                    fvgs = result.get("fvgs", [])
                    bullish_fvgs = [f for f in fvgs if f.get("type") == "bullish"]
                    bearish_fvgs = [f for f in fvgs if f.get("type") == "bearish"]

                    results_lines.append(f"\n**FVG ANALYSIS:**")
                    if bullish_fvgs:
                        for fvg in bullish_fvgs[:3]:
                            status = "filled" if fvg.get("is_filled") else "tapped" if fvg.get("is_tapped") else "untapped"
                            results_lines.append(f"  • Bullish FVG: ${fvg['low']:.{price_precision}f} - ${fvg['high']:.{price_precision}f} ({status})")
                    if bearish_fvgs:
                        for fvg in bearish_fvgs[:3]:
                            status = "filled" if fvg.get("is_filled") else "tapped" if fvg.get("is_tapped") else "untapped"
                            results_lines.append(f"  • Bearish FVG: ${fvg['low']:.{price_precision}f} - ${fvg['high']:.{price_precision}f} ({status})")
                    if not bullish_fvgs and not bearish_fvgs:
                        results_lines.append(f"  • No significant FVGs detected")

                    collected_results["fvg_detector"] = result
                    self.log(state, f"FVG detector found {len(fvgs)} FVGs ({len(bullish_fvgs)} bullish, {len(bearish_fvgs)} bearish)")
            except Exception as e:
                self.log(state, f"Tool fvg_detector failed: {str(e)}")

        if "order_block_detector" in relevant_tool_names:
            try:
                self.log(state, "Calling tool: order_block_detector")
                detector = OrderBlockDetector(timeframe="5m", min_move_pips=10)
                result = _run_async(detector.detect(candles))
                if result and isinstance(result, dict):
                    blocks = result.get("order_blocks", [])
                    bullish_blocks = [b for b in blocks if b.get("type") == "bullish"]
                    bearish_blocks = [b for b in blocks if b.get("type") == "bearish"]

                    results_lines.append("\n**ORDER BLOCK ANALYSIS:**")
                    if bullish_blocks:
                        for block in bullish_blocks[:3]:
                            results_lines.append(
                                f"  • Bullish OB: ${block['low']:.{price_precision}f} - ${block['high']:.{price_precision}f} "
                                f"({'retested' if block.get('is_retested') else 'fresh'})"
                            )
                    if bearish_blocks:
                        for block in bearish_blocks[:3]:
                            results_lines.append(
                                f"  • Bearish OB: ${block['low']:.{price_precision}f} - ${block['high']:.{price_precision}f} "
                                f"({'retested' if block.get('is_retested') else 'fresh'})"
                            )
                    if not bullish_blocks and not bearish_blocks:
                        results_lines.append("  • No significant order blocks detected")

                    collected_results["order_block_detector"] = result
            except Exception as e:
                self.log(state, f"Tool order_block_detector failed: {str(e)}")

        if "premium_discount_analyzer" in relevant_tool_names:
            try:
                self.log(state, "Calling tool: premium_discount_analyzer")
                pd_analyzer = PremiumDiscountAnalyzer(timeframe="5m")
                result = _run_async(pd_analyzer.analyze(candles))
                if result and isinstance(result, dict):
                    results_lines.append(f"\n**PREMIUM/DISCOUNT ZONES:**")
                    results_lines.append(f"  • Current Zone: {result.get('zone', 'N/A')}")
                    results_lines.append(f"  • Zone Level: {result.get('price_level_percent', 0):.1f}%")
                    eq_zone = result.get("zones", {}).get("equilibrium", {})
                    if eq_zone:
                        eq_mid = (eq_zone.get("low", 0) + eq_zone.get("high", 0)) / 2
                        results_lines.append(f"  • Equilibrium: ${eq_mid:.{price_precision}f}")

                    collected_results["premium_discount"] = result
            except Exception as e:
                self.log(state, f"Tool premium_discount_analyzer failed: {str(e)}")

        if "session_context_analyzer" in relevant_tool_names:
            try:
                self.log(state, "Calling tool: session_context_analyzer")
                analyzer = SessionContextAnalyzer(timeframe="5m")
                result = _run_async(analyzer.analyze(candles))
                if result and isinstance(result, dict):
                    results_lines.append("\n**SESSION CONTEXT:**")
                    results_lines.append(f"  • Session: {result.get('current_session', 'unknown')}")
                    results_lines.append(f"  • Killzone: {result.get('current_killzone') or 'none'}")
                    if result.get("true_session_open") is not None:
                        results_lines.append(f"  • True Session Open: ${result['true_session_open']:.{price_precision}f}")
                    if result.get("midnight_open") is not None:
                        results_lines.append(f"  • Midnight Open: ${result['midnight_open']:.{price_precision}f}")
                    collected_results["session_context_analyzer"] = result
            except Exception as e:
                self.log(state, f"Tool session_context_analyzer failed: {str(e)}")

        if "liquidity_analyzer" in relevant_tool_names:
            try:
                self.log(state, "Calling tool: liquidity_analyzer")
                liq_analyzer = LiquidityAnalyzer(timeframe="5m")
                result = _run_async(liq_analyzer.analyze(candles))
                if result and isinstance(result, dict):
                    collected_results["liquidity_analyzer"] = result
            except Exception as e:
                self.log(state, f"Tool liquidity_analyzer failed: {str(e)}")

        if "market_structure_analyzer" in relevant_tool_names:
            try:
                self.log(state, "Calling tool: market_structure_analyzer")
                ms_analyzer = MarketStructureAnalyzer(timeframe="5m")
                result = _run_async(ms_analyzer.analyze(candles))
                if result and isinstance(result, dict):
                    collected_results["market_structure"] = result
            except Exception as e:
                self.log(state, f"Tool market_structure_analyzer failed: {str(e)}")

        # Compute RSI/MACD if instructions mention them
        collected_results.update(
            self._compute_indicator_results(candles, self.config.get("instructions", ""))
        )

        # If no tool results, use basic technical analysis
        if not results_lines:
            text = self._compute_technical_analysis(state, candles, price_precision)
            return text, collected_results

        # Add basic price action at the top
        basic_analysis = self._compute_technical_analysis(state, candles, price_precision)
        return basic_analysis + "\n\n" + "\n".join(results_lines), collected_results
    
    def _compute_indicator_results(self, candles: List[Dict], instructions: str) -> Dict[str, Any]:
        """Compute RSI-14 and MACD(12,26,9) from candle close prices when instructions mention them.

        Returns dict with "rsi" and/or "macd" keys matching ChartAnnotationBuilder format.
        """
        if not candles or len(candles) < 26:
            return {}

        results: Dict[str, Any] = {}
        instructions_lower = instructions.lower() if instructions else ""
        closes = [float(c["close"]) for c in candles]

        # --- RSI-14 (Wilder's smoothing) ---
        if "rsi" in instructions_lower:
            period = 14
            if len(closes) > period:
                deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
                gains = [max(d, 0) for d in deltas]
                losses = [abs(min(d, 0)) for d in deltas]

                # Seed with SMA
                avg_gain = sum(gains[:period]) / period
                avg_loss = sum(losses[:period]) / period

                rsi_values: List[float] = []
                for i in range(period, len(deltas)):
                    avg_gain = (avg_gain * (period - 1) + gains[i]) / period
                    avg_loss = (avg_loss * (period - 1) + losses[i]) / period
                    rs = avg_gain / avg_loss if avg_loss != 0 else 100.0
                    rsi_values.append(100.0 - (100.0 / (1.0 + rs)))

                current_rsi = rsi_values[-1] if rsi_values else 50.0
                results["rsi"] = {
                    "values": rsi_values,
                    "current_rsi": current_rsi,
                    "is_oversold": current_rsi < 30,
                    "is_overbought": current_rsi > 70,
                }

        # --- MACD (12, 26, 9) ---
        if "macd" in instructions_lower:
            fast, slow, signal_period = 12, 26, 9
            if len(closes) >= slow + signal_period:
                def _ema(data: List[float], span: int) -> List[float]:
                    k = 2.0 / (span + 1)
                    ema_vals = [data[0]]
                    for val in data[1:]:
                        ema_vals.append(val * k + ema_vals[-1] * (1 - k))
                    return ema_vals

                ema_fast = _ema(closes, fast)
                ema_slow = _ema(closes, slow)
                macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
                signal_line = _ema(macd_line, signal_period)
                histogram = [m - s for m, s in zip(macd_line, signal_line)]

                is_bullish = (
                    len(macd_line) >= 2
                    and macd_line[-1] > signal_line[-1]
                    and macd_line[-2] <= signal_line[-2]
                )
                is_bearish = (
                    len(macd_line) >= 2
                    and macd_line[-1] < signal_line[-1]
                    and macd_line[-2] >= signal_line[-2]
                )

                results["macd"] = {
                    "values": {
                        "macd": macd_line,
                        "signal": signal_line,
                        "histogram": histogram,
                    },
                    "is_bullish_crossover": is_bullish,
                    "is_bearish_crossover": is_bearish,
                }

        return results

    def _compute_technical_analysis(self, state: PipelineState, candles: List[Dict], price_precision: int = 2) -> str:
        """Pre-compute technical indicators and return as formatted text with appropriate precision."""
        if not candles or len(candles) < 20:
            return "Insufficient candle data for technical analysis."
        
        analysis_lines = []
        
        # Price action summary
        latest = candles[-1]
        oldest = candles[0]
        price_change = ((latest['close'] - oldest['open']) / oldest['open']) * 100
        
        analysis_lines.append("**PRICE ACTION:**")
        analysis_lines.append(f"- Current: {latest['close']:.{price_precision}f}")
        analysis_lines.append(f"- Period Change: {price_change:+.2f}%")
        analysis_lines.append(f"- High: {max(c['high'] for c in candles):.{price_precision}f}")
        analysis_lines.append(f"- Low: {min(c['low'] for c in candles):.{price_precision}f}")
        
        # Simple trend detection
        closes = [c['close'] for c in candles]
        recent_closes = closes[-10:]
        if all(recent_closes[i] >= recent_closes[i-1] for i in range(1, len(recent_closes))):
            analysis_lines.append(f"- Trend: **Strong Uptrend** (10 consecutive higher closes)")
        elif all(recent_closes[i] <= recent_closes[i-1] for i in range(1, len(recent_closes))):
            analysis_lines.append(f"- Trend: **Strong Downtrend** (10 consecutive lower closes)")
        elif recent_closes[-1] > recent_closes[0]:
            analysis_lines.append(f"- Trend: **Bullish** (higher close over last 10 periods)")
        elif recent_closes[-1] < recent_closes[0]:
            analysis_lines.append(f"- Trend: **Bearish** (lower close over last 10 periods)")
        else:
            analysis_lines.append(f"- Trend: **Ranging/Neutral**")
        
        # Volume analysis
        if 'volume' in latest and latest['volume']:
            volumes = [c['volume'] for c in candles if 'volume' in c and c['volume']]
            if volumes:
                avg_volume = sum(volumes) / len(volumes)
                volume_ratio = latest['volume'] / avg_volume if avg_volume > 0 else 1
                analysis_lines.append(f"\n**VOLUME:**")
                analysis_lines.append(f"- Current: {latest['volume']:,.0f}")
                analysis_lines.append(f"- Average: {avg_volume:,.0f}")
                if volume_ratio > 1.5:
                    analysis_lines.append(f"- Status: **High volume spike** ({volume_ratio:.1f}x average)")
                elif volume_ratio < 0.7:
                    analysis_lines.append(f"- Status: **Low volume** ({volume_ratio:.1f}x average)")
                else:
                    analysis_lines.append(f"- Status: Normal ({volume_ratio:.1f}x average)")
        
        # Support/Resistance (simple)
        recent_highs = [c['high'] for c in candles[-20:]]
        recent_lows = [c['low'] for c in candles[-20:]]
        resistance = max(recent_highs)
        support = min(recent_lows)
        
        analysis_lines.append(f"\n**KEY LEVELS:**")
        analysis_lines.append(f"- Resistance: {resistance:.{price_precision}f}")
        analysis_lines.append(f"- Support: {support:.{price_precision}f}")
        analysis_lines.append(f"- Distance to resistance: {((resistance - latest['close']) / latest['close'] * 100):+.2f}%")
        analysis_lines.append(f"- Distance to support: {((support - latest['close']) / latest['close'] * 100):+.2f}%")
        
        return "\n".join(analysis_lines)
    
    def _prepare_market_context(self, state: PipelineState, timeframe: str, price_precision: int = 2) -> str:
        """Prepare market data context with appropriate price precision."""
        lines = [f"Symbol: {state.symbol}", f"Timeframe: {timeframe}"]
        
        if state.market_data and state.market_data.current_price:
            lines.append(f"Current Price: {state.market_data.current_price:.{price_precision}f}")
        
        # Show recent candles
        candles = state.get_timeframe_data(timeframe)
        if candles and len(candles) >= 3:
            lines.append(f"\nLast 3 candles:")
            for c in candles[-3:]:
                lines.append(
                    f"  {c.timestamp}: O={c.open:.{price_precision}f} H={c.high:.{price_precision}f} "
                    f"L={c.low:.{price_precision}f} C={c.close:.{price_precision}f}"
                )
        
        return "\n".join(lines)
    
    def _prepare_bias_context(self, state: PipelineState) -> str:
        """Prepare bias context if available."""
        if not state.biases:
            return "No bias analysis available."

        # Prefer bias for the primary pipeline timeframe if present, otherwise take any available bias.
        preferred_tf = state.timeframes[0] if getattr(state, "timeframes", None) else None
        bias = state.biases.get(preferred_tf) if preferred_tf else None
        if not bias:
            # Fall back to first available bias result
            bias = next(iter(state.biases.values()))

        return (
            f"Bias ({bias.timeframe}): {bias.bias}\n"
            f"Confidence: {bias.confidence:.0%}\n"
            f"Reasoning: {bias.reasoning[:200]}..."
        )
    
    def _run_deterministic_evaluation(self, state: PipelineState):
        """
        Run regime detection and setup evaluation before the LLM (TP-011).

        Returns a StrategySpec if a deterministic setup fires, otherwise None.
        The LLM still runs for explanation, but mechanical levels come from here.
        """
        try:
            from app.agents.strategy_engine import RegimeDetector, SetupEvaluator
            from app.schemas.pipeline_state import RegimeContext

            if not state.market_data:
                return None

            candles_5m = list(state.market_data.timeframes.get("5m", []))
            candles_1h = list(state.market_data.timeframes.get("1h", []))
            candles_daily = list(state.market_data.timeframes.get("1d", []))
            price = float(state.market_data.current_price or 0)

            if not candles_5m and not candles_1h:
                return None

            detector = RegimeDetector()
            regime = detector.detect(
                candles_5m=candles_5m,
                candles_1h=candles_1h or None,
                current_price=price,
            )

            evaluator = SetupEvaluator()
            spec = evaluator.evaluate(
                regime=regime,
                candles_5m=candles_5m,
                candles_1h=candles_1h or None,
                candles_daily=candles_daily or None,
                current_price=price,
            )
            return spec
        except Exception as e:
            self.logger.warning(f"Deterministic evaluation failed (non-fatal): {e}")
            return None

    def _parse_strategy_result(self, result: Any, state: PipelineState) -> StrategyResult:
        """Parse CrewAI result into StrategyResult."""
        import json
        import re
        
        result_str = str(result)
        
        # Log for debugging
        logger.info("parsing_strategy_result", result_length=len(result_str), preview=result_str[:300])
        
        # Try to extract JSON (use a more robust approach for nested structures)
        parsed_data = None
        
        # Method 1: Try to find and parse complete JSON block (handles nested structures)
        # Look for outermost JSON braces containing "action"
        if '"action"' in result_str:
            # Find the start of the JSON block
            action_index = result_str.find('"action"')
            # Search backwards for opening brace
            start_idx = result_str.rfind('{', 0, action_index)
            
            if start_idx != -1:
                # Count braces to find matching closing brace
                brace_count = 0
                end_idx = start_idx
                for i in range(start_idx, len(result_str)):
                    if result_str[i] == '{':
                        brace_count += 1
                    elif result_str[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break
                
                if end_idx > start_idx:
                    json_str = result_str[start_idx:end_idx]
                    try:
                        parsed_data = json.loads(json_str)
                        logger.info("json_parsed_successfully", 
                                  keys=list(parsed_data.keys()),
                                  method="brace_counting")
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning("json_parse_failed_brace_counting", 
                                     error=str(e),
                                     json_preview=json_str[:200])
        
        # Method 2: Fallback to regex patterns (for simpler cases)
        if not parsed_data:
            json_patterns = [
                r'\{[^{}]*"action"[^{}]*\}',  # Basic JSON without nested structures
            ]
            
            for pattern in json_patterns:
                json_match = re.search(pattern, result_str, re.DOTALL)
                if json_match:
                    try:
                        parsed_data = json.loads(json_match.group())
                        logger.info("json_parsed_successfully", 
                                  keys=list(parsed_data.keys()),
                                  method="regex")
                        break
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning("json_parse_failed", error=str(e), pattern=pattern)
                        continue
        
        if parsed_data:
            raw_reasoning = parsed_data.get("reasoning", "")
            
            # If reasoning is empty or very short, try to extract it from the full result text
            if not raw_reasoning or len(raw_reasoning) < 50:
                logger.warning("reasoning_empty_or_short", reasoning_length=len(raw_reasoning) if raw_reasoning else 0)
                # Look for reasoning after the JSON block
                json_end = result_str.find(json_match.group()) + len(json_match.group()) if json_match else 0
                remaining_text = result_str[json_end:].strip()
                if len(remaining_text) > 50:
                    raw_reasoning = remaining_text
                    logger.info("extracted_reasoning_from_remaining_text", length=len(raw_reasoning))
                elif not raw_reasoning:
                    # Use the entire result as reasoning if JSON reasoning is empty
                    raw_reasoning = result_str
                    logger.info("using_full_result_as_reasoning", length=len(raw_reasoning))
            
            # Use LLM synthesis to clean and format reasoning (falls back to regex if needed)
            formatted_reasoning = self._synthesize_reasoning_with_llm(raw_reasoning)
            logger.info("formatted_reasoning", original_length=len(raw_reasoning), formatted_length=len(formatted_reasoning))
            
            return StrategyResult(
                action=parsed_data.get("action", "HOLD"),
                entry_price=float(parsed_data.get("entry_price", 0)),
                stop_loss=float(parsed_data.get("stop_loss", 0)) if parsed_data.get("stop_loss") else None,
                take_profit=float(parsed_data.get("take_profit", 0)) if parsed_data.get("take_profit") else None,
                confidence=float(parsed_data.get("confidence", 0.5)),
                pattern_detected=parsed_data.get("pattern_detected", ""),
                reasoning=formatted_reasoning
            )
        
        # Fallback: parse from text
        logger.warning("falling_back_to_text_parsing")
        action = "HOLD"
        if "buy" in result_str.lower() and "action" in result_str.lower():
            action = "BUY"
        elif "sell" in result_str.lower() and "action" in result_str.lower():
            action = "SELL"
        
        return StrategyResult(
            action=action,
            entry_price=state.market_data.current_price if state.market_data else 0,
            stop_loss=None,
            take_profit=None,
            confidence=0.5,
            pattern_detected="",
            reasoning=self._synthesize_reasoning_with_llm(result_str)
        )
    
    def _synthesize_reasoning_with_llm(self, raw_text: str) -> str:
        """
        Use LLM to clean and synthesize reasoning if it contains artifacts.
        This is a fallback for when the primary LLM output contains tool artifacts.
        """
        # Check for CrewAI internal messages that shouldn't be shown to users
        if "thought:" in raw_text.lower() and "now can give" in raw_text.lower():
            logger.warning("detected_crewai_internal_message", text=raw_text)
            # Return a professional fallback instead of the internal message
            return "Strategy analysis in progress. Awaiting detailed market evaluation."
        
        if not raw_text or len(raw_text.strip()) < 20:
            return "Strategy analysis completed. Market conditions evaluated for trade opportunities."
        
        # Check if text has obvious artifacts
        has_artifacts = (
            "to=" in raw_text or
            "json {" in raw_text.lower() or
            "```" in raw_text or
            "commentary" in raw_text.lower() or
            re.search(r'^\s*\d+\.\s*$', raw_text, re.MULTILINE)  # Standalone numbers
        )
        
        if not has_artifacts:
            # No artifacts detected, just format
            return self._format_reasoning(raw_text)
        
        # If text is too short even with artifacts, try formatting first
        if len(raw_text.strip()) < 100:
            logger.info("text_too_short_for_synthesis", length=len(raw_text), using_regex_only=True)
            return self._format_reasoning(self._clean_reasoning(raw_text))
        
        # Use LLM to synthesize clean reasoning
        try:
            synthesis_prompt = f"""The following trading strategy analysis contains technical artifacts. 
Please rewrite it as clean, professional analysis following this structure:

**MARKET STRUCTURE:**
(describe trend, support/resistance with EXACT PRICES)

**PATTERNS IDENTIFIED:**
(describe any patterns like Fair Value Gaps, flags, etc. with EXACT PRICE RANGES)

**TOOL ANALYSIS:**
(what indicators showed)

**ENTRY RATIONALE:**
(why this entry)

**EXIT STRATEGY:**
(why these levels)

**RISK FACTORS:**
(what could go wrong)

CRITICAL REQUIREMENTS:
- Remove tool call syntax (e.g., "to=tool_name json...")
- Remove JSON fragments and code blocks
- Remove standalone numbers or bullets on empty lines
- Use **HEADER:** format for section headers (double asterisks)
- Use bullet points (•) for lists
- PRESERVE ALL SPECIFIC PRICE LEVELS AND PRICE RANGES (e.g., $445.20-$446.50, "support at $150")
- PRESERVE pattern names (e.g., "Fair Value Gap", "Bull Flag", "Head and Shoulders")
- PRESERVE level descriptions (e.g., "resistance at $155", "support around $150")

These details are critical for chart visualization!

If the original text lacks specific analysis, state what is missing clearly and professionally.

Original analysis:
{raw_text}

Provide ONLY the cleaned, formatted analysis. Keep all specific prices and pattern descriptions intact."""

            client = create_openai_client()
            synthesis_model = resolve_chat_model(self.model)
            
            response = client.chat.completions.create(
                model=synthesis_model,
                messages=[{"role": "user", "content": synthesis_prompt}],
                temperature=0.3
            )
            cleaned = response.choices[0].message.content.strip()
            
            logger.info("llm_synthesis_applied", 
                       original_length=len(raw_text), 
                       cleaned_length=len(cleaned),
                       had_artifacts=has_artifacts)
            
            return cleaned if len(cleaned) > 50 else self._format_reasoning(raw_text)
            
        except Exception as e:
            logger.warning("llm_synthesis_failed", error=str(e))
            # Fall back to regex cleaning + formatting
            return self._format_reasoning(self._clean_reasoning(raw_text))
    
    def _format_reasoning(self, text: str) -> str:
        """Format reasoning text for better readability in UI with bullet points and structure."""
        import re
        
        if not text or len(text) < 20:
            return text
        
        logger.info("format_reasoning_input", length=len(text), preview=text[:200])
        
        # Step 1: Detect and ADD ** formatting to section headers that don't have it
        # Pattern: "• MARKET STRUCTURE:" or just "MARKET STRUCTURE:" at start of line
        # Convert to: "**MARKET STRUCTURE:**"
        section_keywords = [
            'MARKET STRUCTURE', 'PATTERNS IDENTIFIED', 'PATTERN IDENTIFIED', 
            'TOOL ANALYSIS', 'ENTRY RATIONALE', 'EXIT STRATEGY', 'RISK FACTORS',
            'KEY FACTORS', 'ANALYSIS', 'SUMMARY', 'DECISION', 'RECOMMENDATION'
        ]
        
        for keyword in section_keywords:
            # Remove number/bullet if present, then add ** formatting
            # Handles: "1. MARKET STRUCTURE:", "• MARKET STRUCTURE:", or just "MARKET STRUCTURE:"
            before_count = text.count(keyword)
            text = re.sub(
                rf'^\s*(?:\d+\.\s*)?•?\s*({keyword}):\s*',
                rf'\n\n**\1:**\n',
                text,
                flags=re.MULTILINE | re.IGNORECASE
            )
            after_count = text.count(f'**{keyword}:**')
            if before_count > 0:
                logger.info(f"formatted_keyword_{keyword}", before=before_count, after=after_count)
        
        # Step 2: Remove standalone numbers (2., 3., 4., etc.) on their own lines
        text = re.sub(r'^\s*\d+\.\s*$', '', text, flags=re.MULTILINE)
        logger.info("removed_standalone_numbers")
        
        # Step 3: Normalize bullet points - remove standalone bullets on their own line
        text = re.sub(r'^\s*•\s*$', '', text, flags=re.MULTILINE)
        
        # Step 4: Handle remaining bullets before section headers (for any we missed)
        text = re.sub(r'^\s*•\s*(?=\*\*[A-Z])', '', text, flags=re.MULTILINE)
        
        # Step 5: Normalize bullets at start of lines (keep the bullet, remove extra whitespace)
        formatted = re.sub(r'^\s*•\s+', '• ', text, flags=re.MULTILINE)
        
        # Step 6: Clean up spacing
        # Remove lines that are just bullets
        formatted = re.sub(r'^•\s*$', '', formatted, flags=re.MULTILINE)
        # Collapse multiple newlines
        formatted = re.sub(r'\n\n\n+', '\n\n', formatted)
        # Remove leading/trailing whitespace
        formatted = formatted.strip()
        
        logger.info("format_reasoning_output", length=len(formatted), preview=formatted[:200])
        
        return formatted
    
    def _clean_reasoning(self, text: str) -> str:
        """Make reasoning safe and readable for end users."""
        import re
        if not text:
            return "No detailed analysis provided."
        
        cleaned = text
        
        # Remove CrewAI tool-call artifacts (only very specific patterns)
        cleaned = re.sub(r"commentary\s+to=\w+\s+tool_code=\w+\s+json\s*\{[^}]+\}", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove code blocks with triple backticks
        cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
        
        # Remove HTML/XML tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        
        # Remove numbered list formatting that LLM adds (we'll convert to bullets later)
        # Pattern 1: "1." on its own line (empty list item)
        cleaned = re.sub(r"^\s*\d+\.\s*$", "", cleaned, flags=re.MULTILINE)
        # Pattern 2: "1." at start of line followed by section header (e.g., "1. **MARKET STRUCTURE:**")
        cleaned = re.sub(r"^\s*\d+\.\s+(?=\*\*[A-Z])", "", cleaned, flags=re.MULTILINE)
        # Pattern 3: "1. •" or "1.•" (number directly before bullet - redundant)
        cleaned = re.sub(r"\d+\.\s*•", "•", cleaned)
        
        # Fix line breaks - ensure bullets always start on a new line
        # Pattern: text.• next bullet -> text.\n• next bullet
        cleaned = re.sub(r'(\.)(\s*)•', r'\1\n\n•', cleaned)
        
        # Collapse multiple whitespaces and newlines
        cleaned = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned)  # Collapse 3+ newlines to 2
        cleaned = re.sub(r"[ \t]+", " ", cleaned)  # Collapse spaces/tabs
        cleaned = cleaned.strip()
        
        # If still too long, truncate smartly at sentence boundary
        if len(cleaned) > 1500:
            # Find a good truncation point (sentence end)
            truncate_at = cleaned.rfind(".", 0, 1500)
            if truncate_at > 800:  # Make sure we have substantial content
                cleaned = cleaned[:truncate_at + 1] + "\n\n[Analysis truncated for brevity]"
            else:
                cleaned = cleaned[:1500] + "..."
        
        # If cleaned is empty or too short after all cleaning, return a default
        if len(cleaned.strip()) < 20:
            return "Market analysis completed. Decision based on current price action and technical indicators."
        
        return cleaned
