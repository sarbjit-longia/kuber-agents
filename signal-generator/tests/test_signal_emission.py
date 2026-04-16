import importlib
import sys
from collections import deque
from datetime import datetime

import pytest
from kafka.errors import KafkaTimeoutError

from app.schemas.signal import BiasType, Signal, SignalType, TickerSignal


class _FakeLogger:
    def __init__(self):
        self.info_events = []
        self.error_events = []
        self.warning_events = []

    def info(self, event, **kwargs):
        self.info_events.append((event, kwargs))

    def error(self, event, **kwargs):
        self.error_events.append((event, kwargs))

    def warning(self, event, **kwargs):
        self.warning_events.append((event, kwargs))


class _FakeRecordMetadata:
    topic = 'trading-signals'
    partition = 0
    offset = 42


class _FakeFuture:
    def __init__(self, error=None):
        self.error = error

    def get(self, timeout=10):
        if self.error is not None:
            raise self.error
        return _FakeRecordMetadata()


class _FakeProducer:
    def __init__(self, error=None):
        self.error = error

    def send(self, topic, key, value):
        return _FakeFuture(error=self.error)


def _load_main_module(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    sys.modules.pop('app.main', None)
    return importlib.import_module('app.main')


def _build_service(service_cls, producer):
    service = service_cls.__new__(service_cls)
    service.kafka_producer = producer
    service.scanner_universe = None
    service.recent_signals = deque(maxlen=50)
    service.meter = None
    service.metrics = None
    return service


def _build_signal():
    return Signal(
        signal_type=SignalType.CCI_OVERBOUGHT,
        source='cci_generator',
        timestamp=datetime(2026, 4, 16, 0, 49, 27),
        tickers=[
            TickerSignal(
                ticker='AUD_USD',
                signal=BiasType.BEARISH,
                confidence=70.0,
                reasoning='CCI overbought'
            )
        ],
        metadata={}
    )


@pytest.mark.asyncio
async def test_emit_signals_logs_emitted_only_after_kafka_ack(monkeypatch, tmp_path, capsys):
    main_module = _load_main_module(monkeypatch, tmp_path)
    fake_logger = _FakeLogger()
    monkeypatch.setattr(main_module, 'logger', fake_logger)

    service = _build_service(main_module.SignalGeneratorService, _FakeProducer())
    await service._emit_signals([_build_signal()], generator_name='cci_generator')

    info_events = [event for event, _ in fake_logger.info_events]
    assert 'signal_generated' in info_events
    assert 'signal_published_to_kafka' in info_events
    assert 'signal_emitted' in info_events

    emitted_payload = next(payload for event, payload in fake_logger.info_events if event == 'signal_emitted')
    assert emitted_payload['topic'] == 'trading-signals'
    assert emitted_payload['offset'] == 42

    output = capsys.readouterr().out
    assert 'Published to Kafka: trading-signals' in output
    assert 'Kafka publish failed' not in output


@pytest.mark.asyncio
async def test_emit_signals_does_not_log_emitted_when_kafka_publish_fails(monkeypatch, tmp_path, capsys):
    main_module = _load_main_module(monkeypatch, tmp_path)
    fake_logger = _FakeLogger()
    monkeypatch.setattr(main_module, 'logger', fake_logger)

    service = _build_service(
        main_module.SignalGeneratorService,
        _FakeProducer(error=KafkaTimeoutError('Timeout after waiting for 10 secs.'))
    )
    await service._emit_signals([_build_signal()], generator_name='cci_generator')

    info_events = [event for event, _ in fake_logger.info_events]
    assert 'signal_generated' in info_events
    assert 'signal_published_to_kafka' not in info_events
    assert 'signal_emitted' not in info_events

    generated_payload = next(payload for event, payload in fake_logger.info_events if event == 'signal_generated')
    assert generated_payload['kafka_published'] is False
    assert 'Timeout after waiting for 10 secs.' in generated_payload['publish_error']

    error_events = [event for event, _ in fake_logger.error_events]
    assert 'kafka_publish_failed' in error_events

    output = capsys.readouterr().out
    assert 'Kafka publish failed: KafkaTimeoutError' in output or 'Kafka publish failed: Timeout after waiting for 10 secs.' in output
    assert 'Published to Kafka: trading-signals' not in output
