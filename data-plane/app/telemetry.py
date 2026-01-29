"""OpenTelemetry configuration for Data Plane"""
import structlog
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
    
    return _meter


def get_meter():
    """Get the global meter instance"""
    return _meter

