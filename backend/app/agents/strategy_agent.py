"""
Strategy Agent using CrewAI

Generates trading strategies and entry/exit plans based on bias and market data.
Uses CrewAI with specialized sub-agents for pattern recognition and trade planning.
"""
from typing import Dict, Any
from crewai import Agent, Task, Crew, Process

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema, StrategyResult
from app.agents.schema_utils import add_standard_fields
from app.tools.strategy_tools.tool_executor import StrategyToolExecutor
from app.services.chart_annotation_builder import ChartAnnotationBuilder
from app.config import settings
from app.services.langfuse_service import trace_agent_execution, trace_llm_call, flush_langfuse


class StrategyAgent(BaseAgent):
    """
    Trading strategy agent powered by CrewAI.
    
    This agent uses a crew of specialized AI agents:
    - Pattern Recognition Specialist: Identifies chart patterns and setups
    - Trade Plan Architect: Designs entry/exit strategy with risk parameters
    
    This is a PAID agent (uses OpenAI API).
    
    Configuration:
        - strategy_timeframe: Timeframe for strategy execution (e.g., "5m", "15m", "1h")
        - risk_reward_minimum: Minimum risk/reward ratio (default: 2.0)
        - model: LLM model to use (default: "gpt-4" for better reasoning)
    
    Example config:
        {
            "strategy_timeframe": "5m",
            "risk_reward_minimum": 2.0,
            "model": "gpt-4"
        }
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="strategy_agent",
            name="AI Strategy Agent",
            description="AI-powered trading strategy generation with pattern recognition and trade planning. Uses GPT-4 for complex reasoning.",
            category="analysis",
            version="1.0.0",
            icon="psychology",
            pricing_rate=0.15,  # $0.15 per execution (GPT-4 is more expensive)
            is_free=False,
            requires_timeframes=["5m"],  # Only requires the strategy timeframe
            requires_market_data=True,
            requires_position=False,
            supported_tools=["webhook_notifier", "email_notifier"],  # Added tool support
            config_schema=AgentConfigSchema(
                type="object",
                title="Strategy Agent Configuration",
                description="Configure trading strategy generation",
                properties=add_standard_fields({
                    "strategy_timeframe": {
                        "type": "string",
                        "title": "Strategy Timeframe",
                        "description": "Primary timeframe for trade execution",
                        "enum": ["1m", "5m", "15m", "30m", "1h"],
                        "default": "5m"
                    },
                    "risk_reward_minimum": {
                        "type": "number",
                        "title": "Minimum Risk/Reward Ratio",
                        "description": "Minimum acceptable risk/reward ratio",
                        "default": 2.0,
                        "minimum": 1.0,
                        "maximum": 10.0
                    },
                    "aggressive_mode": {
                        "type": "boolean",
                        "title": "Aggressive Mode",
                        "description": "Take more aggressive entries (higher risk)",
                        "default": False
                    },
                    "model": {
                        "type": "string",
                        "title": "AI Model",
                        "description": "Which LLM model to use",
                        "enum": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
                        "default": "gpt-4"
                    }
                }),
                required=["strategy_timeframe"]
            ),
            can_initiate_trades=True,
            can_close_positions=False
        )
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        super().__init__(agent_id, config)
        self.model = config.get("model", "gpt-4")
        self._setup_crew()
    
    def _setup_crew(self):
        """Set up the CrewAI crew with specialized agents."""
        
        # Pattern Recognition Specialist
        self.pattern_specialist = Agent(
            role="Chart Pattern Recognition Specialist",
            goal="Identify high-probability chart patterns and trading setups",
            backstory="""You are an expert in technical analysis with 20+ years of experience.
            You specialize in identifying chart patterns like head & shoulders, triangles, 
            double tops/bottoms, flags, pennants, and candlestick patterns.
            You can spot breakouts, pullbacks, and continuation patterns with high accuracy.
            You always consider the context of higher timeframes.""",
            verbose=False,
            allow_delegation=False,
            llm=self.model
        )
        
        # Trade Plan Architect
        self.trade_architect = Agent(
            role="Trade Plan Architect",
            goal="Design precise trade plans with optimal entry, stop loss, and take profit levels",
            backstory="""You are a professional trading strategist who creates detailed trade plans.
            You calculate exact entry prices, stop loss levels, and take profit targets.
            You ensure excellent risk/reward ratios and consider market structure.
            You provide clear, actionable trade plans with specific price levels.
            You never take trades without a proper risk management plan.""",
            verbose=False,
            allow_delegation=False,
            llm=self.model
        )
    
    def process(self, state: PipelineState) -> PipelineState:
        """
        Generate trading strategy using CrewAI agents.
        
        Args:
            state: Current pipeline state with market data and bias
            
        Returns:
            Updated pipeline state with strategy
            
        Raises:
            InsufficientDataError: If required data missing
            AgentProcessingError: If strategy generation fails
        """
        # Create Langfuse trace for this agent execution
        trace = trace_agent_execution(
            execution_id=str(state.execution_id),
            agent_type=self.metadata.agent_type,
            agent_id=self.agent_id,
            pipeline_id=str(state.pipeline_id),
            user_id=str(state.user_id),
        )
        
        self.log(state, "Starting AI-powered strategy generation with CrewAI")
        
        # Validate inputs
        if not self.validate_input(state):
            raise InsufficientDataError(
                f"Strategy agent requires market data with timeframes: {self.metadata.requires_timeframes}"
            )
        
        # Check if we have bias information (recommended but not required)
        has_bias = len(state.biases) > 0
        if not has_bias:
            self.add_warning(state, "No bias information available. Strategy will be generated without bias context.")
        
        try:
            strategy_tf = self.config["strategy_timeframe"]
            min_rr = self.config.get("risk_reward_minimum", 2.0)
            aggressive = self.config.get("aggressive_mode", False)
            
            # Execute auto-detected tools if present
            tool_results = None
            auto_detected_tools = self.config.get("auto_detected_tools", [])
            if auto_detected_tools:
                self.log(state, f"Executing {len(auto_detected_tools)} auto-detected tools")
                tool_executor = StrategyToolExecutor(state.symbol)
                
                # Use asyncio to run async tool execution
                import asyncio
                import nest_asyncio
                nest_asyncio.apply()
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    tool_results = loop.run_until_complete(
                        tool_executor.execute_tools(auto_detected_tools)
                    )
                    self.log(state, f"Tool execution complete. Results: {list(tool_results.keys())}")
                finally:
                    loop.close()
            
            # Prepare context
            market_context = self._prepare_strategy_context(state, strategy_tf)
            bias_context = self._prepare_bias_context(state) if has_bias else "No bias information available."
            tool_context = self._prepare_tool_context(tool_results) if tool_results else ""
            
            # Create tasks
            pattern_task = Task(
                description=f"""Analyze {state.symbol} on {strategy_tf} timeframe and identify trading patterns:

CURRENT MARKET DATA:
{market_context}

BIAS CONTEXT:
{bias_context}

{tool_context}

Your tasks:
1. Identify any chart patterns (triangles, flags, head & shoulders, etc.)
2. Spot candlestick patterns (engulfing, hammers, shooting stars, etc.)
3. Look for breakout or pullback opportunities
4. Identify support/resistance zones
5. Determine if there's a high-probability setup

Provide a detailed analysis of what patterns you see and whether there's a valid trading opportunity.
Be specific about price levels and patterns.""",
                agent=self.pattern_specialist,
                expected_output="Detailed pattern analysis with specific price levels and opportunity assessment"
            )
            
            trade_plan_task = Task(
                description=f"""Based on the pattern analysis, create a detailed trade plan for {state.symbol}:

REQUIREMENTS:
- Strategy Timeframe: {strategy_tf}
- Minimum Risk/Reward: {min_rr}:1
- Aggressive Mode: {"Yes" if aggressive else "No"}
- Current Price: {f'${state.market_data.current_price:.2f}' if state.market_data.current_price is not None else 'N/A'}

If a valid trading opportunity exists:
1. Determine ACTION: BUY or SELL
2. Calculate precise ENTRY price
3. Set STOP LOSS level (must protect capital)
4. Set TAKE PROFIT target (must meet minimum R/R)
5. Assess CONFIDENCE (0.0 to 1.0)
6. Identify the PATTERN detected
7. Provide clear REASONING

If no valid opportunity exists:
- Return ACTION: HOLD with reasoning

FORMAT YOUR RESPONSE AS JSON:
{{
    "action": "BUY|SELL|HOLD",
    "entry_price": 0.00,
    "stop_loss": 0.00,
    "take_profit": 0.00,
    "confidence": 0.0-1.0,
    "pattern_detected": "pattern name",
    "reasoning": "detailed explanation"
}}

IMPORTANT: Only suggest trades with positive risk/reward ratios that meet the minimum requirement.""",
                agent=self.trade_architect,
                expected_output="JSON with complete trade plan including entry, stop loss, take profit, and reasoning",
                context=[pattern_task]
            )
            
            # Run the crew
            self.log(state, f"Running CrewAI strategy crew on {strategy_tf} timeframe")
            
            crew = Crew(
                agents=[self.pattern_specialist, self.trade_architect],
                tasks=[pattern_task, trade_plan_task],
                process=Process.sequential,
                verbose=False
            )
            
            result = crew.kickoff()
            
            # Trace the LLM call to Langfuse
            if trace and result:
                trace_llm_call(
                    trace=trace,
                    model=self.model,
                    prompt=f"Strategy generation for {state.symbol} on {strategy_tf}",
                    response=str(result),
                    tokens_used=None,
                    cost=0.15,  # Estimated
                )
            
            # Parse result
            strategy_result = self._parse_crew_result(result, state)
            
            # Store in state
            state.strategy = strategy_result
            
            confidence_str = f"{strategy_result.confidence:.2f}" if strategy_result.confidence is not None else "N/A"
            self.log(
                state,
                f"✓ Strategy generated: {strategy_result.action} (confidence: {confidence_str})"
            )
            
            if strategy_result.action in ["BUY", "SELL"]:
                entry_str = f"${strategy_result.entry_price:.2f}" if strategy_result.entry_price is not None else "N/A"
                sl_str = f"${strategy_result.stop_loss:.2f}" if strategy_result.stop_loss is not None else "N/A"
                tp_str = f"${strategy_result.take_profit:.2f}" if strategy_result.take_profit is not None else "N/A"
                self.log(
                    state,
                    f"  Entry: {entry_str}, SL: {sl_str}, TP: {tp_str}"
                )
            
            self.record_report(
                state,
                title="Strategy plan generated",
                summary=f"{strategy_result.action} plan on {strategy_tf} (confidence {confidence_str})",
                metrics={
                    "action": strategy_result.action,
                    "confidence": confidence_str,
                    "risk_reward_minimum": min_rr,
                },
                data={
                    "entry_price": strategy_result.entry_price,
                    "stop_loss": strategy_result.stop_loss,
                    "take_profit": strategy_result.take_profit,
                    "pattern": strategy_result.pattern_detected,
                    "reasoning": strategy_result.reasoning,
                    "aggressive_mode": aggressive,
                },
            )
            
            # Generate chart visualization data
            # Generate chart even without tools, using strategy result and market data
            self.log(state, "Generating strategy chart visualization...")
            try:
                chart_builder = ChartAnnotationBuilder(
                    symbol=state.symbol,
                    timeframe=strategy_tf
                )
                
                # Get candles for chart
                chart_candles = state.get_timeframe_data(strategy_tf)
                if chart_candles:
                    # Convert PipelineCandle objects to dicts for chart builder
                    candle_dicts = [
                        {
                            "timestamp": c.timestamp,
                            "open": c.open,
                            "high": c.high,
                            "low": c.low,
                            "close": c.close,
                            "volume": c.volume
                        }
                        for c in chart_candles
                    ]
                    
                    chart_data = chart_builder.build_chart_data(
                        candles=candle_dicts,
                        tool_results=tool_results,
                        strategy_result=strategy_result,
                        instructions=self.config.get("instructions")
                    )
                    
                    # Store chart data in execution artifacts
                    state.execution_artifacts["strategy_chart"] = chart_data
                    
                    self.log(
                        state,
                        f"✓ Chart visualization generated with {len(chart_data['annotations']['shapes'])} shapes, "
                        f"{len(chart_data['annotations']['markers'])} markers"
                    )
                else:
                    self.add_warning(state, "No candle data available for chart generation")
                    
            except Exception as e:
                # Don't fail the whole strategy if chart generation fails
                self.add_warning(state, f"Chart generation failed: {str(e)}")
                self.logger.error("chart_generation_failed", error=str(e), exc_info=True)
            
            # Track cost (GPT-4 is more expensive)
            estimated_cost = 0.15
            self.track_cost(state, estimated_cost)
            
            # Flush Langfuse data
            flush_langfuse()
            
            return state
        
        except Exception as e:
            error_msg = f"Strategy generation failed: {str(e)}"
            self.add_error(state, error_msg)
            
            # Flush Langfuse on error too
            flush_langfuse()
            
            raise AgentProcessingError(error_msg) from e
    
    def _prepare_strategy_context(self, state: PipelineState, timeframe: str) -> str:
        """Prepare market data context for strategy generation."""
        candles = state.get_timeframe_data(timeframe)
        if not candles:
            return "No candle data available"
        
        # Get recent candles
        recent = candles[-10:]  # Last 10 candles
        
        # Format current price safely
        price_str = f"${state.market_data.current_price:.2f}" if state.market_data.current_price is not None else "N/A"
        spread_str = f"${state.market_data.spread:.4f}" if state.market_data.spread else "N/A"
        
        context = f"""
Current Price: {price_str}
Spread: {spread_str}

Last 10 Candles (oldest to newest):
"""
        for i, candle in enumerate(recent, 1):
            o = f"{candle.open:.2f}" if candle.open is not None else "N/A"
            h = f"{candle.high:.2f}" if candle.high is not None else "N/A"
            l = f"{candle.low:.2f}" if candle.low is not None else "N/A"
            c = f"{candle.close:.2f}" if candle.close is not None else "N/A"
            v = f"{candle.volume:,}" if candle.volume is not None else "N/A"
            context += f"{i}. O:{o} H:{h} L:{l} C:{c} V:{v}\n"
        
        # Add indicators if available
        latest = recent[-1]
        if latest.rsi is not None:
            context += f"\nTechnical Indicators (Latest):\n"
            context += f"RSI: {latest.rsi:.2f}\n"
            if latest.macd is not None:
                macd_sig = f"{latest.macd_signal:.2f}" if latest.macd_signal is not None else "N/A"
                context += f"MACD: {latest.macd:.2f} (Signal: {macd_sig})\n"
            if latest.sma_20 is not None:
                sma50 = f"{latest.sma_50:.2f}" if latest.sma_50 is not None else "N/A"
                context += f"SMA(20): {latest.sma_20:.2f}, SMA(50): {sma50}\n"
        
        return context
    
    def _prepare_bias_context(self, state: PipelineState) -> str:
        """Prepare bias information for strategy generation."""
        if not state.biases:
            return "No bias information available."
        
        context = "BIAS ANALYSIS:\n"
        for timeframe, bias in state.biases.items():
            context += f"\n{timeframe}: {bias.bias} (confidence: {bias.confidence:.2f})\n"
            context += f"  Reasoning: {bias.reasoning[:200]}...\n"
            if bias.key_factors:
                context += f"  Key Factors: {', '.join(bias.key_factors[:3])}\n"
        
        return context
    
    def _prepare_tool_context(self, tool_results: Dict[str, Any]) -> str:
        """Prepare tool execution results for LLM context."""
        import json
        
        if not tool_results:
            return ""
        
        context = "\n\n=== STRATEGY TOOL ANALYSIS ===\n\n"
        
        for tool_name, result in tool_results.items():
            if "error" in result:
                context += f"⚠️ {tool_name.upper()}: Error - {result['error']}\n\n"
                continue
            
            context += f"📊 {tool_name.upper().replace('_', ' ')}:\n"
            
            # Format specific tool types
            if tool_name == "fvg_detector":
                context += self._format_fvg_result(result)
            elif tool_name == "liquidity_analyzer":
                context += self._format_liquidity_result(result)
            elif tool_name == "market_structure":
                context += self._format_structure_result(result)
            elif tool_name == "premium_discount":
                context += self._format_premium_discount_result(result)
            elif tool_name == "rsi":
                context += self._format_rsi_result(result)
            elif tool_name == "macd":
                context += self._format_macd_result(result)
            else:
                # Generic formatting
                context += json.dumps(result, indent=2) + "\n"
            
            context += "\n"
        
        context += "=== END TOOL ANALYSIS ===\n\n"
        context += "Use the above tool analysis to inform your strategy decision. "
        context += "The tools provide objective market data to validate or refine your strategy.\n"
        
        return context
    
    def _format_fvg_result(self, result: Dict) -> str:
        """Format FVG detector results."""
        text = f"  • Total FVGs Found: {result['total_fvgs']} ({result['unfilled_fvgs']} unfilled)\n"
        
        if result.get('latest_bullish_fvg'):
            fvg = result['latest_bullish_fvg']
            text += f"  • Latest Bullish FVG: {fvg['low']:.5f} - {fvg['high']:.5f} "
            text += f"(Gap: {fvg['gap_size_pips']:.1f} pips, "
            text += ("Filled)" if fvg['is_filled'] else "Unfilled)") + "\n"
        
        if result.get('latest_bearish_fvg'):
            fvg = result['latest_bearish_fvg']
            text += f"  • Latest Bearish FVG: {fvg['low']:.5f} - {fvg['high']:.5f} "
            text += f"(Gap: {fvg['gap_size_pips']:.1f} pips, "
            text += ("Filled)" if fvg['is_filled'] else "Unfilled)") + "\n"
        
        return text
    
    def _format_liquidity_result(self, result: Dict) -> str:
        """Format liquidity analyzer results."""
        text = f"  • Swing Highs: {len(result['swing_highs'])}, Swing Lows: {len(result['swing_lows'])}\n"
        text += f"  • Liquidity Grabs: {result['total_grabs']}\n"
        
        pools = result.get('active_liquidity_pools', {})
        if pools.get('above'):
            text += f"  • Buy-Side Liquidity (above): {', '.join(f'{p:.5f}' for p in pools['above'][:3])}\n"
        if pools.get('below'):
            text += f"  • Sell-Side Liquidity (below): {', '.join(f'{p:.5f}' for p in pools['below'][:3])}\n"
        
        if result.get('latest_grab'):
            grab = result['latest_grab']
            text += f"  • Latest Grab: {grab['type']} at {grab['level']:.5f} ({'Reversed' if grab['reversed'] else 'No reversal'})\n"
        
        return text
    
    def _format_structure_result(self, result: Dict) -> str:
        """Format market structure results."""
        text = f"  • Trend: {result['trend'].upper()}\n"
        text += f"  • Structure Events: {len(result['structure_events'])}\n"
        text += f"  • HH: {result['higher_highs']}, HL: {result['higher_lows']}, "
        text += f"LH: {result['lower_highs']}, LL: {result['lower_lows']}\n"
        
        if result.get('latest_bos'):
            bos = result['latest_bos']
            text += f"  • Latest BOS: {bos['direction'].upper()} at {bos['level']:.5f}\n"
        
        if result.get('latest_choch'):
            choch = result['latest_choch']
            text += f"  • Latest CHoCH: {choch['direction'].upper()} at {choch['level']:.5f}\n"
        
        return text
    
    def _format_premium_discount_result(self, result: Dict) -> str:
        """Format premium/discount zone results."""
        text = f"  • Current Zone: {result['zone'].upper()}\n"
        text += f"  • Price Level: {result['price_level_percent']:.1f}% of range\n"
        text += f"  • Range: {result['range_low']:.5f} - {result['range_high']:.5f} "
        text += f"({result['range_size_pips']:.1f} pips)\n"
        
        if result['is_in_discount']:
            text += "  ✅ IDEAL FOR BUYS (in discount zone)\n"
        elif result['is_in_premium']:
            text += "  ✅ IDEAL FOR SELLS (in premium zone)\n"
        else:
            text += "  ⚠️  In equilibrium - wait for better price\n"
        
        return text
    
    def _format_rsi_result(self, result: Dict) -> str:
        """Format RSI indicator results."""
        text = f"  • Current RSI: {result['current_rsi']:.1f}\n"
        
        if result['is_oversold']:
            text += "  ✅ OVERSOLD (<30) - potential buy signal\n"
        elif result['is_overbought']:
            text += "  ✅ OVERBOUGHT (>70) - potential sell signal\n"
        else:
            text += "  • Status: Neutral\n"
        
        return text
    
    def _format_macd_result(self, result: Dict) -> str:
        """Format MACD indicator results."""
        text = f"  • MACD: {result['current_macd']:.5f}, Signal: {result['current_signal']:.5f}\n"
        text += f"  • Histogram: {result['current_histogram']:.5f}\n"
        
        if result['is_bullish_crossover']:
            text += "  ✅ BULLISH CROSSOVER - buy signal\n"
        elif result['is_bearish_crossover']:
            text += "  ✅ BEARISH CROSSOVER - sell signal\n"
        elif result['is_bullish']:
            text += "  • Status: Bullish (MACD above signal)\n"
        elif result['is_bearish']:
            text += "  • Status: Bearish (MACD below signal)\n"
        
        return text
    
    def _parse_crew_result(self, result: Any, state: PipelineState) -> StrategyResult:
        """Parse CrewAI result into StrategyResult."""
        import json
        import re
        
        # Convert CrewOutput to string if needed
        if hasattr(result, 'raw'):
            result_str = str(result.raw)
        elif hasattr(result, 'output'):
            result_str = str(result.output)
        else:
            result_str = str(result)
        
        # Try to extract JSON
        try:
            json_match = re.search(r'\{[^}]+\}', result_str, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                action = data.get("action", "HOLD").upper()
                
                # Validate action
                if action not in ["BUY", "SELL", "HOLD", "CLOSE"]:
                    action = "HOLD"
                
                return StrategyResult(
                    action=action,
                    confidence=float(data.get("confidence", 0.5)),
                    entry_price=float(data.get("entry_price", 0)) if action in ["BUY", "SELL"] else None,
                    stop_loss=float(data.get("stop_loss", 0)) if action in ["BUY", "SELL"] else None,
                    take_profit=float(data.get("take_profit", 0)) if action in ["BUY", "SELL"] else None,
                    position_size=None,  # Will be set by Risk Manager
                    reasoning=data.get("reasoning", result_str[:500]),
                    pattern_detected=data.get("pattern_detected")
                )
        except Exception as e:
            self.log(state, f"Failed to parse JSON result: {e}", level="warning")
        
        # Fallback: Parse text
        action = "HOLD"
        if "BUY" in result_str.upper() and "DON'T BUY" not in result_str.upper():
            action = "BUY"
        elif "SELL" in result_str.upper() and "DON'T SELL" not in result_str.upper():
            action = "SELL"
        
        return StrategyResult(
            action=action,
            confidence=0.5,
            entry_price=state.market_data.current_price if action in ["BUY", "SELL"] else None,
            stop_loss=None,
            take_profit=None,
            position_size=None,
            reasoning=result_str[:500],
            pattern_detected=None
        )

