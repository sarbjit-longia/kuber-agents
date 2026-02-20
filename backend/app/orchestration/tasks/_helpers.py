"""
Shared helper functions used across multiple Celery tasks.
"""
import structlog
from datetime import datetime
from uuid import UUID
from typing import Optional, Dict, Any

from app.database import SessionLocal
from app.models.execution import Execution

logger = structlog.get_logger()


def _send_position_closed_notification(
    execution: Execution,
    pnl: float = 0.0,
    pnl_percent: float = 0.0,
    exit_reason: str = "Position closed"
):
    """
    Send Telegram notification for position closure.
    
    Args:
        execution: Execution object
        pnl: Profit/Loss in dollars
        pnl_percent: P&L percentage
        exit_reason: Reason for exit
    """
    try:
        from app.services.telegram_notifier import telegram_notifier
        from app.models.user import User as UserModel
        from app.models.pipeline import Pipeline as PipelineModel
        
        if not execution.user_id or not execution.pipeline_id:
            return
        
        db = SessionLocal()
        try:
            # Get user
            user = db.query(UserModel).filter(UserModel.id == execution.user_id).first()
            if not user or not user.telegram_enabled:
                return
            
            if not user.telegram_bot_token or not user.telegram_chat_id:
                return
            
            # Get pipeline
            pipeline = db.query(PipelineModel).filter(PipelineModel.id == execution.pipeline_id).first()
            if not pipeline or not pipeline.notification_enabled:
                return
            
            # Check if position_closed is in notification events
            notification_events = pipeline.notification_events or []
            if "position_closed" not in notification_events:
                return
            
            # Send notification
            telegram_notifier.send_position_closed(
                bot_token=user.telegram_bot_token,
                chat_id=user.telegram_chat_id,
                symbol=execution.symbol,
                pnl=pnl,
                pnl_percent=pnl_percent,
                exit_reason=exit_reason,
                pipeline_name=pipeline.name
            )
            
            logger.info(
                "telegram_notification_sent",
                user_id=str(execution.user_id),
                pipeline_id=str(execution.pipeline_id),
                event="position_closed"
            )
            
        finally:
            db.close()
            
    except Exception as e:
        # Don't fail monitoring if notification fails
        logger.error(
            "telegram_notification_failed",
            error=str(e),
            execution_id=str(execution.id) if execution else None
        )


def _send_monitoring_stalled_notification(
    execution: Execution,
    error_count: int = 0,
    last_error: str = None,
):
    """
    Send Telegram notification when monitoring is stalled due to communication errors.

    Alerts the user that their position may still be open on the broker but the
    system can no longer reach the broker API. Manual review is required.

    Args:
        execution: Execution object
        error_count: Number of failed communication attempts
        last_error: Last error message from broker API
    """
    try:
        from app.services.telegram_notifier import telegram_notifier
        from app.models.user import User as UserModel
        from app.models.pipeline import Pipeline as PipelineModel

        if not telegram_notifier:
            return

        db = SessionLocal()
        try:
            user = db.query(UserModel).filter(UserModel.id == execution.user_id).first()
            if not user or not user.telegram_enabled:
                return

            if not user.telegram_bot_token or not user.telegram_chat_id:
                return

            pipeline = db.query(PipelineModel).filter(
                PipelineModel.id == execution.pipeline_id
            ).first()

            pipeline_name = pipeline.name if pipeline else "Unknown Pipeline"

            telegram_notifier.send_pipeline_error(
                bot_token=user.telegram_bot_token,
                chat_id=user.telegram_chat_id,
                pipeline_name=pipeline_name,
                error_message=(
                    f"⚠️ Broker communication lost for {execution.symbol or 'unknown symbol'} "
                    f"after {error_count} attempts.\n\n"
                    f"Your position may still be OPEN on the broker.\n"
                    f"Please check your broker account and reconcile manually.\n\n"
                    f"Last error: {last_error or 'Unknown'}"
                ),
                symbol=execution.symbol,
            )

            logger.info(
                "monitoring_stalled_notification_sent",
                user_id=str(execution.user_id),
                pipeline_id=str(execution.pipeline_id),
                symbol=execution.symbol,
                error_count=error_count,
            )

        finally:
            db.close()

    except Exception as e:
        # Never fail the monitoring task because of a notification error
        logger.error(
            "monitoring_stalled_notification_failed",
            error=str(e),
            execution_id=str(execution.id) if execution else None,
        )


def _extract_broker_tool(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract broker tool configuration from pipeline config.
    
    Searches for broker tool in:
    1. config.broker_tool (direct)
    2. config.nodes[].config.tools[] (nested in agent configs)
    
    Args:
        config: Pipeline configuration dict
        
    Returns:
        Broker tool config dict or None
    """
    from app.services.brokers.factory import broker_factory
    
    if not config:
        return None
    
    # Check direct broker_tool field
    broker_tool = config.get("broker_tool")
    if broker_tool:
        return broker_tool
    
    # Search in agent node configs
    nodes = config.get("nodes", []) or []
    for node in nodes:
        cfg = node.get("config") or {}
        for tool in (cfg.get("tools") or []):
            if broker_factory.is_broker_tool(tool.get("tool_type")):
                return tool
    
    return None


def _serialize_logs(logs):
    """Helper to serialize execution logs."""
    return [
        {
            "timestamp": log.get("timestamp").isoformat() if isinstance(log.get("timestamp"), datetime) else log.get("timestamp"),
            "message": log.get("message"),
            "level": log.get("level", "info"),
            "agent_id": log.get("agent_id")
        }
        for log in logs
    ]


def _serialize_reports(reports):
    """Helper to serialize agent reports."""
    from datetime import datetime
    
    def serialize_value(value):
        """Recursively serialize values, converting datetime to ISO string."""
        if isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [serialize_value(item) for item in value]
        else:
            return value
    
    serialized = {}
    for agent_id, report in reports.items():
        if hasattr(report, 'dict'):
            report_dict = report.dict()
        else:
            report_dict = report
        
        # Recursively serialize all values in the report
        serialized[agent_id] = serialize_value(report_dict)
    
    return serialized


def save_pipeline_state(execution, state, db=None):
    """
    Serialize and save the full PipelineState to execution.pipeline_state.

    Uses Pydantic's .dict() for lossless round-tripping.  UUIDs and datetimes
    are converted to strings so the result is pure JSON.

    Args:
        execution: Execution ORM object
        state: PipelineState Pydantic model
        db: Optional SQLAlchemy session — if provided, flag_modified is called
    """
    from sqlalchemy.orm.attributes import flag_modified

    def _json_safe(value):
        """Recursively convert non-JSON-native types."""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, dict):
            return {k: _json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_json_safe(item) for item in value]
        return value

    try:
        execution.pipeline_state = _json_safe(state.dict())
        if db is not None:
            flag_modified(execution, "pipeline_state")
    except Exception as e:
        logger.error(
            "save_pipeline_state_failed",
            execution_id=str(execution.id),
            error=str(e),
            exc_info=True,
        )


def load_pipeline_state(execution):
    """
    Deserialize PipelineState from execution.pipeline_state.

    Falls back to the legacy reconstruction from execution.result
    if pipeline_state is not yet populated (for pre-migration executions).

    Args:
        execution: Execution ORM object

    Returns:
        PipelineState instance, or None if deserialization fails entirely
    """
    from app.schemas.pipeline_state import (
        PipelineState,
        StrategyResult,
        RiskAssessment,
        TradeExecution,
    )

    # --- Primary path: use the full pipeline_state snapshot ---
    if execution.pipeline_state:
        try:
            return PipelineState(**execution.pipeline_state)
        except Exception as e:
            logger.warning(
                "pipeline_state_deserialization_failed_trying_legacy",
                execution_id=str(execution.id),
                error=str(e),
            )
            # Fall through to legacy path

    # --- Legacy fallback: reconstruct from execution.result ---
    logger.info(
        "using_legacy_state_reconstruction",
        execution_id=str(execution.id),
    )

    pipeline = execution.pipeline
    state_dict = execution.result or {}

    state = PipelineState(
        pipeline_id=pipeline.id if pipeline else execution.pipeline_id,
        execution_id=execution.id,
        user_id=execution.user_id,
        symbol=execution.symbol or "UNKNOWN",
        mode=execution.mode or "paper",
        execution_phase="monitoring",
    )

    try:
        if state_dict.get("strategy"):
            state.strategy = StrategyResult(**state_dict["strategy"])
        if state_dict.get("risk_assessment"):
            state.risk_assessment = RiskAssessment(**state_dict["risk_assessment"])
        if state_dict.get("trade_execution"):
            state.trade_execution = TradeExecution(**state_dict["trade_execution"])
    except Exception as deser_error:
        logger.warning(
            "legacy_state_deserialization_partial_failure",
            execution_id=str(execution.id),
            error=str(deser_error),
        )

    # Restore agent reports
    if execution.reports:
        for agent_id, report_data in execution.reports.items():
            state.agent_reports[agent_id] = report_data

    return state
