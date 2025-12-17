"""
Executive Report Generator

Generates comprehensive, LLM-powered executive summaries of pipeline executions.
"""
from typing import Dict, Any, Optional
import structlog
from openai import AsyncOpenAI

from app.config import settings
from app.services.langfuse_service import get_langfuse_client

logger = structlog.get_logger(__name__)


class ExecutiveReportGenerator:
    """
    Generates executive summaries of pipeline executions using LLM.
    
    Takes all agent reports, strategy decisions, and execution context
    and produces a human-readable, actionable summary.
    """
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )
        self.model = "gpt-3.5-turbo"
    
    async def generate_executive_summary(
        self,
        execution_data: Dict[str, Any],
        langfuse_trace: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Generate executive summary of the execution.
        
        Args:
            execution_data: Complete execution data including all agent reports
            langfuse_trace: Optional Langfuse trace for tracking
            
        Returns:
            Dict with executive_summary, key_takeaways, and recommendations
        """
        logger.info("generating_executive_summary", execution_id=execution_data.get("id"))
        
        try:
            # Build context from all agent reports
            context = self._build_context(execution_data)
            
            # Create prompt for LLM
            prompt = self._create_summary_prompt(context)
            
            # Call LLM
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional trading analyst creating executive summaries of algorithmic trading decisions. Be concise, clear, and actionable."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            summary_text = response.choices[0].message.content
            
            # Track in Langfuse if available (fully optional, won't affect functionality)
            if langfuse_trace:
                try:
                    generation = langfuse_trace.generation(
                        name="executive_summary_generation",
                        model=self.model,
                        input=prompt,
                        output=summary_text,
                        usage={
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens
                        },
                        metadata={
                            "cost": self._calculate_cost(response.usage),
                        },
                    )
                except Exception:
                    # Silently ignore Langfuse errors (quota, rate limit, etc.)
                    # This ensures report generation always works
                    pass
            
            # Parse the summary into sections
            summary_sections = self._parse_summary(summary_text)
            
            logger.info("executive_summary_generated", 
                       execution_id=execution_data.get("id"),
                       tokens=response.usage.total_tokens)
            
            return {
                "executive_summary": summary_sections.get("summary", summary_text),
                "key_takeaways": summary_sections.get("takeaways", []),
                "final_recommendation": summary_sections.get("recommendation", ""),
                "risk_notes": summary_sections.get("risk_notes", ""),
                "generated_at": execution_data.get("completed_at"),
                "tokens_used": response.usage.total_tokens,
                "generation_cost": self._calculate_cost(response.usage)
            }
            
        except Exception as e:
            logger.error("executive_summary_generation_failed", error=str(e))
            return {
                "executive_summary": "Failed to generate executive summary",
                "error": str(e)
            }
    
    def _build_context(self, execution_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build context from execution data."""
        context = {
            "symbol": execution_data.get("symbol", "N/A"),
            "pipeline": execution_data.get("pipeline_name", "Unknown"),
            "status": execution_data.get("status", "unknown"),
            "mode": execution_data.get("mode", "paper"),
        }
        
        # Add agent reports
        reports = execution_data.get("reports", {})
        if reports:
            context["agent_reports"] = {}
            for agent_id, report in reports.items():
                context["agent_reports"][report.get("agent_type", agent_id)] = {
                    "summary": report.get("summary", ""),
                    "data": report.get("data", {})
                }
        
        # Add result summaries
        result = execution_data.get("result", {})
        if result:
            if "biases" in result:
                context["bias"] = result["biases"]
            if "strategy" in result:
                context["strategy"] = result["strategy"]
            if "risk_assessment" in result:
                context["risk_assessment"] = result["risk_assessment"]
            if "trade_execution" in result:
                context["trade_execution"] = result["trade_execution"]
        
        return context
    
    def _create_summary_prompt(self, context: Dict[str, Any]) -> str:
        """Create prompt for LLM."""
        prompt = f"""Create an executive summary for this trading pipeline execution:

**Symbol:** {context['symbol']}
**Pipeline:** {context['pipeline']}
**Mode:** {context['mode']}

"""
        
        # Add agent reports
        if "agent_reports" in context:
            prompt += "**Agent Analysis:**\n\n"
            for agent_type, report in context["agent_reports"].items():
                prompt += f"**{agent_type}:** {report['summary']}\n\n"
        
        # Add strategy
        if "strategy" in context:
            strategy = context["strategy"]
            prompt += f"""**Strategy Decision:**
- Action: {strategy.get('action', 'N/A')}
- Confidence: {strategy.get('confidence', 0) * 100:.0f}%
- Reasoning: {strategy.get('reasoning', 'N/A')}

"""
        
        # Add risk assessment
        if "risk_assessment" in context:
            risk = context["risk_assessment"]
            prompt += f"""**Risk Assessment:**
- Approved: {risk.get('approved', 'N/A')}
- Risk Level: {risk.get('risk_level', 'N/A')}
- Notes: {risk.get('notes', 'N/A')}

"""
        
        # Add trade execution
        if "trade_execution" in context:
            trade = context["trade_execution"]
            prompt += f"""**Trade Execution:**
- Status: {trade.get('status', 'N/A')}
- Order ID: {trade.get('order_id', 'N/A')}

"""
        
        prompt += """
Please provide:
1. **Executive Summary** (2-3 sentences): High-level overview of what happened
2. **Key Takeaways** (3-5 bullet points): Most important insights
3. **Final Recommendation**: Clear action item for the trader
4. **Risk Notes**: Any concerns or warnings

Format your response as:

SUMMARY:
[Your 2-3 sentence summary]

TAKEAWAYS:
- [Takeaway 1]
- [Takeaway 2]
- [Takeaway 3]

RECOMMENDATION:
[Your clear recommendation]

RISK_NOTES:
[Any concerns or warnings, or "None" if no concerns]
"""
        
        return prompt
    
    def _parse_summary(self, summary_text: str) -> Dict[str, Any]:
        """Parse LLM response into sections."""
        sections = {
            "summary": "",
            "takeaways": [],
            "recommendation": "",
            "risk_notes": ""
        }
        
        current_section = None
        lines = summary_text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('SUMMARY:'):
                current_section = 'summary'
                continue
            elif line.startswith('TAKEAWAYS:'):
                current_section = 'takeaways'
                continue
            elif line.startswith('RECOMMENDATION:'):
                current_section = 'recommendation'
                continue
            elif line.startswith('RISK_NOTES:'):
                current_section = 'risk_notes'
                continue
            
            if current_section and line:
                if current_section == 'takeaways' and line.startswith('-'):
                    sections['takeaways'].append(line[1:].strip())
                elif current_section != 'takeaways':
                    if sections[current_section]:
                        sections[current_section] += " " + line
                    else:
                        sections[current_section] = line
        
        return sections
    
    def _calculate_cost(self, usage: Any) -> float:
        """Calculate cost based on token usage."""
        # GPT-3.5-turbo pricing
        prompt_cost = (usage.prompt_tokens / 1000) * 0.0015
        completion_cost = (usage.completion_tokens / 1000) * 0.002
        return prompt_cost + completion_cost


# Singleton instance
executive_report_generator = ExecutiveReportGenerator()

