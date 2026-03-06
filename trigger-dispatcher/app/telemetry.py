"""
Telemetry Configuration for Trigger Dispatcher

Sets up Prometheus metrics and process resource monitoring.
Uses native prometheus_client for reliable cross-platform metrics export.
"""
import logging
from typing import Optional
import psutil
import threading
import time

from prometheus_client import start_http_server, Gauge, Counter, Histogram, REGISTRY
import os

logger = logging.getLogger(__name__)


# ── Process resource metrics ──────────────────────────────────────────────

process_cpu_percent = Gauge(
    'process_cpu_percent',
    'CPU usage percentage of this process',
    ['service']
)

process_memory_bytes = Gauge(
    'process_memory_bytes',
    'Memory usage in bytes of this process',
    ['service', 'type']
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


# ── Signal consumption metrics ───────────────────────────────────────────

signals_consumed_total = Counter(
    'signals_consumed_total',
    'Total signals consumed from Kafka',
)

pipelines_matched_total = Counter(
    'pipelines_matched_total',
    'Total pipelines matched to signals',
)

pipelines_enqueued_total = Counter(
    'pipelines_enqueued_total',
    'Total pipelines enqueued for execution',
)

pipelines_skipped_running_total = Counter(
    'pipelines_skipped_running_total',
    'Total pipelines skipped (already running)',
)

batch_size_histogram = Histogram(
    'batch_size',
    'Signal batch size',
)

batch_processing_duration_seconds = Histogram(
    'batch_processing_duration_seconds',
    'Time to process a batch of signals',
)

pipeline_cache_size_gauge = Gauge(
    'pipeline_cache_size',
    'Number of pipelines in cache',
)


class MetricsCollector:
    """Wrapper that provides the same interface as the OTel meter-based metrics."""

    def __init__(self):
        self.signals_consumed = _CounterAdapter(signals_consumed_total)
        self.pipelines_matched = _CounterAdapter(pipelines_matched_total)
        self.pipelines_enqueued = _CounterAdapter(pipelines_enqueued_total)
        self.pipelines_skipped = _CounterAdapter(pipelines_skipped_running_total)
        self.batch_size_histogram = _HistogramAdapter(batch_size_histogram)
        self.batch_processing_duration = _HistogramAdapter(batch_processing_duration_seconds)
        self.cache_size = _GaugeAdapter(pipeline_cache_size_gauge)


class _CounterAdapter:
    """Adapts prometheus_client Counter to OTel-like .add(amount, attributes) interface."""

    def __init__(self, counter: Counter):
        self._counter = counter

    def add(self, amount, attributes=None):
        if attributes:
            self._counter.labels(**attributes).inc(amount)
        else:
            self._counter.inc(amount)


class _HistogramAdapter:
    """Adapts prometheus_client Histogram to OTel-like .record(value, attributes) interface."""

    def __init__(self, histogram: Histogram):
        self._histogram = histogram

    def record(self, value, attributes=None):
        if attributes:
            self._histogram.labels(**attributes).observe(value)
        else:
            self._histogram.observe(value)


class _GaugeAdapter:
    """Adapts prometheus_client Gauge to OTel-like UpDownCounter .add(delta) / .set(value) interface."""

    def __init__(self, gauge: Gauge):
        self._gauge = gauge

    def add(self, delta, attributes=None):
        """For UpDownCounter compatibility — just set the absolute value instead."""
        # OTel UpDownCounter uses delta, but Gauge.set is simpler and more correct
        if attributes:
            self._gauge.labels(**attributes).inc(delta)
        else:
            self._gauge.inc(delta)

    def set(self, value, attributes=None):
        if attributes:
            self._gauge.labels(**attributes).set(value)
        else:
            self._gauge.set(value)


def setup_telemetry(
    service_name: str = "trigger-dispatcher",
    service_version: str = "1.0.0",
    metrics_port: int = 8001
) -> MetricsCollector:
    """
    Set up Prometheus metrics for the trigger dispatcher.

    Returns:
        MetricsCollector with counters/histograms matching the OTel interface.
    """
    # Start Prometheus metrics HTTP server
    try:
        start_http_server(port=metrics_port)
        logger.info(f"Prometheus metrics endpoint started on port {metrics_port}")
    except OSError as e:
        logger.warning(f"Failed to start metrics server on port {metrics_port}: {e}")

    # Start process metrics collection thread
    start_process_metrics_collection(service_name)

    logger.info(f"Telemetry setup complete for {service_name}")

    return MetricsCollector()


def start_process_metrics_collection(service_name: str, interval: int = 15):
    """Start background thread to collect process resource metrics."""
    process = psutil.Process()

    def collect_metrics():
        while True:
            try:
                cpu_percent = process.cpu_percent(interval=1)
                process_cpu_percent.labels(service=service_name).set(cpu_percent)

                mem_info = process.memory_info()
                process_memory_bytes.labels(service=service_name, type='rss').set(mem_info.rss)
                process_memory_bytes.labels(service=service_name, type='vms').set(mem_info.vms)

                num_threads = process.num_threads()
                process_threads.labels(service=service_name).set(num_threads)

                try:
                    num_fds = len(process.open_files())
                    process_open_files.labels(service=service_name).set(num_fds)
                except (psutil.AccessDenied, AttributeError):
                    pass
            except Exception as e:
                logger.error(f"Error collecting process metrics: {e}")

            time.sleep(interval)

    metrics_thread = threading.Thread(target=collect_metrics, daemon=True)
    metrics_thread.start()
    logger.info(f"Process metrics collection started for {service_name}")


def get_meter() -> MetricsCollector:
    """Get a new MetricsCollector instance."""
    return MetricsCollector()
