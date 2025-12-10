"""
OpenTelemetry Configuration for Trading Platform

This module sets up observability with OpenTelemetry for metrics, traces, and logs.
Supports both local (Prometheus) and cloud (AWS CloudWatch/X-Ray) backends.
"""
import os
import logging
from typing import Optional

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION, DEPLOYMENT_ENVIRONMENT
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from prometheus_client import start_http_server

logger = logging.getLogger(__name__)

# Global meter instance
_meter: Optional[metrics.Meter] = None


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
    
    logger.info(f"OpenTelemetry setup complete for {service_name}")
    
    return _meter


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

