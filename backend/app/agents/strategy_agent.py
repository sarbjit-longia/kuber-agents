"""
Strategy Agent V2 - Instruction-driven trade strategy generation

This agent reads natural language instructions and automatically uses appropriate tools
to generate trading strategies.
"""
import structlog
import json
import re
from typing import Dict, Any
from crewai import Agent, Task, Crew

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
            requires_timeframes=["5m"],
            config_schema=AgentConfigSchema(
                type="object",
                title="Strategy Agent Configuration",
                properties={
                    "instructions": {
                        "type": "string",
                        "title": "Strategy Instructions",
                        "description": "Natural language instructions for generating trade strategies",
                        "default": "Analyze the chart and identify high-probability trade setups. Look for clear patterns (flags, triangles, FVGs) with defined support/resistance. Generate BUY or SELL signals with specific entry, stop loss, and take profit levels. Ensure minimum 2:1 risk/reward ratio."
                    },
                    "strategy_timeframe": {
                        "type": "string",
                        "title": "Strategy Timeframe",
                        "description": "Primary timeframe for trade execution",
                        "enum": ["1m", "5m", "15m", "30m", "1h"],
                        "default": "5m"
                    },
                    "min_risk_reward": {
                        "type": "number",
                        "title": "Minimum Risk/Reward",
                        "description": "Minimum acceptable R/R ratio",
                        "default": 2.0
                    },
                    "model": {
                        "type": "string",
                        "title": "AI Model",
                        "enum": ["gpt-3.5-turbo", "gpt-4"],
                        "default": "gpt-4"
                    }
                },
                required=["instructions", "strategy_timeframe"]
            ),
            can_initiate_trades=True,
            can_close_positions=False
        )
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        super().__init__(agent_id, config)
        self.model = config.get("model", "gpt-4")
    
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
        
        try:
            # Get configuration
            instructions = self.config.get("instructions", "").strip()
            if not instructions:
                instructions = self.metadata.config_schema.properties["instructions"]["default"]
            
            strategy_tf = self.config.get("strategy_timeframe", "5m")
            min_rr = self.config.get("min_risk_reward", 2.0)
            
            self.log(state, f"Strategy timeframe: {strategy_tf}, Min R/R: {min_rr}")
            self.log(state, f"Using instructions: {instructions[:100]}...")
            
            # Prepare context
            market_context = self._prepare_market_context(state, strategy_tf)
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
            
            # Create single strategist agent with user instructions
            strategist = Agent(
                role="Trading Strategist",
                goal=instructions,  # User's natural language instructions!
                backstory=f"""You are an expert trading strategist for {state.symbol}.
                You have access to various technical analysis tools (RSI, MACD, FVG detector, etc.).
                Use them as needed to generate high-probability trade setups.
                Always ensure proper risk management with clear entry, stop loss, and take profit levels.""",
                tools=tools,
                llm=self.model,
                verbose=True,
                allow_delegation=False
            )
            
            # Create strategy task
            strategy_task = Task(
                description=f"""Generate a trading strategy for {state.symbol} on {strategy_tf} timeframe.

CURRENT MARKET DATA:
{market_context}

MARKET BIAS:
{bias_context}

YOUR INSTRUCTIONS:
{instructions}

REQUIREMENTS:
- Minimum Risk/Reward: {min_rr}:1
- Current Price: ${state.market_data.current_price:.2f if state.market_data and state.market_data.current_price else 0}

Use the available tools as needed to analyze the market and find trade setups.

Provide your strategy in this JSON format:
{{
    "action": "BUY|SELL|HOLD",
    "entry_price": 0.00,
    "stop_loss": 0.00,
    "take_profit": 0.00,
    "confidence": 0.0-1.0,
    "pattern_detected": "name of pattern/setup",
    "reasoning": "detailed explanation including which tools you used and what they showed"
}}

Only suggest trades (BUY/SELL) if:
1. There's a clear high-probability setup
2. Risk/reward ratio meets minimum ({min_rr}:1)
3. Entry, stop loss, and take profit are clearly defined

Otherwise, return action=HOLD with reasoning.""",
                agent=strategist,
                expected_output="JSON with complete trade strategy or HOLD recommendation"
            )
            
            # Execute crew
            crew = Crew(
                agents=[strategist],
                tasks=[strategy_task],
                verbose=False
            )
            
            self.log(state, "Executing strategy generation...")
            result = crew.kickoff()
            
            # Parse result
            strategy_result = self._parse_strategy_result(result, state)
            
            # Update state
            state.strategy = strategy_result
            
            self.log(
                state,
                f"✓ Strategy: {strategy_result.action} @ ${strategy_result.entry_price:.2f} "
                f"(confidence: {strategy_result.confidence:.0%})"
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
    
    def _prepare_market_context(self, state: PipelineState, timeframe: str) -> str:
        """Prepare market data context."""
        lines = [f"Symbol: {state.symbol}", f"Timeframe: {timeframe}"]
        
        if state.market_data and state.market_data.current_price:
            lines.append(f"Current Price: ${state.market_data.current_price:.2f}")
        
        # Show recent candles
        candles = state.get_timeframe_data(timeframe)
        if candles and len(candles) >= 3:
            lines.append(f"\nLast 3 candles:")
            for c in candles[-3:]:
                lines.append(
                    f"  {c.timestamp}: O=${c.open:.2f} H=${c.high:.2f} "
                    f"L=${c.low:.2f} C=${c.close:.2f}"
                )
        
        return "\n".join(lines)
    
    def _prepare_bias_context(self, state: PipelineState) -> str:
        """Prepare bias context if available."""
        if not state.bias:
            return "No bias analysis available."
        
        return (
            f"Overall Bias: {state.bias.bias}\n"
            f"Confidence: {state.bias.confidence:.0%}\n"
            f"Reasoning: {state.bias.reasoning[:200]}..."
        )
    
    def _parse_strategy_result(self, result: Any, state: PipelineState) -> StrategyResult:
        """Parse CrewAI result into StrategyResult."""
        result_str = str(result)
        
        # Try to extract JSON
        json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', result_str, re.DOTALL)
        
        if json_match:
            try:
                data = json.loads(json_match.group())
                return StrategyResult(
                    action=data.get("action", "HOLD"),
                    entry_price=float(data.get("entry_price", 0)),
                    stop_loss=float(data.get("stop_loss", 0)) if data.get("stop_loss") else None,
                    take_profit=float(data.get("take_profit", 0)) if data.get("take_profit") else None,
                    confidence=float(data.get("confidence", 0.5)),
                    pattern_detected=data.get("pattern_detected", ""),
                    reasoning=data.get("reasoning", result_str)
                )
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Fallback: parse from text
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
            reasoning=result_str[:500]
        )

