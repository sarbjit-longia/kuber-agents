"""
Bias Agent - Determines overall market bias using LLM + tools

This agent is instruction-driven: it reads natural language instructions from the user
and automatically selects appropriate tools to complete the analysis.
"""
import structlog
import re
from typing import Dict, Any
from datetime import datetime
from crewai import Agent, Task, Crew, LLM
from openai import OpenAI

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
            supported_tools=[
                # Analysis tools - Bias Agent can use any technical indicator
                "rsi", "macd", "sma_crossover", "bollinger_bands",
                "fvg_detector", "liquidity_analyzer", "market_structure", "premium_discount"
            ],
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
                        "description": "LLM model to use. OpenAI models (gpt-3.5/gpt-4) use API credits. 'lm-studio' uses your local model (free).",
                        "enum": ["lm-studio", "gpt-3.5-turbo", "gpt-4", "gpt-4o"],
                        "default": "lm-studio"
                    }
                },
                required=["instructions"]
            ),
            can_initiate_trades=False,
            can_close_positions=False
        )
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        super().__init__(agent_id, config)
        import os
        
        model_name = config.get("model", "lm-studio")
        
        # Route to OpenAI API for official OpenAI models, otherwise use local LM Studio
        openai_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4o", "gpt-4-turbo"]
        
        if model_name in openai_models:
            # Use real OpenAI API (requires credits)
            self.logger.info(f"Using OpenAI API for model: {model_name}")
            self.model = LLM(
                model=f"openai/{model_name}",
                temperature=0.7,
                base_url="https://api.openai.com/v1",
                api_key=os.getenv("OPENAI_API_KEY")
            )
            # Use gpt-4o for function calling (best tool execution)
            self.function_calling_llm = LLM(
                model="openai/gpt-4o",
                temperature=0.0,
                base_url="https://api.openai.com/v1",
                api_key=os.getenv("OPENAI_API_KEY")
            )
        else:
            # Use local LM Studio (free, uses loaded model)
            # The actual model name doesn't matter - LM Studio uses whatever is loaded
            self.logger.info(f"Using local LM Studio (loaded model)")
            # Use environment variables for LM Studio connection
            self.model = model_name
            # For local models, use same model for function calling
            self.function_calling_llm = LLM(model=model_name, temperature=0.0)
    
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
                function_calling_llm=self.function_calling_llm,  # Dedicated LLM for tool calling!
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

IMPORTANT: After calling tools and gathering data, SYNTHESIZE your findings into clean, professional analysis.

Provide your final output in this JSON format:
{{
    "bias": "BULLISH|BEARISH|NEUTRAL",
    "confidence": 0.0-1.0,
    "reasoning": "Your professional analysis here. See formatting rules below.",
    "key_factors": ["factor1", "factor2", "factor3"]
}}

CRITICAL RULES FOR "reasoning" FIELD:
- Write in clear, professional English sentences
- Synthesize what tools showed you (e.g., "The RSI on the 1d timeframe is at 65, indicating building momentum")
- NO tool call syntax (e.g., "to=tool.rsi_calculator json...")
- NO JSON fragments or code blocks
- NO technical execution artifacts
- Be specific about indicator values and what they mean
- Make it readable for traders and portfolio managers

Example of GOOD reasoning:
"The RSI on the 1d timeframe is at 65, indicating building momentum toward overbought territory. The MACD shows a bullish crossover above the signal line, supporting upside potential. Volume is slightly elevated at 1.4× average, confirming interest."

Example of BAD reasoning (DO NOT DO THIS):
"commentary to=tool.rsi_calculator json {{...}} The market shows..."

Be specific about which indicators you used and what they showed.""",
                agent=analyst,
                expected_output="JSON with bias determination, confidence, clean professional reasoning (no tool artifacts), and key factors"
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
            
            # Update state (biases is a dict keyed by timeframe)
            state.biases[bias_result.timeframe] = bias_result
            
            self.log(
                state,
                f"✓ Bias determined: {bias_result.bias} (confidence: {bias_result.confidence:.0%}) for {bias_result.timeframe}"
            )

            # Record structured report for UI (avoid raw JSON/arrays)
            # First try LLM-based synthesis, then fallback to regex cleaning
            cleaned_reasoning = self._synthesize_reasoning_with_llm(bias_result.reasoning)
            key_factors_text = ", ".join(bias_result.key_factors) if bias_result.key_factors else "None identified"
            
            self.record_report(
                state,
                title="Market Bias Analysis",
                summary=f"{bias_result.bias} bias ({bias_result.confidence:.0%}) on {bias_result.timeframe}",
                data={
                    "Market Bias": bias_result.bias,
                    "Confidence Level": f"{bias_result.confidence:.0%}",
                    "Analyzed Timeframe": bias_result.timeframe,
                    "Key Market Factors": key_factors_text,
                    "Detailed Analysis": cleaned_reasoning or "Multi-timeframe technical analysis completed. Price action, momentum, and trend indicators evaluated.",
                },
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
                # Determine primary timeframe from instructions
                from app.services.instruction_parser import instruction_parser
                instructions = self.config.get("instructions", "")
                extracted_timeframes = instruction_parser.extract_timeframes(instructions) if instructions else []
                primary_timeframe = extracted_timeframes[0] if extracted_timeframes else (state.timeframes[0] if state.timeframes else "1d")
                raw_reasoning = data.get("reasoning", result_str)
                return BiasResult(
                    bias=data.get("bias", "NEUTRAL"),
                    confidence=float(data.get("confidence", 0.5)),
                    timeframe=primary_timeframe,
                    reasoning=self._clean_reasoning(raw_reasoning),  # Clean reasoning
                    key_factors=data.get("key_factors", [])
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
        
        # Determine primary timeframe from instructions
        from app.services.instruction_parser import instruction_parser
        instructions = self.config.get("instructions", "")
        extracted_timeframes = instruction_parser.extract_timeframes(instructions) if instructions else []
        primary_timeframe = extracted_timeframes[0] if extracted_timeframes else (state.timeframes[0] if state.timeframes else "1d")
        
        return BiasResult(
            bias=bias,
            confidence=confidence,
            timeframe=primary_timeframe,
            reasoning=self._clean_reasoning(result_str),  # Clean reasoning in fallback too
            key_factors=[]
        )

    def _synthesize_reasoning_with_llm(self, raw_text: str) -> str:
        """
        Use LLM to clean and synthesize reasoning if it contains artifacts.
        This is a fallback for when the primary LLM output contains tool artifacts.
        """
        if not raw_text or len(raw_text.strip()) < 20:
            return "Market bias analysis completed based on technical indicators and market conditions."
        
        # Check if text has obvious artifacts
        has_artifacts = (
            "to=" in raw_text or
            "json {" in raw_text.lower() or
            "```" in raw_text or
            "commentary" in raw_text.lower()
        )
        
        if not has_artifacts:
            # No artifacts detected, return as-is
            return raw_text
        
        # Use LLM to synthesize clean reasoning
        try:
            import os
            synthesis_prompt = f"""The following text contains technical artifacts from tool execution. 
Please rewrite it as clean, professional market analysis suitable for traders and portfolio managers.

Remove any:
- Tool call syntax (e.g., "to=tool_name json...")
- JSON fragments
- Code blocks
- Technical execution details

Keep the core market insights and make it read like professional analysis.

Original text:
{raw_text}

Provide ONLY the cleaned, professional analysis text. Do not add any preamble or explanation."""

            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": synthesis_prompt}],
                temperature=0.3
            )
            cleaned = response.choices[0].message.content.strip()
            
            logger.info("llm_synthesis_applied", 
                       original_length=len(raw_text), 
                       cleaned_length=len(cleaned),
                       had_artifacts=has_artifacts)
            
            return cleaned if len(cleaned) > 20 else raw_text
            
        except Exception as e:
            logger.warning("llm_synthesis_failed", error=str(e))
            # Fall back to regex cleaning
            return self._clean_reasoning(raw_text)

    def _clean_reasoning(self, text: str) -> str:
        """Make reasoning safe and readable for end users."""
        import re
        if not text:
            return "Market bias analysis completed based on technical indicators and market conditions."
        
        cleaned = text
        
        # Remove CrewAI tool-call artifacts - multiple patterns
        # Pattern 1: "commentary to=tool_name json {...}" (tool_name can have dots, e.g., tool.rsi_calculator)
        cleaned = re.sub(r"commentary\s+to=[\w_.]+\s+(?:tool_code=\w+\s+)?json\s*\{[^}]+\}", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
        
        # Pattern 2: Inline JSON tool calls like "to=macd_calculator json {...}" or "to=tool.rsi_calculator json {...}"
        cleaned = re.sub(r"to=[\w_.]+\s+json\s*\{[^}]+\}", "", cleaned, flags=re.IGNORECASE)
        
        # Remove code blocks with triple backticks
        cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
        
        # Remove ONLY obvious standalone JSON objects (starting with { on new line, ending with } on new line)
        cleaned = re.sub(r"^\s*\{[\s\S]*?\}\s*$", "", cleaned, flags=re.MULTILINE)
        
        # Remove HTML/XML tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        
        # Collapse multiple whitespaces and newlines
        cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)  # Preserve paragraph breaks
        cleaned = re.sub(r"[ \t]+", " ", cleaned)  # Collapse spaces/tabs
        cleaned = cleaned.strip()
        
        # If still too long, truncate smartly at sentence boundary
        if len(cleaned) > 1000:
            truncate_at = cleaned.rfind(".", 0, 1000)
            if truncate_at > 500:
                cleaned = cleaned[:truncate_at + 1] + "\n\n[Analysis truncated]"
            else:
                cleaned = cleaned[:1000] + "..."
        
        # If cleaned is empty or too short after all cleaning, return a default
        if len(cleaned.strip()) < 20:
            return "Multi-timeframe technical analysis completed. Price action, momentum, and trend indicators evaluated."
        
        return cleaned
