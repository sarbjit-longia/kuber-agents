"""
Celery Task: Check Pipeline Active-Hours Schedules

Runs every minute via Celery Beat. For each pipeline with schedule_enabled=True:
  - Converts current UTC time to the pipeline owner's timezone
  - Checks if today's day-of-week is in schedule_days
  - If inside [schedule_start_time, schedule_end_time) and is_active=False -> activate
  - If outside window and is_active=True -> deactivate, optionally liquidate
"""
import structlog
from datetime import datetime
from zoneinfo import ZoneInfo

from app.orchestration.celery_app import celery_app
from app.database import SessionLocal
from app.models.pipeline import Pipeline
from app.models.user import User

logger = structlog.get_logger()


@celery_app.task(name="app.orchestration.tasks.check_pipeline_schedules_active_hours")
def check_pipeline_schedules_active_hours():
    """
    Check all schedule-enabled pipelines and activate/deactivate based on time window.
    """
    db = SessionLocal()
    activated = 0
    deactivated = 0

    try:
        # Query all schedule-enabled pipelines joined with their user for timezone
        rows = (
            db.query(Pipeline, User)
            .join(User, Pipeline.user_id == User.id)
            .filter(Pipeline.schedule_enabled == True)  # noqa: E712
            .all()
        )

        logger.info("schedule_check_start", total_scheduled=len(rows))

        for pipeline, user in rows:
            try:
                tz_name = user.timezone or "America/New_York"
                try:
                    tz = ZoneInfo(tz_name)
                except Exception:
                    logger.warning(
                        "schedule_invalid_timezone",
                        pipeline_id=str(pipeline.id),
                        timezone=tz_name,
                    )
                    continue

                now_user = datetime.now(tz)
                # isoweekday(): Mon=1 .. Sun=7
                today_dow = now_user.isoweekday()

                schedule_days = pipeline.schedule_days or [1, 2, 3, 4, 5]
                start_time = pipeline.schedule_start_time  # "HH:MM"
                end_time = pipeline.schedule_end_time  # "HH:MM"

                if not start_time or not end_time:
                    continue

                current_hhmm = now_user.strftime("%H:%M")

                # Determine if inside the active window
                in_day = today_dow in schedule_days
                in_time = start_time <= current_hhmm < end_time
                inside_window = in_day and in_time

                if inside_window and not pipeline.is_active:
                    # Activate
                    pipeline.is_active = True
                    activated += 1
                    logger.info(
                        "schedule_activated",
                        pipeline_id=str(pipeline.id),
                        user_tz=tz_name,
                        current_time=current_hhmm,
                    )

                elif not inside_window and pipeline.is_active:
                    # Deactivate
                    pipeline.is_active = False
                    deactivated += 1
                    logger.info(
                        "schedule_deactivated",
                        pipeline_id=str(pipeline.id),
                        user_tz=tz_name,
                        current_time=current_hhmm,
                    )

                    # Optionally liquidate positions
                    if pipeline.liquidate_on_deactivation:
                        from app.orchestration.tasks.liquidate_positions import (
                            liquidate_pipeline_positions,
                        )

                        liquidate_pipeline_positions.delay(
                            pipeline_id=str(pipeline.id),
                            user_id=str(pipeline.user_id),
                            reason="schedule",
                        )
                        logger.info(
                            "schedule_liquidation_enqueued",
                            pipeline_id=str(pipeline.id),
                        )

            except Exception as e:
                logger.error(
                    "schedule_check_pipeline_error",
                    pipeline_id=str(pipeline.id),
                    error=str(e),
                    exc_info=True,
                )
                continue

        db.commit()

        logger.info(
            "schedule_check_done",
            activated=activated,
            deactivated=deactivated,
        )
        return {"activated": activated, "deactivated": deactivated}

    except Exception as e:
        db.rollback()
        logger.error("schedule_check_failed", error=str(e), exc_info=True)
        return {"activated": 0, "deactivated": 0, "error": str(e)}
    finally:
        db.close()
