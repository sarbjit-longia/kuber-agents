"""
Bias Agent using CrewAI

Analyzes market data across multiple timeframes to determine market bias.
This agent uses CrewAI with multiple sub-agents for comprehensive analysis.
"""
from typing import Dict, Any
from crewai import Agent, Task, Crew, Process

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema, BiasResult
from app.config import settings


class BiasAgent(BaseAgent):
    """
    Multi-timeframe bias analysis agent powered by CrewAI.
    
    This agent uses a crew of AI sub-agents to analyze market data:
    - Market Structure Analyst: Analyzes price action and market structure
    - Sentiment Analyst: Evaluates market sentiment indicators
    - Bias Synthesizer: Combines analyses to determine overall bias
    
    This is a PAID agent (uses OpenAI API for LLM calls).
    
    Configuration:
        - primary_timeframe: Main timeframe for bias (e.g., "1h", "4h")
        - secondary_timeframes: Additional timeframes to consider
        - model: LLM model to use (default: "gpt-3.5-turbo")
    
    Example config:
        {
            "primary_timeframe": "4h",
            "secondary_timeframes": ["1h", "1d"],
            "model": "gpt-3.5-turbo"
        }
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="bias_agent",
            name="Multi-Timeframe Bias Agent",
            description="AI-powered market bias analysis across multiple timeframes using CrewAI. Uses GPT-3.5-turbo.",
            category="analysis",
            version="1.0.0",
            icon="analytics",
            pricing_rate=0.05,  # $0.05 per execution (estimated)
            is_free=False,
            requires_timeframes=["1h", "4h", "1d"],  # Minimum required
            requires_market_data=True,
            requires_position=False,
            supported_tools=["webhook_notifier", "email_notifier"],  # Added for bias change alerts
            config_schema=AgentConfigSchema(
                type="object",
                title="Bias Agent Configuration",
                description="Configure multi-timeframe bias analysis",
                properties={
                    "primary_timeframe": {
                        "type": "string",
                        "title": "Primary Timeframe",
                        "description": "Main timeframe for bias determination",
                        "enum": ["1h", "4h", "1d"],
                        "default": "4h"
                    },
                    "secondary_timeframes": {
                        "type": "array",
                        "title": "Secondary Timeframes",
                        "description": "Additional timeframes to consider",
                        "items": {
                            "type": "string",
                            "enum": ["5m", "15m", "30m", "1h", "4h", "1d", "1w"]
                        },
                        "default": ["1h", "1d"]
                    },
                    "model": {
                        "type": "string",
                        "title": "AI Model",
                        "description": "Which LLM model to use",
                        "enum": ["gpt-3.5-turbo", "gpt-4"],
                        "default": "gpt-3.5-turbo"
                    }
                },
                required=["primary_timeframe"]
            ),
            can_initiate_trades=False,
            can_close_positions=False
        )
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        super().__init__(agent_id, config)
        self.model = config.get("model", "gpt-3.5-turbo")
        
        # Initialize CrewAI agents (sub-agents)
        self._setup_crew()
    
    def _setup_crew(self):
        """Set up the CrewAI crew with sub-agents."""
        
        # Market Structure Analyst
        self.structure_analyst = Agent(
            role="Market Structure Analyst",
            goal="Analyze price action and market structure to identify trends and key levels",
            backstory="""You are an expert technical analyst specializing in market structure.
            You identify support/resistance levels, trend direction, and market phases.
            You analyze candlestick patterns and price movements across timeframes.""",
            verbose=False,
            allow_delegation=False,
            llm=self.model
        )
        
        # Sentiment Analyst
        self.sentiment_analyst = Agent(
            role="Market Sentiment Analyst",
            goal="Evaluate market sentiment using technical indicators and momentum",
            backstory="""You are a sentiment analysis expert who reads market psychology.
            You use RSI, MACD, volume, and other indicators to gauge market sentiment.
            You identify overbought/oversold conditions and momentum shifts.""",
            verbose=False,
            allow_delegation=False,
            llm=self.model
        )
        
        # Bias Synthesizer
        self.bias_synthesizer = Agent(
            role="Bias Synthesizer",
            goal="Combine all analyses to determine the overall market bias",
            backstory="""You are a senior trading strategist who synthesizes multiple analyses.
            You weigh different timeframes and factors to determine the strongest bias.
            You provide clear, actionable bias determinations (BULLISH/BEARISH/NEUTRAL).""",
            verbose=False,
            allow_delegation=False,
            llm=self.model
        )
    
    def process(self, state: PipelineState) -> PipelineState:
        """
        Analyze market bias using CrewAI agents.
        
        Args:
            state: Current pipeline state with market data
            
        Returns:
            Updated pipeline state with bias analysis
            
        Raises:
            InsufficientDataError: If required data missing
            AgentProcessingError: If analysis fails
        """
        self.log(state, "Starting multi-timeframe bias analysis with CrewAI")
        
        # Validate inputs
        if not self.validate_input(state):
            raise InsufficientDataError(
                f"Bias agent requires market data with timeframes: {self.metadata.requires_timeframes}"
            )
        
        try:
            primary_tf = self.config["primary_timeframe"]
            secondary_tfs = self.config.get("secondary_timeframes", ["1h", "1d"])
            
            # Prepare market data context for AI agents
            market_context = self._prepare_market_context(state, primary_tf, secondary_tfs)
            
            # Create tasks for each agent
            structure_task = Task(
                description=f"""Analyze the market structure for {state.symbol}:
                
                Primary Timeframe ({primary_tf}):
                {market_context['primary']}
                
                Identify:
                1. Current trend direction (uptrend/downtrend/sideways)
                2. Key support and resistance levels
                3. Market phase (accumulation/distribution/markup/markdown)
                4. Any significant patterns
                
                Provide a clear structural analysis.""",
                agent=self.structure_analyst,
                expected_output="Detailed market structure analysis with trend direction and key levels"
            )
            
            sentiment_task = Task(
                description=f"""Analyze market sentiment for {state.symbol}:
                
                Technical Indicators:
                {market_context['indicators']}
                
                Evaluate:
                1. Momentum (RSI, MACD)
                2. Volume trends
                3. Overbought/oversold conditions
                4. Divergences
                
                Determine the current market sentiment.""",
                agent=self.sentiment_analyst,
                expected_output="Market sentiment analysis with indicator readings"
            )
            
            synthesis_task = Task(
                description=f"""Based on the structure and sentiment analyses, determine the overall bias:
                
                Consider:
                1. Agreement/disagreement between timeframes
                2. Strength of trends and momentum
                3. Risk factors
                
                Provide:
                - Bias: BULLISH, BEARISH, or NEUTRAL
                - Confidence: 0.0 to 1.0
                - Key factors supporting the bias
                - Reasoning for the determination
                
                Format your response as JSON:
                {{
                    "bias": "BULLISH|BEARISH|NEUTRAL",
                    "confidence": 0.0-1.0,
                    "key_factors": ["factor1", "factor2", ...],
                    "reasoning": "explanation"
                }}""",
                agent=self.bias_synthesizer,
                expected_output="JSON with bias determination, confidence, factors, and reasoning",
                context=[structure_task, sentiment_task]
            )
            
            # Create and run the crew
            self.log(state, f"Running CrewAI crew with {len([structure_task, sentiment_task, synthesis_task])} tasks")
            
            crew = Crew(
                agents=[self.structure_analyst, self.sentiment_analyst, self.bias_synthesizer],
                tasks=[structure_task, sentiment_task, synthesis_task],
                process=Process.sequential,
                verbose=False
            )
            
            # Execute the crew
            result = crew.kickoff()
            
            # Parse the result
            bias_result = self._parse_crew_result(result, primary_tf)
            
            # Store in state
            state.biases[primary_tf] = bias_result
            
            self.log(
                state,
                f"✓ Bias determined: {bias_result.bias} "
                f"(confidence: {bias_result.confidence:.2f}) on {primary_tf}"
            )
            
            # Track cost (estimate based on tokens)
            # TODO: Implement actual token counting from OpenAI response
            estimated_cost = 0.05  # Rough estimate
            self.track_cost(state, estimated_cost)
            
            return state
        
        except Exception as e:
            error_msg = f"Bias analysis failed: {str(e)}"
            self.add_error(state, error_msg)
            raise AgentProcessingError(error_msg) from e
    
    def _prepare_market_context(
        self,
        state: PipelineState,
        primary_tf: str,
        secondary_tfs: list
    ) -> Dict[str, str]:
        """
        Prepare market data context for AI agents.
        
        Returns:
            Dictionary with formatted market data strings
        """
        context = {}
        
        # Primary timeframe data
        primary_candles = state.get_timeframe_data(primary_tf)
        if primary_candles:
            latest = primary_candles[-1]
            context['primary'] = f"""
            Latest Candle: O:{latest.open:.2f} H:{latest.high:.2f} L:{latest.low:.2f} C:{latest.close:.2f}
            Volume: {latest.volume:,}
            Last 5 Closes: {', '.join([f'{c.close:.2f}' for c in primary_candles[-5:]])}
            """
        
        # Indicators (from latest candle if available)
        if primary_candles and primary_candles[-1].rsi:
            latest = primary_candles[-1]
            context['indicators'] = f"""
            RSI: {latest.rsi:.2f} {self._interpret_rsi(latest.rsi)}
            MACD: {latest.macd:.2f} (Signal: {latest.macd_signal:.2f})
            """
        else:
            context['indicators'] = "Technical indicators not yet calculated"
        
        return context
    
    def _interpret_rsi(self, rsi: float) -> str:
        """Helper to interpret RSI value."""
        if rsi > 70:
            return "(Overbought)"
        elif rsi < 30:
            return "(Oversold)"
        else:
            return "(Neutral)"
    
    def _parse_crew_result(self, result: Any, timeframe: str) -> BiasResult:
        """
        Parse CrewAI result into BiasResult.
        
        Args:
            result: Raw result from CrewAI (CrewOutput or str)
            timeframe: Timeframe analyzed
            
        Returns:
            BiasResult object
        """
        import json
        import re
        
        # Convert CrewOutput to string if needed
        if hasattr(result, 'raw'):
            result_str = str(result.raw)
        elif hasattr(result, 'output'):
            result_str = str(result.output)
        else:
            result_str = str(result)
        
        # Try to extract JSON from the result
        try:
            # Look for JSON in the result
            json_match = re.search(r'\{[^}]+\}', result_str, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                return BiasResult(
                    bias=data.get("bias", "NEUTRAL"),
                    confidence=float(data.get("confidence", 0.5)),
                    timeframe=timeframe,
                    reasoning=data.get("reasoning", result_str[:200]),
                    key_factors=data.get("key_factors", [])
                )
        except:
            pass
        
        # Fallback: Parse text result
        bias = "NEUTRAL"
        if "BULLISH" in result_str.upper():
            bias = "BULLISH"
        elif "BEARISH" in result_str.upper():
            bias = "BEARISH"
        
        return BiasResult(
            bias=bias,
            confidence=0.6,
            timeframe=timeframe,
            reasoning=result_str[:500],  # First 500 chars
            key_factors=[]
        )

