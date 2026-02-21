"""
Celery Tasks: Trade Approval

Two tasks:
1. resume_approved_execution — Resume execution after user approves a trade
2. check_approval_timeout — Auto-reject if user doesn't respond in time
"""
import structlog
from uuid import UUID
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.orchestration.celery_app import celery_app
from app.database import SessionLocal
from app.models.execution import Execution, ExecutionStatus
from app.models.pipeline import Pipeline
from app.agents import get_registry
from app.schemas.pipeline_state import PipelineState

from app.orchestration.tasks._helpers import (
    _serialize_logs,
    _serialize_reports,
    load_pipeline_state,
    save_pipeline_state,
)

logger = structlog.get_logger()


@celery_app.task(
    name="resume_approved_execution",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def resume_approved_execution(self, execution_id: str) -> dict:
    """
    Resume execution after the user approves the trade.

    Loads the saved PipelineState, creates a Trade Manager agent,
    and runs it to execute the trade. Then handles the result
    (monitoring or completed).
    """
    db: Session = SessionLocal()
    try:
        execution = (
            db.query(Execution)
            .filter(Execution.id == UUID(execution_id))
            .first()
        )
        if not execution:
            logger.error("execution_not_found", execution_id=execution_id)
            return {"status": "error", "reason": "execution_not_found"}

        # Verify state
        if execution.status != ExecutionStatus.AWAITING_APPROVAL:
            logger.warning(
                "unexpected_status",
                execution_id=execution_id,
                status=execution.status.value,
            )
            return {"status": "skipped", "reason": f"status_is_{execution.status.value}"}

        if execution.approval_status != "approved":
            logger.warning(
                "not_approved",
                execution_id=execution_id,
                approval_status=execution.approval_status,
            )
            return {"status": "skipped", "reason": "not_approved"}

        # Set execution to RUNNING
        execution.status = ExecutionStatus.RUNNING
        execution.version += 1
        db.commit()

        # Load pipeline state
        state = load_pipeline_state(execution)
        if not state:
            logger.error("pipeline_state_missing", execution_id=execution_id)
            execution.status = ExecutionStatus.FAILED
            execution.error_message = "Pipeline state missing — cannot resume after approval"
            execution.completed_at = datetime.utcnow()
            execution.version += 1
            db.commit()
            return {"status": "error", "reason": "pipeline_state_missing"}

        # Load pipeline to get config
        pipeline = db.query(Pipeline).filter(Pipeline.id == execution.pipeline_id).first()
        if not pipeline:
            logger.error("pipeline_not_found", execution_id=execution_id)
            execution.status = ExecutionStatus.FAILED
            execution.error_message = "Pipeline not found"
            execution.completed_at = datetime.utcnow()
            execution.version += 1
            db.commit()
            return {"status": "error", "reason": "pipeline_not_found"}

        # Find trade_manager_agent node config
        config = pipeline.config or {}
        nodes = config.get("nodes", [])
        tm_node = next(
            (n for n in nodes if n.get("agent_type") == "trade_manager_agent"),
            None,
        )
        if not tm_node:
            logger.error("trade_manager_node_missing", execution_id=execution_id)
            execution.status = ExecutionStatus.FAILED
            execution.error_message = "Trade Manager agent not found in pipeline config"
            execution.completed_at = datetime.utcnow()
            execution.version += 1
            db.commit()
            return {"status": "error", "reason": "trade_manager_node_missing"}

        # Create and run Trade Manager agent
        registry = get_registry()
        agent = registry.create_agent(
            agent_type="trade_manager_agent",
            agent_id=tm_node.get("id", "node-trade_manager_agent"),
            config=tm_node.get("config", {}),
        )

        # Update agent_states to show trade manager is running
        agent_states = execution.agent_states or []
        for i, ast in enumerate(agent_states):
            if ast.get("agent_type") == "trade_manager_agent":
                agent_states[i]["status"] = "running"
                agent_states[i]["started_at"] = datetime.utcnow().isoformat()
                break
        execution.agent_states = agent_states
        flag_modified(execution, "agent_states")
        db.commit()

        # Run the Trade Manager
        state = agent.process(state)

        # Update agent_states to show trade manager completed
        for i, ast in enumerate(agent_states):
            if ast.get("agent_type") == "trade_manager_agent":
                agent_states[i]["status"] = "completed"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["cost"] = state.agent_costs.get(
                    tm_node.get("id", "node-trade_manager_agent"), 0.0
                )
                break

        execution.agent_states = agent_states
        execution.logs = _serialize_logs(state.execution_log)
        execution.reports = _serialize_reports(state.agent_reports)
        execution.cost = state.total_cost
        execution.cost_breakdown = state.agent_costs

        # Serialize result
        result = {}
        if state.strategy:
            result["strategy"] = state.strategy.dict() if hasattr(state.strategy, "dict") else state.strategy
        if state.risk_assessment:
            result["risk_assessment"] = state.risk_assessment.dict() if hasattr(state.risk_assessment, "dict") else state.risk_assessment
        if state.trade_execution:
            result["trade_execution"] = state.trade_execution.dict() if hasattr(state.trade_execution, "dict") else state.trade_execution
        if state.market_bias:
            result["market_bias"] = state.market_bias.dict() if hasattr(state.market_bias, "dict") else state.market_bias
        execution.result = result

        # Save pipeline state
        save_pipeline_state(execution, state)

        # Determine outcome: monitoring or completed
        if state.execution_phase == "monitoring":
            execution.status = ExecutionStatus.MONITORING
            execution.execution_phase = "monitoring"
            execution.monitor_interval_minutes = getattr(state, "monitor_interval_minutes", 5.0)

            # Schedule monitoring check
            from app.orchestration.tasks.monitoring import schedule_monitoring_check
            monitor_delay = execution.monitor_interval_minutes * 60
            execution.next_check_at = datetime.utcnow() + __import__("datetime").timedelta(seconds=monitor_delay)

            flag_modified(execution, "agent_states")
            flag_modified(execution, "logs")
            flag_modified(execution, "reports")
            flag_modified(execution, "result")
            flag_modified(execution, "pipeline_state")
            flag_modified(execution, "cost_breakdown")
            execution.version += 1
            db.commit()

            schedule_monitoring_check.apply_async(
                args=[execution_id],
                countdown=monitor_delay,
            )
            logger.info("approved_execution_monitoring", execution_id=execution_id)
            return {"status": "monitoring"}
        else:
            execution.status = ExecutionStatus.COMPLETED
            execution.completed_at = datetime.utcnow()

            flag_modified(execution, "agent_states")
            flag_modified(execution, "logs")
            flag_modified(execution, "reports")
            flag_modified(execution, "result")
            flag_modified(execution, "pipeline_state")
            flag_modified(execution, "cost_breakdown")
            execution.version += 1
            db.commit()

            logger.info("approved_execution_completed", execution_id=execution_id)
            return {"status": "completed"}

    except Exception as e:
        logger.error(
            "resume_approved_execution_failed",
            execution_id=execution_id,
            error=str(e),
            exc_info=True,
        )
        db.rollback()

        # Mark execution as failed
        try:
            execution = db.query(Execution).filter(Execution.id == UUID(execution_id)).first()
            if execution:
                execution.status = ExecutionStatus.FAILED
                execution.error_message = f"Failed to resume after approval: {str(e)}"
                execution.completed_at = datetime.utcnow()
                execution.version += 1
                db.commit()
        except Exception:
            db.rollback()

        raise self.retry(exc=e)
    finally:
        db.close()


@celery_app.task(name="check_approval_timeout")
def check_approval_timeout(execution_id: str) -> dict:
    """
    Check if an approval has timed out. If the execution is still
    AWAITING_APPROVAL with approval_status="pending", mark it as timed_out.

    This task is race-condition safe: if the user already approved/rejected,
    this is a no-op.
    """
    db: Session = SessionLocal()
    try:
        execution = (
            db.query(Execution)
            .filter(Execution.id == UUID(execution_id))
            .first()
        )
        if not execution:
            logger.warning("timeout_check_execution_not_found", execution_id=execution_id)
            return {"status": "not_found"}

        # Only timeout if still awaiting and pending
        if (
            execution.status != ExecutionStatus.AWAITING_APPROVAL
            or execution.approval_status != "pending"
        ):
            logger.info(
                "timeout_check_skipped",
                execution_id=execution_id,
                status=execution.status.value,
                approval_status=execution.approval_status,
            )
            return {"status": "skipped", "reason": "already_resolved"}

        # Mark as timed out
        execution.approval_status = "timed_out"
        execution.approval_responded_at = datetime.utcnow()
        execution.status = ExecutionStatus.COMPLETED
        execution.completed_at = datetime.utcnow()

        # Set result with timeout info
        result = execution.result or {}
        result["trade_outcome"] = "rejected"
        result["exit_reason"] = "Approval timed out"
        execution.result = result
        flag_modified(execution, "result")

        # Mark the trade manager agent as skipped
        agent_states = execution.agent_states or []
        for i, ast in enumerate(agent_states):
            if ast.get("agent_type") == "trade_manager_agent":
                agent_states[i]["status"] = "skipped"
                agent_states[i]["completed_at"] = datetime.utcnow().isoformat()
                agent_states[i]["error"] = "Approval timed out"
                break
        execution.agent_states = agent_states
        flag_modified(execution, "agent_states")

        execution.version += 1
        db.commit()

        logger.info("approval_timed_out", execution_id=execution_id)
        return {"status": "timed_out"}

    except Exception as e:
        logger.error(
            "timeout_check_failed",
            execution_id=execution_id,
            error=str(e),
            exc_info=True,
        )
        db.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
