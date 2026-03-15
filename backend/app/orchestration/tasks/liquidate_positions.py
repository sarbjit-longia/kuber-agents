"""
Celery Task: Liquidate Pipeline Positions

Closes all MONITORING positions for a given pipeline via market orders.
Used when:
  - Schedule deactivates a pipeline with liquidate_on_deactivation=True
  - User manually deactivates with liquidate_positions=True
"""
import structlog
from datetime import datetime

from app.orchestration.celery_app import celery_app
from app.database import SessionLocal
from app.models.execution import Execution, ExecutionStatus
from app.models.pipeline import Pipeline
from app.orchestration.tasks._helpers import _extract_broker_tool, _send_position_closed_notification

logger = structlog.get_logger()


@celery_app.task(
    name="app.orchestration.tasks.liquidate_pipeline_positions",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def liquidate_pipeline_positions(self, pipeline_id: str, user_id: str, reason: str = "schedule"):
    """
    Close all MONITORING positions for a pipeline.

    Args:
        pipeline_id: Pipeline UUID string
        user_id: User UUID string
        reason: Why liquidation was triggered (schedule / manual_deactivation)
    """
    logger.info(
        "liquidate_pipeline_positions_start",
        pipeline_id=pipeline_id,
        user_id=user_id,
        reason=reason,
    )

    db = SessionLocal()
    closed_count = 0
    error_count = 0

    try:
        pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
        if not pipeline:
            logger.warning("liquidate_pipeline_not_found", pipeline_id=pipeline_id)
            return {"closed": 0, "errors": 0, "reason": "pipeline_not_found"}

        # Extract broker tool from pipeline config
        broker_tool_config = _extract_broker_tool(pipeline.config or {})
        if not broker_tool_config:
            logger.warning("liquidate_no_broker_tool", pipeline_id=pipeline_id)
            return {"closed": 0, "errors": 0, "reason": "no_broker_tool"}

        from app.services.brokers.factory import broker_factory

        broker = broker_factory.from_tool_config(broker_tool_config)

        # Find all MONITORING executions for this pipeline
        monitoring_executions = (
            db.query(Execution)
            .filter(
                Execution.pipeline_id == pipeline_id,
                Execution.status == ExecutionStatus.MONITORING,
            )
            .all()
        )

        logger.info(
            "liquidate_monitoring_executions_found",
            pipeline_id=pipeline_id,
            count=len(monitoring_executions),
        )

        for execution in monitoring_executions:
            try:
                # Extract trade details
                trade_id = None
                if execution.result and "trade_execution" in execution.result:
                    trade_exec = execution.result.get("trade_execution", {})
                    trade_id = trade_exec.get("trade_id")

                symbol = execution.symbol or "UNKNOWN"

                logger.info(
                    "liquidating_position",
                    execution_id=str(execution.id),
                    symbol=symbol,
                    trade_id=trade_id,
                )

                close_result = broker.close_position(symbol, trade_id=trade_id)

                if close_result.get("success", False):
                    # Mark execution as COMPLETED
                    execution.status = ExecutionStatus.COMPLETED
                    execution.completed_at = datetime.utcnow()
                    execution.execution_phase = "completed"
                    execution.next_check_at = None

                    # Tag result with liquidation info for audit trail
                    if execution.result is None:
                        execution.result = {}
                    execution.result["liquidation_reason"] = reason
                    execution.result["liquidated_at"] = datetime.utcnow().isoformat()
                    execution.result["trade_outcome"] = {
                        "status": "executed",
                        "pnl": 0.0,
                        "pnl_percent": 0.0,
                        "exit_reason": f"Position liquidated ({reason})",
                        "closed_at": datetime.utcnow().isoformat(),
                    }

                    from sqlalchemy.orm.attributes import flag_modified

                    flag_modified(execution, "result")
                    closed_count += 1

                    # Send notification if enabled
                    if pipeline.notification_enabled:
                        _send_position_closed_notification(
                            execution,
                            pnl=0.0,
                            pnl_percent=0.0,
                            exit_reason=f"Position liquidated ({reason})",
                        )

                    logger.info(
                        "position_liquidated",
                        execution_id=str(execution.id),
                        symbol=symbol,
                    )
                else:
                    error_count += 1
                    logger.error(
                        "position_liquidation_failed",
                        execution_id=str(execution.id),
                        symbol=symbol,
                        error=close_result.get("error"),
                    )

            except Exception as e:
                error_count += 1
                logger.error(
                    "position_liquidation_error",
                    execution_id=str(execution.id),
                    error=str(e),
                    exc_info=True,
                )

        db.commit()

        logger.info(
            "liquidate_pipeline_positions_done",
            pipeline_id=pipeline_id,
            closed=closed_count,
            errors=error_count,
        )
        return {"closed": closed_count, "errors": error_count, "reason": reason}

    except Exception as exc:
        db.rollback()
        logger.error(
            "liquidate_pipeline_positions_failed",
            pipeline_id=pipeline_id,
            error=str(exc),
            exc_info=True,
        )
        raise self.retry(exc=exc)
    finally:
        db.close()
