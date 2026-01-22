"""
Strategy Agent V2 - Instruction-driven trade strategy generation

This agent reads natural language instructions and automatically uses appropriate tools
to generate trading strategies.
"""
import structlog
import json
import re
from typing import Dict, Any, List, Optional
from crewai import Agent, Task, Crew
from openai import OpenAI

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, StrategyResult, AgentMetadata, AgentConfigSchema
from app.services.langfuse_service import trace_agent_execution
from app.tools.crewai_tools import get_available_tools
from app.services.chart_annotation_builder import ChartAnnotationBuilder
from app.services.reasoning_chart_parser import reasoning_chart_parser
from app.services.model_registry import model_registry

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
                "fvg_detector", "liquidity_analyzer", "market_structure", "premium_discount"
            ],
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
                        "description": "LLM model to use. OpenAI models (gpt-3.5/gpt-4) use API credits. 'lm-studio' uses your local model (free).",
                        "enum": ["lm-studio", "gpt-3.5-turbo", "gpt-4", "gpt-4o"],
                        "default": "lm-studio"
                    }
                },
                required=["instructions"]
            ),
            can_initiate_trades=True,
            can_close_positions=False
        )
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        super().__init__(agent_id, config)
        import os
        
        model_name = config.get("model", "gpt-4")
        
        # Route to OpenAI API for official OpenAI models, otherwise use local LM Studio
        openai_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4o", "gpt-4-turbo"]
        
        if model_name in openai_models:
            # Use real OpenAI API (requires credits)
            self.logger.info(f"Using OpenAI API for model: {model_name}")
            # Strategy agent doesn't use CrewAI, so just store the model name
            # It makes direct OpenAI API calls via openai.OpenAI client
            self.model = model_name
            self.use_openai_api = True
        else:
            # Use local LM Studio (free, uses loaded model)
            self.logger.info(f"Using local LM Studio for model: {model_name}")
            self.model = model_name
            self.use_openai_api = False
    
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
        
        # CHECK BIAS: If bias is NEUTRAL, skip strategy generation
        if state.biases:
            # Get the primary bias
            preferred_tf = state.timeframes[0] if getattr(state, "timeframes", None) else None
            bias = state.biases.get(preferred_tf) if preferred_tf else None
            if not bias:
                # Fall back to first available bias result
                bias = next(iter(state.biases.values()), None)
            
            if bias and bias.bias == "NEUTRAL":
                self.log(state, "⚠️  Bias is NEUTRAL - skipping strategy generation")
                
                # Return HOLD strategy
                state.strategy = StrategyResult(
                    action="HOLD",
                    confidence=0.0,
                    entry_price=state.market_data.current_price if state.market_data else 0.0,
                    stop_loss=None,
                    take_profit=None,
                    position_size=None,
                    reasoning=f"**Market Bias: NEUTRAL**\n\nNo strategy generated because the bias analysis determined the market is NEUTRAL with {bias.confidence:.0%} confidence.\n\n**Bias Reasoning:**\n{bias.reasoning}\n\n**Action:** HOLD and wait for a clear directional bias (BULLISH or BEARISH) before entering a position.",
                    pattern_detected=""
                )
                
                self.record_report(
                    state,
                    title="Strategy Decision",
                    summary="HOLD - Market bias is NEUTRAL",
                    status="completed",
                    data={
                        "Decision": "HOLD",
                        "Reason": "Bias is NEUTRAL",
                        "Bias Confidence": f"{bias.confidence:.0%}",
                        "Recommendation": "Wait for clear directional bias"
                    }
                )
                
                self.log(state, "✓ Strategy: HOLD (bias is NEUTRAL)")
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
            
            # Get all available tools
            tools = get_available_tools(
                ticker=state.symbol,
                candles=candle_dicts if candle_dicts else None
            )
            
            self.log(state, f"Available tools: {[t.name for t in tools]}")
            
            # STAGE 1: Call tools directly to get analysis data
            tool_results_text = self._call_tools_and_format(tools, state, candle_dicts, price_precision)
            
            # STAGE 2: Create agent WITHOUT tools, but WITH tool results in prompt
            # System prompt defines behavior, user instructions define the task
            strategist = Agent(
                role="Trading Strategy Executor",
                goal="Follow the user's trading instructions exactly and generate a trade signal with proper risk management.",
                backstory=f"""You are a disciplined trading strategy executor for {state.symbol}.

CORE PRINCIPLES:
1. You follow user instructions LITERALLY - if they say "enter anytime", you enter without complex analysis
2. You USE THE PROVIDED BIAS - do NOT re-analyze or invent your own bias, use what's given in "Market Bias" section
3. You ALWAYS provide all three prices: entry, stop loss, AND take profit (never leave any blank)
4. You format output as valid JSON only
5. You keep reasoning concise unless user asks for detailed analysis

Your job is to EXECUTE the user's strategy using the data provided, not second-guess it or re-analyze the market.""",
                tools=[],  # Don't give tools to agent - we already called them
                llm=self.model,
                verbose=True,
                allow_delegation=False
            )
            
            # Create strategy task - clean separation of data and instructions
            strategy_task = Task(
                description=f"""Execute the following trading strategy for {state.symbol}.

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

Remember: Follow the user's instructions literally. Keep reasoning brief unless they ask for detailed analysis.""",
                agent=strategist,
                expected_output="A complete, valid JSON object (and ONLY JSON) with all required fields: action, entry_price, stop_loss, take_profit, confidence, pattern_detected, and detailed reasoning. The reasoning should reference any tools used and their results."
            )
            
            # Execute crew
            crew = Crew(
                agents=[strategist],
                tasks=[strategy_task],
                verbose=True  # Enable verbose to see what's happening with tool calls
            )
            
            self.log(state, "Executing strategy generation...")
            crew_result = crew.kickoff()
            
            # Try to get task output instead of crew output
            # The task output should have the final JSON, not just tool calls
            final_output = None
            
            # First, try to get the task output directly
            if hasattr(crew_result, 'tasks_output') and crew_result.tasks_output:
                task_output = crew_result.tasks_output[0] if isinstance(crew_result.tasks_output, list) else crew_result.tasks_output
                if hasattr(task_output, 'raw'):
                    final_output = str(task_output.raw)
                    self.log(state, "📝 Using tasks_output[0].raw")
                elif hasattr(task_output, 'output'):
                    final_output = str(task_output.output)
                    self.log(state, "📝 Using tasks_output[0].output")
                else:
                    final_output = str(task_output)
                    self.log(state, "📝 Using str(tasks_output[0])")
            
            # Fallback to crew result attributes
            if not final_output or len(final_output) < 200:
                self.log(state, "📝 Task output too short, trying crew result attributes...")
                if hasattr(crew_result, 'raw'):
                    final_output = str(crew_result.raw)
                    self.log(state, "📝 Using crew_result.raw")
                elif hasattr(crew_result, 'output'):
                    final_output = str(crew_result.output)
                    self.log(state, "📝 Using crew_result.output")
                else:
                    final_output = str(crew_result)
                    self.log(state, "📝 Using str(crew_result)")
            
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
                    # Build chart from tool results (if any tools were used)
                    chart_data = chart_builder.build_chart_data(
                        candles=candle_dicts,
                        tool_results={},  # Tools are called internally by LLM
                        strategy_result=strategy_result,
                        instructions=instructions
                    )
                    
                    # Parse LLM reasoning to extract patterns/levels
                    self.log(state, "Parsing LLM reasoning for chart patterns...")
                    llm_annotations = reasoning_chart_parser.parse_reasoning_to_annotations(
                        reasoning=strategy_result.reasoning,
                        strategy_action=strategy_result.action,
                        entry_price=strategy_result.entry_price,
                        stop_loss=strategy_result.stop_loss,
                        take_profit=strategy_result.take_profit,
                        candles=candle_dicts
                    )
                    
                    # Merge annotations
                    for annotation_type in ['shapes', 'lines', 'markers', 'zones', 'text', 'arrows']:
                        if annotation_type in llm_annotations:
                            chart_data['annotations'][annotation_type].extend(
                                llm_annotations[annotation_type]
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
            finally:
                db.close()
            
            return state
            
        except Exception as e:
            error_msg = f"Strategy generation failed: {str(e)}"
            self.add_error(state, error_msg)
            logger.exception("strategy_agent_failed", error=str(e))
            raise AgentProcessingError(error_msg) from e
    
    def _call_tools_and_format(self, tools: List[Any], state: PipelineState, candles: List[Dict], price_precision: int = 2) -> str:
        """Call tools directly and format their results as text for the LLM prompt."""
        if not tools or not candles:
            return self._compute_technical_analysis(state, candles, price_precision)
        
        results_lines = []
        
        # Call each tool and format results
        for tool in tools:
            tool_name = tool.name
            try:
                self.log(state, f"Calling tool: {tool_name}")
                
                # Call the tool function directly with appropriate params
                if tool_name == "fvg_detector":
                    result = tool.func(timeframe="5m", lookback_candles=20)
                    if result and isinstance(result, dict):
                        results_lines.append(f"\n**FVG ANALYSIS:**")
                        if result.get("bullish_fvgs"):
                            for fvg in result["bullish_fvgs"][:3]:  # Top 3
                                results_lines.append(f"  • Bullish FVG: ${fvg['low']:.2f} - ${fvg['high']:.2f} ({'filled' if fvg.get('is_filled') else 'unfilled'})")
                        if result.get("bearish_fvgs"):
                            for fvg in result["bearish_fvgs"][:3]:
                                results_lines.append(f"  • Bearish FVG: ${fvg['low']:.2f} - ${fvg['high']:.2f} ({'filled' if fvg.get('is_filled') else 'unfilled'})")
                        if not result.get("bullish_fvgs") and not result.get("bearish_fvgs"):
                            results_lines.append(f"  • No significant FVGs detected")
                
                elif tool_name == "premium_discount_zone":
                    result = tool.func()
                    if result and isinstance(result, dict):
                        results_lines.append(f"\n**PREMIUM/DISCOUNT ZONES:**")
                        results_lines.append(f"  • Current Zone: {result.get('current_zone', 'N/A')}")
                        results_lines.append(f"  • Zone Level: {result.get('zone_percentage', 0):.1f}%")
                        if result.get('eq_level'):
                            results_lines.append(f"  • Equilibrium: ${result['eq_level']:.2f}")
                
                elif tool_name in ["rsi_calculator", "macd_calculator"]:
                    # For indicator tools, we already have the data in state
                    continue
                
            except Exception as e:
                self.log(state, f"Tool {tool_name} failed: {str(e)}")
                continue
        
        # If no tool results, use basic technical analysis
        if not results_lines:
            return self._compute_technical_analysis(state, candles, price_precision)
        
        # Add basic price action at the top
        basic_analysis = self._compute_technical_analysis(state, candles, price_precision)
        return basic_analysis + "\n\n" + "\n".join(results_lines)
    
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

            import os
            
            # Use appropriate base URL based on model selection
            if hasattr(self, 'use_openai_api') and self.use_openai_api:
                client = OpenAI(
                    api_key=os.getenv("OPENAI_API_KEY"),
                    base_url="https://api.openai.com/v1"
                )
                synthesis_model = "gpt-3.5-turbo"
            else:
                client = OpenAI(
                    api_key=os.getenv("OPENAI_API_KEY"),
                    base_url=os.getenv("OPENAI_BASE_URL", "http://host.docker.internal:1234/v1")
                )
                synthesis_model = self.model
            
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

