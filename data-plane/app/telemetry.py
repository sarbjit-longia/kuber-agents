"""OpenTelemetry configuration for Data Plane"""
import structlog
import psutil
import threading
import time
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import start_http_server, Gauge, Counter, Histogram

logger = structlog.get_logger()

_meter_provider = None
_meter = None

# Prometheus metrics for rate limiting and API calls
api_rate_limit_remaining = Gauge(
    'api_rate_limit_remaining',
    'Remaining API calls in the current window',
    ['provider']
)

api_rate_limit_total = Gauge(
    'api_rate_limit_total',
    'Total API calls allowed per window',
    ['provider']
)

api_calls_total = Counter(
    'api_calls_total',
    'Total API calls made',
    ['provider', 'endpoint', 'status']
)

api_call_duration_seconds = Histogram(
    'api_call_duration_seconds',
    'API call duration in seconds',
    ['provider', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Provider bandwidth tracking
provider_bandwidth_bytes_total = Counter(
    'provider_bandwidth_bytes_total',
    'Total bytes received from data providers',
    ['provider', 'endpoint']
)

# Candle cache metrics
candle_cache_hits_total = Counter(
    'candle_cache_hits_total',
    'Total candle cache hits in Redis',
    ['timeframe']
)

candle_cache_misses_total = Counter(
    'candle_cache_misses_total',
    'Total candle cache misses in Redis',
    ['timeframe']
)

# TimescaleDB metrics
timescale_candles_written_total = Counter(
    'timescale_candles_written_total',
    'Total candle rows written to TimescaleDB',
    ['timeframe']
)

timescale_aggregates_read_total = Counter(
    'timescale_aggregates_read_total',
    'Total rows read from TimescaleDB continuous aggregates',
    ['timeframe']
)

timescale_aggregate_refresh_seconds = Histogram(
    'timescale_aggregate_refresh_seconds',
    'Duration of continuous aggregate refresh in seconds',
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

# Prefetch task metrics
prefetch_task_duration_seconds = Histogram(
    'prefetch_task_duration_seconds',
    'Duration of prefetch Celery tasks in seconds',
    ['task'],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

# Process resource metrics
process_cpu_percent = Gauge(
    'process_cpu_percent',
    'CPU usage percentage of this process',
    ['service']
)

process_memory_bytes = Gauge(
    'process_memory_bytes',
    'Memory usage in bytes of this process',
    ['service', 'type']  # type: rss, vms
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


def setup_telemetry(app=None, service_name="data-plane", metrics_port=8001):
    """
    Setup OpenTelemetry instrumentation
    
    Args:
        app: FastAPI app (optional, for FastAPI instrumentation)
        service_name: Service name for metrics
        metrics_port: Port to expose Prometheus metrics
    """
    global _meter_provider, _meter
    
    logger.info("setting_up_telemetry", service=service_name, metrics_port=metrics_port)
    
    # Create resource
    resource = Resource(attributes={
        "service.name": service_name,
    })
    
    # Setup Prometheus exporter
    prometheus_reader = PrometheusMetricReader()
    
    # Create meter provider
    _meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[prometheus_reader]
    )
    
    # Set global meter provider
    metrics.set_meter_provider(_meter_provider)
    
    # Get meter for this service
    _meter = _meter_provider.get_meter(service_name)
    
    # Auto-instrument libraries
    if app:
        FastAPIInstrumentor.instrument_app(app)
        logger.info("fastapi_instrumented")
    
    SQLAlchemyInstrumentor().instrument()
    logger.info("sqlalchemy_instrumented")
    
    RedisInstrumentor().instrument()
    logger.info("redis_instrumented")
    
    HTTPXClientInstrumentor().instrument()
    logger.info("httpx_instrumented")
    
    # Start Prometheus metrics server
    try:
        start_http_server(port=metrics_port, addr="0.0.0.0")
        logger.info("prometheus_metrics_server_started", port=metrics_port)
    except OSError as e:
        # Port already in use (multiple workers or already started)
        logger.warning("prometheus_metrics_server_already_running", port=metrics_port, error=str(e))
    
    # Start process metrics collection thread
    start_process_metrics_collection(service_name)
    
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
                logger.error("process_metrics_collection_error", error=str(e))
            
            time.sleep(interval)
    
    # Start daemon thread
    metrics_thread = threading.Thread(target=collect_metrics, daemon=True)
    metrics_thread.start()
    logger.info("process_metrics_collection_started", service=service_name)


def get_meter():
    """Get the global meter instance"""
    return _meter

