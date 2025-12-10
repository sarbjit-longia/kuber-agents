"""
OpenTelemetry Configuration for Signal Generator

This module sets up observability with OpenTelemetry for metrics.
Supports both local (Prometheus) and cloud (AWS CloudWatch) backends.
"""
import logging
from typing import Optional

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION, DEPLOYMENT_ENVIRONMENT
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server
import os

logger = logging.getLogger(__name__)

# Global meter instance
_meter: Optional[metrics.Meter] = None


def setup_telemetry(
    service_name: str = "signal-generator",
    service_version: str = "1.0.0",
    metrics_port: int = 8001
) -> metrics.Meter:
    """
    Set up OpenTelemetry instrumentation for the signal generator.
    
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

