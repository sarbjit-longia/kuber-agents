"""
Trade Analysis Generator

Generates AI-powered post-trade analysis for completed executions with P&L data.
Follows the same singleton pattern as executive_report_generator.py.
"""
from typing import Dict, Any, Optional
import structlog
from openai import AsyncOpenAI

from app.config import settings
from app.services.langfuse_service import get_langfuse_client

logger = structlog.get_logger(__name__)


class TradeAnalysisGenerator:
    """
    Generates post-trade analysis using LLM.

    Analyzes trade outcomes including entry/exit quality, risk management,
    and provides a grade with actionable lessons.
    """

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
        self.model = "gpt-3.5-turbo"

    async def generate_trade_analysis(
        self,
        execution_data: Dict[str, Any],
        langfuse_trace: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Generate post-trade analysis of the execution.

        Args:
            execution_data: Complete execution data including trade outcome
            langfuse_trace: Optional Langfuse trace for tracking

        Returns:
            Dict with analysis summary, grade, lessons, etc.
        """
        result = execution_data.get("result", {})
        trade_outcome = result.get("trade_outcome")

        # Guard: no trade outcome means nothing to analyze
        if not trade_outcome or trade_outcome.get("pnl") is None:
            return {"available": False}

        logger.info(
            "generating_trade_analysis",
            execution_id=execution_data.get("id"),
        )

        try:
            context = self._build_context(execution_data)
            prompt = self._create_analysis_prompt(context)

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a professional trading coach reviewing completed trades. "
                            "Provide honest, constructive analysis. Be specific about what worked "
                            "and what could improve. Grade fairly based on process quality, not just outcome."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )

            analysis_text = response.choices[0].message.content

            if langfuse_trace:
                try:
                    langfuse_trace.generation(
                        name="trade_analysis_generation",
                        model=self.model,
                        input=prompt,
                        output=analysis_text,
                        usage={
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens,
                        },
                        metadata={"cost": self._calculate_cost(response.usage)},
                    )
                except Exception:
                    pass

            sections = self._parse_analysis(analysis_text)

            logger.info(
                "trade_analysis_generated",
                execution_id=execution_data.get("id"),
                tokens=response.usage.total_tokens,
            )

            return {
                "available": True,
                "analysis_summary": sections.get("summary", analysis_text),
                "what_went_well": sections.get("went_well", []),
                "areas_for_improvement": sections.get("improvements", []),
                "lessons_learned": sections.get("lessons", []),
                "trade_grade": sections.get("grade", "C"),
                "tokens_used": response.usage.total_tokens,
                "generation_cost": self._calculate_cost(response.usage),
            }

        except Exception as e:
            logger.error("trade_analysis_generation_failed", error=str(e))
            return {
                "available": False,
                "error": str(e),
            }

    def _build_context(self, execution_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build context from execution data for trade analysis."""
        result = execution_data.get("result", {})
        strategy = result.get("strategy", {})
        risk = result.get("risk_assessment", {})
        trade_exec = result.get("trade_execution", {})
        trade_outcome = result.get("trade_outcome", {})

        context = {
            "symbol": execution_data.get("symbol", "N/A"),
            "mode": execution_data.get("mode", "paper"),
            "action": strategy.get("action", "N/A"),
            "confidence": strategy.get("confidence", 0),
            "entry_price": strategy.get("entry_price"),
            "stop_loss": strategy.get("stop_loss"),
            "take_profit": strategy.get("take_profit"),
            "pattern": strategy.get("pattern_detected", "N/A"),
            "reasoning": strategy.get("reasoning", "N/A"),
            "risk_approved": risk.get("approved"),
            "risk_score": risk.get("risk_score"),
            "position_size": risk.get("position_size"),
            "max_loss": risk.get("max_loss"),
            "risk_reward_ratio": risk.get("risk_reward_ratio"),
            "filled_price": trade_exec.get("filled_price"),
            "filled_quantity": trade_exec.get("filled_quantity"),
            "order_status": trade_exec.get("status"),
            "pnl": trade_outcome.get("pnl"),
            "pnl_percent": trade_outcome.get("pnl_percent"),
            "exit_price": trade_outcome.get("exit_price"),
            "exit_reason": trade_outcome.get("exit_reason"),
        }

        # Determine if SL or TP was hit
        if context["exit_reason"]:
            reason_lower = context["exit_reason"].lower()
            context["sl_hit"] = "stop" in reason_lower or "sl" in reason_lower
            context["tp_hit"] = "profit" in reason_lower or "tp" in reason_lower or "target" in reason_lower
        else:
            context["sl_hit"] = False
            context["tp_hit"] = False

        return context

    def _create_analysis_prompt(self, context: Dict[str, Any]) -> str:
        """Create prompt for trade analysis."""
        slippage = ""
        if context.get("entry_price") and context.get("filled_price"):
            slip = abs(context["filled_price"] - context["entry_price"])
            slippage = f"\n- Slippage: ${slip:.4f} ({'filled_price'} vs planned {context['entry_price']})"

        prompt = f"""Analyze this completed trade:

**Symbol:** {context['symbol']} ({context['mode']} mode)
**Strategy:** {context['action']} @ ${context.get('entry_price', 'N/A')}
- Confidence: {context['confidence'] * 100 if context['confidence'] else 0:.0f}%
- Pattern: {context['pattern']}
- SL: ${context.get('stop_loss', 'N/A')} | TP: ${context.get('take_profit', 'N/A')}
- Reasoning: {context['reasoning'][:300] if context.get('reasoning') else 'N/A'}

**Risk Assessment:**
- Approved: {context.get('risk_approved', 'N/A')}
- Risk Score: {context.get('risk_score', 'N/A')}
- Position Size: {context.get('position_size', 'N/A')}
- R:R Ratio: {context.get('risk_reward_ratio', 'N/A')}

**Execution:**
- Filled @ ${context.get('filled_price', 'N/A')}{slippage}

**Outcome:**
- P&L: ${context.get('pnl', 0):.2f} ({context.get('pnl_percent', 0):.2f}%)
- Exit Price: ${context.get('exit_price', 'N/A')}
- Exit Reason: {context.get('exit_reason', 'N/A')}
- SL Hit: {context.get('sl_hit')} | TP Hit: {context.get('tp_hit')}

Provide your analysis in this exact format:

SUMMARY:
[2-3 sentence overall assessment of this trade]

GRADE:
[Single letter A-F. A=excellent process+outcome, B=good, C=average, D=poor process, F=major mistakes]

WENT_WELL:
- [What worked well 1]
- [What worked well 2]
- [What worked well 3]

IMPROVEMENTS:
- [Area for improvement 1]
- [Area for improvement 2]
- [Area for improvement 3]

LESSONS:
- [Key lesson 1]
- [Key lesson 2]
- [Key lesson 3]
"""
        return prompt

    def _parse_analysis(self, text: str) -> Dict[str, Any]:
        """Parse LLM response into structured sections."""
        sections: Dict[str, Any] = {
            "summary": "",
            "grade": "C",
            "went_well": [],
            "improvements": [],
            "lessons": [],
        }

        current_section = None
        for line in text.split("\n"):
            line = line.strip()

            if line.startswith("SUMMARY:"):
                current_section = "summary"
                continue
            elif line.startswith("GRADE:"):
                current_section = "grade"
                continue
            elif line.startswith("WENT_WELL:"):
                current_section = "went_well"
                continue
            elif line.startswith("IMPROVEMENTS:"):
                current_section = "improvements"
                continue
            elif line.startswith("LESSONS:"):
                current_section = "lessons"
                continue

            if current_section and line:
                if current_section == "grade":
                    # Extract single letter grade
                    grade = line.strip().upper()
                    if grade and grade[0] in "ABCDF":
                        sections["grade"] = grade[0]
                    current_section = None
                elif current_section in ("went_well", "improvements", "lessons"):
                    if line.startswith("-"):
                        sections[current_section].append(line[1:].strip())
                elif current_section == "summary":
                    if sections["summary"]:
                        sections["summary"] += " " + line
                    else:
                        sections["summary"] = line

        return sections

    def _calculate_cost(self, usage: Any) -> float:
        """Calculate cost based on token usage (GPT-3.5-turbo pricing)."""
        prompt_cost = (usage.prompt_tokens / 1000) * 0.0015
        completion_cost = (usage.completion_tokens / 1000) * 0.002
        return prompt_cost + completion_cost


# Singleton instance
trade_analysis_generator = TradeAnalysisGenerator()
