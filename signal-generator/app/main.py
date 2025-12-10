"""
Signal Generator Service

Main entry point for the signal generator service.
Runs configured signal generators and emits signals to stdout (Phase 1)
or Kafka (Phase 2).
"""
import asyncio
import json
import time
from datetime import datetime
from typing import List, Optional
import structlog
from kafka import KafkaProducer
from kafka.errors import KafkaError

from app.config import settings
from app.generators import get_registry, MockSignalGenerator, GoldenCrossSignalGenerator
from app.schemas.signal import Signal
from app.telemetry import setup_telemetry


# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()


class SignalGeneratorService:
    """
    Signal generator service that runs multiple generators.
    
    In Phase 1, signals are emitted to stdout/logs.
    In Phase 2, signals are published to Kafka.
    """
    
    def __init__(self):
        """Initialize the service with configured generators."""
        self.registry = get_registry()
        self.generators = []
        self.running = False
        self.kafka_producer: Optional[KafkaProducer] = None
        
        # Initialize telemetry
        try:
            self.meter = setup_telemetry(service_name="signal-generator")
            self._setup_metrics()
            logger.info("telemetry_initialized")
        except Exception as e:
            logger.error("telemetry_initialization_failed", error=str(e))
            self.meter = None
        
        # Initialize Kafka producer
        self._initialize_kafka()
    
    def _setup_metrics(self):
        """Setup custom metrics."""
        if not self.meter:
            return
        
        self.signals_generated = self.meter.create_counter(
            "signals_generated_total",
            description="Total signals generated",
            unit="1"
        )
        
        self.signal_generation_duration = self.meter.create_histogram(
            "signal_generation_duration_seconds",
            description="Time taken to generate signals",
            unit="s"
        )
        
        self.kafka_publish_duration = self.meter.create_histogram(
            "kafka_publish_duration_seconds",
            description="Time taken to publish signal to Kafka",
            unit="s"
        )
        
        self.kafka_publish_success = self.meter.create_counter(
            "kafka_publish_success_total",
            description="Total successful Kafka publishes",
            unit="1"
        )
        
        self.kafka_publish_failure = self.meter.create_counter(
            "kafka_publish_failure_total",
            description="Total failed Kafka publishes",
            unit="1"
        )
        
        # Initialize generators based on configuration
        self._initialize_generators()
    
    def _initialize_kafka(self):
        """Initialize Kafka producer for signal publishing."""
        try:
            self.kafka_producer = KafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',  # Wait for all replicas to acknowledge
                retries=3,
                max_in_flight_requests_per_connection=1  # Ensure ordering
            )
            logger.info(
                "kafka_producer_initialized",
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                topic=settings.KAFKA_SIGNAL_TOPIC
            )
        except Exception as e:
            logger.error(
                "kafka_producer_initialization_failed",
                error=str(e),
                exc_info=True
            )
            self.kafka_producer = None
            logger.warning("signals_will_only_log", message="Kafka unavailable, falling back to logs only")
    
    def _initialize_generators(self):
        """Initialize all configured generators."""
        watchlist = settings.get_watchlist()
        
        # Mock generator (for testing)
        from app.schemas.signal import BiasType
        
        mock_config = {
            "tickers": watchlist[:3],  # First 3 tickers
            "emission_probability": 0.3,
            "bias_options": [BiasType.BULLISH, BiasType.BEARISH]
        }
        self.generators.append({
            "name": "mock",
            "generator": MockSignalGenerator(mock_config),
            "interval": settings.MOCK_GENERATOR_INTERVAL_SECONDS
        })
        
        # Golden cross generator
        golden_cross_config = {
            "tickers": watchlist,
            "sma_short": settings.GOLDEN_CROSS_SMA_SHORT,
            "sma_long": settings.GOLDEN_CROSS_SMA_LONG,
            "timeframe": settings.GOLDEN_CROSS_TIMEFRAME,
            "lookback_days": 5,
            "confidence": 0.85
        }
        self.generators.append({
            "name": "golden_cross",
            "generator": GoldenCrossSignalGenerator(golden_cross_config),
            "interval": settings.GOLDEN_CROSS_CHECK_INTERVAL_SECONDS
        })
        
        logger.info(
            "generators_initialized",
            count=len(self.generators),
            generators=[g["name"] for g in self.generators]
        )
    
    async def run_generator(self, generator_info: dict):
        """
        Run a single generator in a loop.
        
        Args:
            generator_info: Dict with generator, interval, and name
        """
        generator = generator_info["generator"]
        interval = generator_info["interval"]
        name = generator_info["name"]
        
        logger.info(
            "generator_started",
            generator=name,
            interval_seconds=interval
        )
        
        while self.running:
            try:
                # Track generation time
                start_time = time.time()
                
                # Generate signals
                signals = await generator.generate()
                
                # Record generation duration
                if self.meter and signals:
                    gen_duration = time.time() - start_time
                    self.signal_generation_duration.record(
                        gen_duration,
                        {"generator": name, "signal_type": signals[0].signal_type.value}
                    )
                
                if signals:
                    # Emit signals (Phase 1: just log them)
                    await self._emit_signals(signals)
                
            except Exception as e:
                logger.error(
                    "generator_error",
                    generator=name,
                    error=str(e),
                    exc_info=True
                )
            
            # Wait for next interval
            await asyncio.sleep(interval)
    
    async def _emit_signals(self, signals: List[Signal]):
        """
        Emit signals to output.
        
        Phase 1: Log to stdout/file
        Phase 2: Publish to Kafka
        
        Args:
            signals: List of signals to emit
        """
        for signal in signals:
            # Convert to Kafka-ready format
            message = signal.to_kafka_message()
            
            # Track metrics
            if self.meter:
                self.signals_generated.add(1, {
                    "signal_type": signal.signal_type.value,
                    "source": signal.source
                })
            
            # Phase 2: Publish to Kafka
            if self.kafka_producer:
                publish_start = time.time()
                try:
                    # Use signal_type as the key for partitioning
                    key = signal.signal_type.value
                    
                    future = self.kafka_producer.send(
                        settings.KAFKA_SIGNAL_TOPIC,
                        key=key,
                        value=message
                    )
                    
                    # Wait for acknowledgment (with timeout)
                    record_metadata = future.get(timeout=10)
                    
                    # Record successful publish
                    if self.meter:
                        publish_duration = time.time() - publish_start
                        self.kafka_publish_duration.record(publish_duration, {
                            "signal_type": signal.signal_type.value
                        })
                        self.kafka_publish_success.add(1, {
                            "signal_type": signal.signal_type.value
                        })
                    
                    logger.info(
                        "signal_published_to_kafka",
                        signal_id=str(signal.signal_id),
                        topic=record_metadata.topic,
                        partition=record_metadata.partition,
                        offset=record_metadata.offset
                    )
                except KafkaError as e:
                    # Record failed publish
                    if self.meter:
                        self.kafka_publish_failure.add(1, {
                            "signal_type": signal.signal_type.value,
                            "error_type": type(e).__name__
                        })
                    
                    logger.error(
                        "kafka_publish_failed",
                        signal_id=str(signal.signal_id),
                        error=str(e),
                        exc_info=True
                    )
                except Exception as e:
                    # Record failed publish
                    if self.meter:
                        self.kafka_publish_failure.add(1, {
                            "signal_type": signal.signal_type.value,
                            "error_type": type(e).__name__
                        })
                    
                    logger.error(
                        "unexpected_kafka_error",
                        signal_id=str(signal.signal_id),
                        error=str(e),
                        exc_info=True
                    )
            
            # Also log the signal (structured logging)
            logger.info(
                "signal_emitted",
                signal_id=str(signal.signal_id),
                signal_type=signal.signal_type.value,
                source=signal.source,
                timestamp=int(signal.timestamp.timestamp()),
                tickers=[
                    {
                        "ticker": ts.ticker,
                        "signal": ts.signal.value,
                        "confidence": ts.confidence
                    }
                    for ts in signal.tickers
                ]
            )
            
            # Also print to stdout in a nice format for visibility
            print("\n" + "="*80)
            print(f"🔔 SIGNAL GENERATED: {signal.signal_type.value.upper()}")
            print(f"   ID: {signal.signal_id}")
            print(f"   Source: {signal.source}")
            print(f"   Timestamp: {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            if self.kafka_producer:
                print(f"   📤 Published to Kafka: {settings.KAFKA_SIGNAL_TOPIC}")
            
            print(f"   Tickers:")
            
            for ticker_signal in signal.tickers:
                print(f"     • {ticker_signal.ticker}: {ticker_signal.signal.value} (confidence: {ticker_signal.confidence:.0f}%)")
                if ticker_signal.reasoning:
                    print(f"       → {ticker_signal.reasoning}")
            
            if signal.metadata:
                print(f"   Metadata: {json.dumps(signal.metadata, indent=6)}")
            
            print("="*80 + "\n")
    
    async def start(self):
        """Start all generators."""
        self.running = True
        
        logger.info(
            "signal_generator_service_starting",
            service=settings.SERVICE_NAME,
            generators=len(self.generators)
        )
        
        print(f"\n🚀 Signal Generator Service Starting...")
        print(f"   Generators: {len(self.generators)}")
        print(f"   Watchlist: {settings.get_watchlist()}")
        print(f"   Log Level: {settings.LOG_LEVEL}\n")
        
        # Start all generators as concurrent tasks
        tasks = [
            asyncio.create_task(self.run_generator(gen_info))
            for gen_info in self.generators
        ]
        
        # Wait for all tasks (runs indefinitely until interrupted)
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("signal_generator_service_cancelled")
            raise
    
    async def stop(self):
        """Stop all generators and cleanup resources."""
        self.running = False
        
        # Close Kafka producer
        if self.kafka_producer:
            try:
                self.kafka_producer.flush(timeout=5)
                self.kafka_producer.close(timeout=5)
                logger.info("kafka_producer_closed")
            except Exception as e:
                logger.error("kafka_producer_close_error", error=str(e))
        
        logger.info("signal_generator_service_stopping")
        print("\n🛑 Signal Generator Service Stopping...\n")


async def main():
    """Main entry point."""
    service = SignalGeneratorService()
    
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
        await service.stop()
    except Exception as e:
        logger.error("service_crashed", error=str(e), exc_info=True)
        await service.stop()
        raise


if __name__ == "__main__":
    asyncio.run(main())

