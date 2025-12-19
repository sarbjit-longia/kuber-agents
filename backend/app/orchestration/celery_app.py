"""
Celery Application Configuration

Configures Celery for asynchronous task execution and scheduling.
"""
import logging
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init
from app.config import settings

logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "trading_platform",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.orchestration.tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=10 * 60,  # 10 minutes max per task (reduced for faster recovery)
    task_soft_time_limit=8 * 60,  # 8 minutes soft limit
    worker_prefetch_multiplier=1,  # One task at a time
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    
    # Task resilience: prevent task loss on worker restart
    task_acks_late=True,  # Don't acknowledge task until it's fully completed
    task_reject_on_worker_lost=True,  # Requeue task if worker dies unexpectedly
    
    # Broker connection settings to prevent blocking
    broker_connection_retry=True,  # Auto-retry on connection loss
    broker_connection_retry_on_startup=True,  # Retry on startup
    broker_connection_max_retries=10,  # Max retry attempts
    broker_pool_limit=10,  # Max connections in pool
    
    # Result backend settings
    result_backend_transport_options={
        'socket_timeout': 5,  # 5 second timeout for result backend
        'socket_connect_timeout': 5,
    },
    
    # Broker transport options
    broker_transport_options={
        'socket_timeout': 5,  # 5 second timeout for broker
        'socket_connect_timeout': 5,
        'socket_keepalive': True,
    },
)

# Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    # Check for scheduled pipelines every minute
    "check-scheduled-pipelines": {
        "task": "app.orchestration.tasks.check_scheduled_pipelines",
        "schedule": crontab(minute="*"),  # Every minute
    },
    # Clean up old executions daily
    "cleanup-old-executions": {
        "task": "app.orchestration.tasks.cleanup_old_executions",
        "schedule": crontab(hour=3, minute=0),  # 3 AM daily
    },
    # Reset daily budgets
    "reset-daily-budgets": {
        "task": "app.orchestration.tasks.reset_daily_budgets",
        "schedule": crontab(hour=0, minute=0),  # Midnight UTC
    },
}


# Initialize telemetry for Celery workers
@worker_process_init.connect
def init_worker_telemetry(**kwargs):
    """
    Initialize OpenTelemetry for Celery worker process.
    
    This runs once per worker process to set up metrics exporting.
    """
    try:
        from app.telemetry import setup_telemetry_minimal
        setup_telemetry_minimal(
            service_name="trading-celery-worker",
            service_version="1.0.0",
            metrics_port=8001
        )
        logger.info("Celery worker telemetry initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Celery worker telemetry: {e}")

