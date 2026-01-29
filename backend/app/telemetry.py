"""
OpenTelemetry Configuration for Trading Platform

This module sets up observability with OpenTelemetry for metrics, traces, and logs.
Supports both local (Prometheus) and cloud (AWS CloudWatch/X-Ray) backends.
"""
import os
import logging
from typing import Optional
import psutil
import threading
import time

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION, DEPLOYMENT_ENVIRONMENT
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from prometheus_client import start_http_server, Gauge, Histogram, Counter

logger = logging.getLogger(__name__)

# Global meter instance
_meter: Optional[metrics.Meter] = None

# Prometheus Gauges for system metrics (using prometheus_client directly)
_system_gauges = {}

# Process resource metrics
process_cpu_percent = Gauge(
    'process_cpu_percent',
    'CPU usage percentage of this process',
    ['service']
)

process_memory_bytes = Gauge(
    'process_memory_bytes',
    'Memory usage in bytes of this process',
    ['service', 'type']  # type: rss, vms, shared
)

process_threads = Gauge(
    'process_threads',
    'Number of threads in this process',
    ['service']
)

process_open_files = Gauge(
    'process_open_files',
    'Number of open file descriptors',
    ['service']
)

# Prometheus Histogram for pipeline execution duration
pipeline_duration_histogram = Histogram(
    'pipeline_execution_duration_seconds',
    'Pipeline execution duration in seconds',
    ['status', 'pipeline_id'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]  # 1s, 5s, 10s, 30s, 1m, 2m, 5m, 10m
)

# Prometheus Counter for pipeline executions (respects time filters)
pipeline_executions_counter = Counter(
    'pipeline_executions_total',
    'Total pipeline executions',
    ['status', 'pipeline_id']
)


def setup_telemetry(
    app,
    service_name: str = "trading-backend",
    service_version: str = "1.0.0",
    metrics_port: int = 8001
) -> metrics.Meter:
    """
    Set up OpenTelemetry instrumentation for the application.
    
    Args:
        app: FastAPI application instance
        service_name: Name of the service for identification
        service_version: Version of the service
        metrics_port: Port to expose Prometheus metrics endpoint
        
    Returns:
        Meter instance for creating custom metrics
    """
    global _meter
    
    # Define resource (service identity)
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        DEPLOYMENT_ENVIRONMENT: os.getenv("ENV", "development"),
        "service.namespace": "trading-platform",
    })
    
    logger.info(f"Setting up OpenTelemetry for {service_name}")
    
    # Setup Metrics with Prometheus exporter
    prometheus_reader = PrometheusMetricReader()
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[prometheus_reader]
    )
    metrics.set_meter_provider(meter_provider)
    
    # Setup Traces
    trace_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(trace_provider)
    
    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI auto-instrumentation enabled")
    
    # Auto-instrument SQLAlchemy
    SQLAlchemyInstrumentor().instrument()
    logger.info("SQLAlchemy auto-instrumentation enabled")
    
    # Auto-instrument Redis
    RedisInstrumentor().instrument()
    logger.info("Redis auto-instrumentation enabled")
    
    # Start Prometheus metrics HTTP server
    try:
        start_http_server(port=metrics_port)
        logger.info(f"Prometheus metrics endpoint started on port {metrics_port}")
    except OSError as e:
        logger.warning(f"Failed to start metrics server on port {metrics_port}: {e}")
    
    # Create and cache meter
    _meter = meter_provider.get_meter(service_name)
    
    # Setup system metrics collection (for backend only)
    if service_name == "trading-backend" and app is not None:
        setup_system_metrics(_meter)
    
    # Start process metrics collection thread
    start_process_metrics_collection(service_name)
    
    logger.info(f"OpenTelemetry setup complete for {service_name}")
    
    return _meter


def get_meter() -> metrics.Meter:
    """
    Get the global meter instance.
    
    Returns:
        Meter instance for creating metrics
        
    Raises:
        RuntimeError: If telemetry hasn't been set up yet
    """
    if _meter is None:
        raise RuntimeError("Telemetry not initialized. Call setup_telemetry() first.")
    return _meter


def setup_telemetry_minimal(
    service_name: str = "trading-worker",
    service_version: str = "1.0.0",
    metrics_port: int = 8001
) -> metrics.Meter:
    """
    Set up OpenTelemetry instrumentation for non-web services (Celery workers).
    
    This is a minimal version that doesn't require a FastAPI app.
    
    Args:
        service_name: Name of the service for identification
        service_version: Version of the service
        metrics_port: Port to expose Prometheus metrics endpoint
        
    Returns:
        Meter instance for creating custom metrics
    """
    global _meter
    
    # Define resource (service identity)
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        DEPLOYMENT_ENVIRONMENT: os.getenv("ENV", "development"),
        "service.namespace": "trading-platform",
    })
    
    logger.info(f"Setting up OpenTelemetry for {service_name} on port {metrics_port}")
    
    # Start Prometheus HTTP server for metrics
    try:
        from prometheus_client import start_http_server
        start_http_server(metrics_port)
        logger.info(f"Prometheus metrics server started on port {metrics_port}")
    except OSError as e:
        if "Address already in use" in str(e):
            logger.warning(f"Metrics port {metrics_port} already in use (expected for worker forks)")
        else:
            logger.error(f"Failed to start metrics server: {e}")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")
    
    # Setup Metrics with Prometheus exporter
    prometheus_reader = PrometheusMetricReader()
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[prometheus_reader]
    )
    metrics.set_meter_provider(meter_provider)
    
    # Setup Traces
    trace_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(trace_provider)
    
    # Auto-instrument SQLAlchemy
    try:
        SQLAlchemyInstrumentor().instrument()
        logger.info("SQLAlchemy auto-instrumentation enabled")
    except Exception as e:
        logger.warning(f"Failed to instrument SQLAlchemy: {e}")
    
    # Auto-instrument Redis
    try:
        RedisInstrumentor().instrument()
        logger.info("Redis auto-instrumentation enabled")
    except Exception as e:
        logger.warning(f"Failed to instrument Redis: {e}")
    
    # Start Prometheus metrics HTTP server
    try:
        start_http_server(port=metrics_port)
        logger.info(f"Prometheus metrics endpoint started on port {metrics_port}")
    except OSError as e:
        logger.warning(f"Failed to start metrics server on port {metrics_port}: {e}")
    
    # Create and cache meter
    _meter = meter_provider.get_meter(service_name)
    
    # Start process metrics collection thread
    start_process_metrics_collection(service_name)
    
    logger.info(f"OpenTelemetry setup complete for {service_name}")
    
    return _meter


def start_process_metrics_collection(service_name: str, interval: int = 15):
    """
    Start background thread to collect process resource metrics.
    
    Args:
        service_name: Name of the service for labeling
        interval: Collection interval in seconds
    """
    process = psutil.Process()
    
    def collect_metrics():
        while True:
            try:
                # CPU percentage
                cpu_percent = process.cpu_percent(interval=1)
                process_cpu_percent.labels(service=service_name).set(cpu_percent)
                
                # Memory info
                mem_info = process.memory_info()
                process_memory_bytes.labels(service=service_name, type='rss').set(mem_info.rss)
                process_memory_bytes.labels(service=service_name, type='vms').set(mem_info.vms)
                
                # Threads
                num_threads = process.num_threads()
                process_threads.labels(service=service_name).set(num_threads)
                
                # Open files
                try:
                    num_fds = len(process.open_files())
                    process_open_files.labels(service=service_name).set(num_fds)
                except (psutil.AccessDenied, AttributeError):
                    pass  # May not have permission on some systems
                    
            except Exception as e:
                logger.error(f"Error collecting process metrics: {e}")
            
            time.sleep(interval)
    
    # Start daemon thread
    metrics_thread = threading.Thread(target=collect_metrics, daemon=True)
    metrics_thread.start()
    logger.info(f"Process metrics collection started for {service_name}")


def get_tracer(name: str = __name__) -> trace.Tracer:
    """
    Get a tracer for creating spans.
    
    Args:
        name: Name of the tracer (usually __name__ of the module)
        
    Returns:
        Tracer instance
    """
    return trace.get_tracer(name)


# Common metric helpers
class MetricsHelper:
    """Helper class for commonly used metrics patterns."""
    
    def __init__(self, meter: metrics.Meter):
        self.meter = meter
        self._counters = {}
        self._histograms = {}
        self._gauges = {}
    
    def counter(self, name: str, description: str = "", unit: str = "1") -> metrics.Counter:
        """Get or create a counter metric."""
        if name not in self._counters:
            self._counters[name] = self.meter.create_counter(
                name=name,
                description=description,
                unit=unit
            )
        return self._counters[name]
    
    def histogram(self, name: str, description: str = "", unit: str = "1") -> metrics.Histogram:
        """Get or create a histogram metric."""
        if name not in self._histograms:
            self._histograms[name] = self.meter.create_histogram(
                name=name,
                description=description,
                unit=unit
            )
        return self._histograms[name]
    
    def gauge(self, name: str, description: str = "", unit: str = "1"):
        """Get or create an observable gauge metric."""
        if name not in self._gauges:
            self._gauges[name] = self.meter.create_observable_gauge(
                name=name,
                description=description,
                unit=unit
            )
        return self._gauges[name]


def setup_system_metrics(meter: metrics.Meter):
    """
    Setup system metrics collection using prometheus_client Gauges.
    
    These metrics are updated periodically and exposed via the Prometheus HTTP endpoint.
    
    Args:
        meter: OpenTelemetry meter instance (unused, kept for API compatibility)
    """
    global _system_gauges
    from app.metrics.system_metrics import system_metrics_collector
    
    logger.info("Setting up system metrics collection with prometheus_client")
    
    # Create Prometheus Gauges (these are automatically exposed on /metrics)
    _system_gauges['active_pipelines'] = Gauge(
        'system_active_pipelines',
        'Number of active pipelines'
    )
    _system_gauges['active_users'] = Gauge(
        'system_active_users',
        'Number of active users with active pipelines'
    )
    _system_gauges['success_rate_24h'] = Gauge(
        'system_success_rate_24h_percent',
        'Success rate of executions in last 24 hours (percentage)'
    )
    _system_gauges['executions_today'] = Gauge(
        'system_executions_today_executions',
        'Number of executions started today'
    )
    _system_gauges['executions_running'] = Gauge(
        'system_executions_running_executions',
        'Number of currently running executions'
    )
    _system_gauges['executions_pending'] = Gauge(
        'system_executions_pending_executions',
        'Number of pending executions'
    )
    
    # Start background task to update metrics periodically
    import threading
    import time
    
    def update_metrics_loop():
        """Background task to update metrics every 15 seconds."""
        while True:
            try:
                metrics_data = system_metrics_collector.collect_all_metrics()
                
                _system_gauges['active_pipelines'].set(metrics_data.get('active_pipelines', 0))
                _system_gauges['active_users'].set(metrics_data.get('active_users', 0))
                _system_gauges['success_rate_24h'].set(metrics_data.get('success_rate_24h', 0.0))
                _system_gauges['executions_today'].set(metrics_data.get('executions_today', 0))
                _system_gauges['executions_running'].set(metrics_data.get('executions_running', 0))
                _system_gauges['executions_pending'].set(metrics_data.get('executions_pending', 0))
                
                logger.debug("system_metrics_updated", metrics=metrics_data)
            except Exception as e:
                logger.error("system_metrics_update_failed", error=str(e), exc_info=True)
            
            time.sleep(15)  # Update every 15 seconds
    
    # Start update thread as daemon (will stop when main program exits)
    update_thread = threading.Thread(target=update_metrics_loop, daemon=True)
    update_thread.start()
    
    logger.info("System metrics collection configured and background updater started")


