"""
Tool Detection Service - LLM-powered analysis of user instructions

This service analyzes user strategy instructions and automatically determines
which tools are required to execute the strategy.
"""
import structlog
from typing import Dict, Any, List, Optional
import json
from openai import AsyncOpenAI

from app.tools.strategy_tools_registry import (
    STRATEGY_TOOL_REGISTRY,
    format_strategy_tools_for_openai,
    get_strategy_tool_pricing
)

logger = structlog.get_logger()


class ToolDetectionService:
    """
    Analyzes user instructions and detects required tools using LLM function calling.
    """
    
    def __init__(self, openai_api_key: str, model: str = "gpt-4"):
        """
        Initialize the service.
        
        Args:
            openai_api_key: OpenAI API key
            model: Model to use (default: gpt-4 for better reasoning)
        """
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model = model
        self.tool_registry = STRATEGY_TOOL_REGISTRY
    
    async def detect_tools(
        self,
        instructions: str,
        agent_type: str = "strategy"
    ) -> Dict[str, Any]:
        """
        Analyze instructions and determine required tools.
        
        Args:
            instructions: User's strategy instructions
            agent_type: Type of agent (strategy, bias, risk_manager)
            
        Returns:
            {
                "status": "success" | "partial" | "error",
                "tools": [
                    {
                        "tool": "fvg_detector",
                        "params": {"timeframe": "1h", "min_gap_pips": 10},
                        "reasoning": "User wants to detect bullish FVG",
                        "cost": 0.01
                    }
                ],
                "unsupported": ["order flow analysis"],
                "total_cost": 0.045,
                "summary": "ICT-based strategy with FVG + liquidity",
                "confidence": 0.85
            }
        """
        
        if not instructions or len(instructions.strip()) < 10:
            return {
                "status": "error",
                "message": "Instructions too short. Please provide more detail.",
                "tools": [],
                "unsupported": [],
                "total_cost": 0.0
            }
        
        try:
            # Build the analysis prompt
            prompt = self._build_detection_prompt(instructions, agent_type)
            
            # Call LLM with function calling
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert trading system analyst. Your job is to analyze trading strategy instructions and determine which tools are needed to execute them. You MUST call the appropriate tool functions based on the strategy."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                tools=format_strategy_tools_for_openai(),
                tool_choice="required",  # Force LLM to call at least one tool
                temperature=0.3,  # Lower temperature for consistent detection
                # NOTE: response_format not compatible with tools/function calling
            )
            
            logger.info("llm_tool_detection_called", model=self.model, instructions_length=len(instructions))
            
            # Extract tool calls from response
            message = response.choices[0].message
            tool_calls = message.tool_calls if message.tool_calls else []
            
            logger.info(
                "llm_response_received",
                tool_calls_count=len(tool_calls),
                finish_reason=response.choices[0].finish_reason,
                has_content=bool(message.content)
            )
            
            # If no tools detected, ask LLM for analysis
            if not tool_calls:
                logger.warning("no_tools_detected", instructions=instructions[:100])
                analysis = await self._analyze_without_tools(instructions)
                return analysis
            
            # Process detected tools
            detected_tools = []
            total_cost = 0.0
            
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                try:
                    params = json.loads(tool_call.function.arguments)
                except:
                    params = {}
                
                tool_info = self.tool_registry.get(tool_name)
                if tool_info:
                    tool_cost = tool_info.get("pricing", 0.0)
                    
                    detected_tools.append({
                        "tool": tool_name,
                        "params": params,
                        "reasoning": f"Detected from: {tool_call.id}",
                        "cost": tool_cost,
                        "category": tool_info.get("category", "unknown")
                    })
                    
                    total_cost += tool_cost
            
            # Get final analysis with reasoning
            final_analysis = await self._get_final_analysis(
                instructions,
                detected_tools,
                total_cost
            )
            
            logger.info(
                "tools_detected",
                num_tools=len(detected_tools),
                total_cost=total_cost,
                agent_type=agent_type
            )
            
            return {
                "status": "success" if not final_analysis.get("unsupported") else "partial",
                "tools": detected_tools,
                "unsupported": final_analysis.get("unsupported", []),
                "total_cost": total_cost,
                "summary": final_analysis.get("summary", ""),
                "confidence": final_analysis.get("confidence", 0.8),
                "llm_cost": self._estimate_llm_cost(response)
            }
            
        except Exception as e:
            logger.error("tool_detection_failed", error=str(e))
            return {
                "status": "error",
                "message": f"Detection failed: {str(e)}",
                "tools": [],
                "unsupported": [],
                "total_cost": 0.0
            }
    
    def _build_detection_prompt(self, instructions: str, agent_type: str) -> str:
        """Build the prompt for tool detection."""
        
        return f"""
Analyze the following trading strategy and determine which tool functions you need to call.

**Strategy Instructions**:
{instructions}

**Your Task**:
YOU MUST call the appropriate tool functions to gather the information needed for this strategy.

**Tool Selection Guidelines**:
- "FVG" or "fair value gap" or "gap" → CALL fvg_detector(timeframe)
- "discount zone" or "premium zone" or "50%" → CALL premium_discount(range_period)
- "liquidity" or "liquidity grab" or "order blocks" → CALL liquidity_analyzer(timeframe)
- "market structure" or "BOS" or "CHoCH" → CALL market_structure(timeframe)
- "RSI" → CALL rsi(timeframe, period)
- "SMA" or "moving average" → CALL sma_crossover(timeframe, fast_period, slow_period)
- "MACD" → CALL macd(timeframe)
- "Bollinger Bands" → CALL bollinger_bands(timeframe)

**Timeframe Guidelines**:
- Intraday/scalping: 5m or 15m
- Day trading: 1h
- Swing trading: 4h or D
- Default for ICT: 1h

Based on the strategy above, call the appropriate tool functions NOW with their required parameters.
"""
    
    async def _analyze_without_tools(self, instructions: str) -> Dict[str, Any]:
        """Analyze when no tools were detected - identify unsupported features."""
        
        prompt = f"""
The following strategy instructions were provided, but no matching tools could be detected.

Instructions: {instructions}

Identify what specific features or requirements are mentioned that we don't currently support.
Also provide a brief summary of what the strategy is trying to do.

Respond in JSON format:
{{
    "unsupported": ["feature1", "feature2"],
    "summary": "Brief strategy description",
    "suggestions": "What could work instead"
}}
"""
        
        response = await self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that responds in JSON format."},
                {"role": "user", "content": prompt + "\n\nRespond with valid JSON only."}
            ],
            temperature=0.3
        )
        
        try:
            analysis = json.loads(response.choices[0].message.content)
            return {
                "status": "error",
                "message": "No supported tools detected for this strategy",
                "tools": [],
                "unsupported": analysis.get("unsupported", []),
                "total_cost": 0.0,
                "summary": analysis.get("summary", ""),
                "suggestions": analysis.get("suggestions", "")
            }
        except:
            return {
                "status": "error",
                "message": "Could not parse strategy instructions",
                "tools": [],
                "unsupported": ["Unable to determine requirements"],
                "total_cost": 0.0
            }
    
    async def _get_final_analysis(
        self,
        instructions: str,
        tools: List[Dict],
        total_cost: float
    ) -> Dict[str, Any]:
        """Get final analysis with reasoning and unsupported features check."""
        
        tools_summary = "\n".join([
            f"- {t['tool']}: {t['params']} (${t['cost']})"
            for t in tools
        ])
        
        prompt = f"""
Strategy: {instructions}

Detected Tools:
{tools_summary}

Total Cost: ${total_cost}

Provide analysis:
1. Are these tools sufficient to execute the strategy?
2. Is anything mentioned in the strategy that we can't support?
3. Brief summary of the strategy type
4. Confidence (0-1) that the detected tools are correct

Respond in JSON:
{{
    "unsupported": [],
    "summary": "Brief strategy description",
    "confidence": 0.9,
    "notes": "Any additional observations"
}}
"""
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that responds in JSON format."},
                    {"role": "user", "content": prompt + "\n\nRespond with valid JSON only."}
                ],
                temperature=0.3
            )
            
            return json.loads(response.choices[0].message.content)
        except:
            return {
                "unsupported": [],
                "summary": f"Strategy using {len(tools)} tools",
                "confidence": 0.7
            }
    
    def _estimate_llm_cost(self, response) -> float:
        """Estimate LLM API cost from response."""
        if not response.usage:
            return 0.0
        
        # GPT-4 pricing (approximate)
        input_cost_per_1k = 0.03
        output_cost_per_1k = 0.06
        
        input_cost = (response.usage.prompt_tokens / 1000) * input_cost_per_1k
        output_cost = (response.usage.completion_tokens / 1000) * output_cost_per_1k
        
        return input_cost + output_cost

