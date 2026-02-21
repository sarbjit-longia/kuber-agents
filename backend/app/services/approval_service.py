"""
Trade Approval Service

Orchestrates the approval flow: checks if approval is required,
initiates the approval gate, builds pre-trade reports, and handles
resume/timeout logic.
"""
import secrets
import structlog
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.execution import Execution, ExecutionStatus
from app.models.pipeline import Pipeline
from app.schemas.pipeline_state import PipelineState
from app.config import settings

logger = structlog.get_logger()


class ApprovalService:
    """Service for managing trade approval workflow."""

    @staticmethod
    def should_require_approval(pipeline: Pipeline, mode: str) -> bool:
        """
        Check if the pipeline requires approval for the given execution mode.

        Args:
            pipeline: The Pipeline model instance
            mode: Execution mode (live, paper, simulation, validation)

        Returns:
            True if approval is required
        """
        if not pipeline.require_approval:
            return False
        approval_modes = pipeline.approval_modes or []
        if not approval_modes:
            return True  # If require_approval is True but no modes specified, require for all
        return mode in approval_modes

    @staticmethod
    def initiate_approval(
        execution: Execution,
        pipeline: Pipeline,
        state: PipelineState,
        db_session: Session,
    ) -> None:
        """
        Pause the execution and initiate the approval flow.

        1. Generate a unique approval token
        2. Set execution status to AWAITING_APPROVAL
        3. Save the pipeline state snapshot
        4. Schedule a timeout task
        5. Send SMS if configured

        Args:
            execution: The Execution model instance
            pipeline: The Pipeline model instance
            state: Current PipelineState with all agent results
            db_session: Active SQLAlchemy session
        """
        token = secrets.token_urlsafe(48)
        timeout_minutes = pipeline.approval_timeout_minutes or 15
        expires_at = datetime.utcnow() + timedelta(minutes=timeout_minutes)

        execution.status = ExecutionStatus.AWAITING_APPROVAL
        execution.approval_status = "pending"
        execution.approval_requested_at = datetime.utcnow()
        execution.approval_token = token
        execution.approval_expires_at = expires_at

        # Save pipeline state snapshot for later resumption
        from app.orchestration.tasks._helpers import save_pipeline_state
        save_pipeline_state(execution, state)

        flag_modified(execution, "pipeline_state")
        execution.version += 1
        db_session.commit()

        logger.info(
            "approval_initiated",
            execution_id=str(execution.id),
            pipeline_id=str(pipeline.id),
            token=token[:8] + "...",
            expires_at=expires_at.isoformat(),
            timeout_minutes=timeout_minutes,
        )

        # Schedule timeout check via Celery
        try:
            from app.orchestration.tasks.approval import check_approval_timeout
            check_approval_timeout.apply_async(
                args=[str(execution.id)],
                countdown=timeout_minutes * 60,
            )
        except Exception as e:
            logger.error("failed_to_schedule_timeout_task", error=str(e))

        # Send SMS notification if configured
        channels = pipeline.approval_channels or []
        if "sms" in channels and pipeline.approval_phone:
            try:
                from app.services.sms_notifier import TwilioSmsNotifier
                report = ApprovalService.build_pre_trade_report(state, pipeline)
                approval_url = f"{settings.APPROVAL_BASE_URL}/approve/{token}"
                TwilioSmsNotifier.send_approval_request(
                    to_phone=pipeline.approval_phone,
                    symbol=execution.symbol or "N/A",
                    action=report.get("action", "TRADE"),
                    confidence=report.get("confidence"),
                    position_size=report.get("position_size"),
                    entry_price=report.get("entry_price"),
                    approval_url=approval_url,
                    timeout_minutes=timeout_minutes,
                )
            except Exception as e:
                logger.error("sms_notification_failed", error=str(e))

    @staticmethod
    def build_pre_trade_report(state: PipelineState, pipeline: Pipeline) -> Dict[str, Any]:
        """
        Consolidate agent reports into a pre-trade summary for the approval UI.

        Args:
            state: PipelineState with all agent results
            pipeline: The Pipeline instance

        Returns:
            Dictionary with key trade parameters and agent summaries
        """
        report: Dict[str, Any] = {
            "pipeline_name": pipeline.name,
            "symbol": state.symbol,
        }

        # Strategy data
        if state.strategy:
            strategy = state.strategy
            report["action"] = getattr(strategy, "action", None)
            report["confidence"] = getattr(strategy, "confidence", None)
            report["entry_price"] = getattr(strategy, "entry_price", None)
            report["take_profit"] = getattr(strategy, "take_profit", None)
            report["stop_loss"] = getattr(strategy, "stop_loss", None)

        # Risk assessment data
        if state.risk_assessment:
            risk = state.risk_assessment
            report["risk_approved"] = getattr(risk, "approved", None)
            report["position_size"] = getattr(risk, "position_size", None)
            report["risk_score"] = getattr(risk, "risk_score", None)
            report["risk_notes"] = getattr(risk, "notes", None)

        # Market bias
        if state.market_bias:
            bias = state.market_bias
            report["bias_direction"] = getattr(bias, "direction", None)
            report["bias_strength"] = getattr(bias, "strength", None)

        # Agent reports (serialized for display)
        if state.agent_reports:
            agent_summaries = {}
            for agent_id, agent_report in state.agent_reports.items():
                if hasattr(agent_report, "dict"):
                    agent_summaries[agent_id] = agent_report.dict()
                elif isinstance(agent_report, dict):
                    agent_summaries[agent_id] = agent_report
            report["agent_reports"] = agent_summaries

        return report
