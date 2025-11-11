"""
Strategy Agent using CrewAI

Generates trading strategies and entry/exit plans based on bias and market data.
Uses CrewAI with specialized sub-agents for pattern recognition and trade planning.
"""
from typing import Dict, Any
from crewai import Agent, Task, Crew, Process

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema, StrategyResult
from app.config import settings


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
                properties={
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
                },
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
            
            # Prepare context
            market_context = self._prepare_strategy_context(state, strategy_tf)
            bias_context = self._prepare_bias_context(state) if has_bias else "No bias information available."
            
            # Create tasks
            pattern_task = Task(
                description=f"""Analyze {state.symbol} on {strategy_tf} timeframe and identify trading patterns:

CURRENT MARKET DATA:
{market_context}

BIAS CONTEXT:
{bias_context}

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
- Current Price: ${state.market_data.current_price:.2f}

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
            
            # Parse result
            strategy_result = self._parse_crew_result(result, state)
            
            # Store in state
            state.strategy = strategy_result
            
            self.log(
                state,
                f"✓ Strategy generated: {strategy_result.action} "
                f"(confidence: {strategy_result.confidence:.2f})"
            )
            
            if strategy_result.action in ["BUY", "SELL"]:
                self.log(
                    state,
                    f"  Entry: ${strategy_result.entry_price:.2f}, "
                    f"SL: ${strategy_result.stop_loss:.2f}, "
                    f"TP: ${strategy_result.take_profit:.2f}"
                )
            
            # Track cost (GPT-4 is more expensive)
            estimated_cost = 0.15
            self.track_cost(state, estimated_cost)
            
            return state
        
        except Exception as e:
            error_msg = f"Strategy generation failed: {str(e)}"
            self.add_error(state, error_msg)
            raise AgentProcessingError(error_msg) from e
    
    def _prepare_strategy_context(self, state: PipelineState, timeframe: str) -> str:
        """Prepare market data context for strategy generation."""
        candles = state.get_timeframe_data(timeframe)
        if not candles:
            return "No candle data available"
        
        # Get recent candles
        recent = candles[-10:]  # Last 10 candles
        
        context = f"""
Current Price: ${state.market_data.current_price:.2f}
Spread: ${state.market_data.spread:.4f if state.market_data.spread else 'N/A'}

Last 10 Candles (oldest to newest):
"""
        for i, candle in enumerate(recent, 1):
            context += f"{i}. O:{candle.open:.2f} H:{candle.high:.2f} L:{candle.low:.2f} C:{candle.close:.2f} V:{candle.volume:,}\n"
        
        # Add indicators if available
        latest = recent[-1]
        if latest.rsi:
            context += f"\nTechnical Indicators (Latest):\n"
            context += f"RSI: {latest.rsi:.2f}\n"
            if latest.macd:
                context += f"MACD: {latest.macd:.2f} (Signal: {latest.macd_signal:.2f})\n"
            if latest.sma_20:
                context += f"SMA(20): {latest.sma_20:.2f}, SMA(50): {latest.sma_50:.2f}\n"
        
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

