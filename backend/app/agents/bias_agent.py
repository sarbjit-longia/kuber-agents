"""
Bias Agent - Determines overall market bias using LLM + tools

This agent is instruction-driven: it reads natural language instructions from the user
and automatically selects appropriate tools to complete the analysis.
"""
import structlog
from typing import Dict, Any
from datetime import datetime
from crewai import Agent, Task, Crew

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import AgentMetadata, AgentConfigSchema
from app.schemas.pipeline_state import PipelineState, BiasResult
from app.services.langfuse_service import trace_agent_execution
from app.tools.crewai_tools import get_available_tools
from app.services.model_registry import model_registry

logger = structlog.get_logger()


class BiasAgent(BaseAgent):
    """
    Bias Agent - Determines market bias (BULLISH/BEARISH/NEUTRAL)
    
    This agent analyzes market conditions using technical indicators and price action
    to determine the overall bias. It uses natural language instructions provided by
    the user and automatically selects the appropriate tools.
    
    Example Instructions:
        "Determine bias using RSI on daily timeframe. RSI > 70 = bearish, RSI < 30 = bullish"
        "Use multiple timeframes (1h, 4h, 1d) to determine overall trend"
        "Analyze market structure and momentum to determine bias"
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="bias_agent",
            name="Bias Agent",
            description="Determines overall market bias (bullish/bearish/neutral) using technical analysis",
            category="analysis",
            version="2.0.0",
            icon="trending_up",
            pricing_rate=0.0,
            is_free=True,
            requires_timeframes=[],  # Derived from instructions
            config_schema=AgentConfigSchema(
                type="object",
                title="Bias Agent Configuration",
                properties={
                    "instructions": {
                        "type": "string",
                        "title": "Instructions",
                        "description": "Natural language instructions for how to determine market bias",
                        "default": "Analyze the market using RSI, MACD, and price action across multiple timeframes (1h, 4h, 1d) to determine if the overall bias is BULLISH, BEARISH, or NEUTRAL. Consider momentum, trend strength, and key levels."
                    },
                    "model": {
                        "type": "string",
                        "title": "AI Model",
                        "description": "Which LLM model to use",
                        "enum": ["gpt-3.5-turbo", "gpt-4"],
                        "default": "gpt-3.5-turbo"
                    }
                },
                required=["instructions"]
            ),
            can_initiate_trades=False,
            can_close_positions=False
        )
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        super().__init__(agent_id, config)
        self.model = config.get("model", "gpt-3.5-turbo")
    
    def process(self, state: PipelineState) -> PipelineState:
        """
        Analyze market bias using LLM + tools.
        
        Args:
            state: Current pipeline state with market data
            
        Returns:
            Updated pipeline state with bias analysis
        """
        # Create Langfuse trace
        trace = trace_agent_execution(
            execution_id=str(state.execution_id),
            agent_type=self.metadata.agent_type,
            agent_id=self.agent_id,
            pipeline_id=str(state.pipeline_id),
            user_id=str(state.user_id),
        )
        
        self.log(state, "Starting bias analysis with instruction-driven approach")
        
        # Validate inputs
        if not self.validate_input(state):
            raise InsufficientDataError(
                f"Bias agent requires market data with timeframes: {self.metadata.requires_timeframes}"
            )
        
        try:
            # Get user instructions
            instructions = self.config.get("instructions", "").strip()
            if not instructions:
                instructions = self.metadata.config_schema.properties["instructions"]["default"]
            
            self.log(state, f"Using instructions: {instructions[:100]}...")
            
            # Prepare market context
            market_context = self._prepare_market_context(state)
            
            # Get all available tools for this ticker
            tools = get_available_tools(
                ticker=state.symbol,
                candles=None  # Indicator tools don't need candles
            )
            
            self.log(state, f"Available tools: {[t.name for t in tools]}")
            
            # Create single analyst agent with user instructions
            analyst = Agent(
                role="Market Bias Analyst",
                goal=instructions,  # User's natural language instructions!
                backstory=f"""You are an expert market analyst for {state.symbol}. 
                You have access to various technical analysis tools. 
                Use them as needed to accomplish your goal based on the instructions provided.
                Always provide clear reasoning for your bias determination.""",
                tools=tools,
                llm=self.model,
                verbose=True,
                allow_delegation=False
            )
            
            # Create analysis task
            analysis_task = Task(
                description=f"""Analyze {state.symbol} and determine the market bias.
                
CURRENT MARKET DATA:
{market_context}

YOUR INSTRUCTIONS:
{instructions}

Use the available tools as needed (RSI, MACD, SMA, etc.) to complete your analysis.

Provide your final output in this JSON format:
{{
    "bias": "BULLISH|BEARISH|NEUTRAL",
    "confidence": 0.0-1.0,
    "reasoning": "detailed explanation of your analysis",
    "key_factors": ["factor1", "factor2", "factor3"]
}}

Be specific about which indicators you used and what they showed.""",
                agent=analyst,
                expected_output="JSON with bias determination, confidence, reasoning, and key factors"
            )
            
            # Execute crew
            crew = Crew(
                agents=[analyst],
                tasks=[analysis_task],
                verbose=False
            )
            
            self.log(state, "Executing bias analysis...")
            result = crew.kickoff()
            
            # Parse result
            bias_result = self._parse_bias_result(result, state)
            
            # Update state
            state.bias = bias_result
            
            self.log(
                state,
                f"✓ Bias determined: {bias_result.bias} (confidence: {bias_result.confidence:.0%})"
            )
            
            # Track cost using model registry
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                model_id = self.config.get("model", "gpt-3.5-turbo")
                # Base cost for bias agent (minimal tool usage)
                base_cost = 0.01
                # Calculate total cost based on model
                total_cost = model_registry.calculate_agent_cost(
                    model_id=model_id,
                    db=db,
                    base_cost=base_cost,
                    estimated_input_tokens=1000,  # Typical bias prompt
                    estimated_output_tokens=300   # Typical bias response
                )
                self.track_cost(state, total_cost)
            finally:
                db.close()
            
            return state
            
        except Exception as e:
            error_msg = f"Bias analysis failed: {str(e)}"
            self.add_error(state, error_msg)
            logger.exception("bias_agent_failed", agent_id=self.agent_id, error=str(e))
            raise AgentProcessingError(error_msg) from e
    
    def _prepare_market_context(self, state: PipelineState) -> str:
        """Prepare market data context for the LLM."""
        lines = [f"Symbol: {state.symbol}"]
        
        if state.market_data and state.market_data.current_price:
            lines.append(f"Current Price: ${state.market_data.current_price:.2f}")
        
        # Show available timeframes
        if state.market_data and state.market_data.timeframes:
            lines.append(f"\nAvailable Timeframes: {list(state.market_data.timeframes.keys())}")
            
            # Show recent price action for each timeframe
            for tf, data in state.market_data.timeframes.items():
                if data and len(data) > 0:
                    latest = data[-1]
                    lines.append(
                        f"  {tf}: Close=${latest.close:.2f}, "
                        f"High=${latest.high:.2f}, Low=${latest.low:.2f}"
                    )
        
        # Show signal context if available
        if state.signal_data:
            lines.append(f"\nTriggering Signal: {state.signal_data.signal_type}")
            lines.append(f"Signal Confidence: {state.signal_data.confidence:.0%}")
        
        return "\n".join(lines)
    
    def _parse_bias_result(self, result: Any, state: PipelineState) -> BiasResult:
        """Parse CrewAI result into BiasResult."""
        import json
        import re
        
        result_str = str(result)
        
        # Try to extract JSON from result
        json_match = re.search(r'\{[^{}]*"bias"[^{}]*\}', result_str, re.DOTALL)
        
        if json_match:
            try:
                data = json.loads(json_match.group())
                return BiasResult(
                    bias=data.get("bias", "NEUTRAL"),
                    confidence=float(data.get("confidence", 0.5)),
                    reasoning=data.get("reasoning", result_str),
                    key_factors=data.get("key_factors", []),
                    timeframe_analysis={}
                )
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Fallback: parse bias from text
        bias = "NEUTRAL"
        confidence = 0.5
        
        result_lower = result_str.lower()
        if "bullish" in result_lower or "buy" in result_lower:
            bias = "BULLISH"
            confidence = 0.7
        elif "bearish" in result_lower or "sell" in result_lower:
            bias = "BEARISH"
            confidence = 0.7
        
        return BiasResult(
            bias=bias,
            confidence=confidence,
            reasoning=result_str[:500],  # Truncate if too long
            key_factors=[],
            timeframe_analysis={}
        )
