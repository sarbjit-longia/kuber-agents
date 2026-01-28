"""
Trigger Dispatcher Service - Main Module

This service consumes trading signals from Kafka and triggers matching pipelines.

Architecture:
- In-memory pipeline cache (refreshed every 30s)
- Batch signal processing (500ms window or 20 signals)
- Single DB query per batch for execution status
- Bulk Celery task enqueuing
"""
import asyncio
import json
import time
from typing import List, Dict, Set, Any
from datetime import datetime, timezone

import structlog
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from sqlalchemy import select, and_, cast, String
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from celery import Celery

from app.config import settings
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


# Database setup
engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Celery setup
celery_app = Celery(
    "trigger_dispatcher",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)


class Signal:
    """Simple signal model for deserialization."""
    def __init__(self, data: Dict[str, Any]):
        self.signal_id = data.get("signal_id")
        self.signal_type = data.get("signal_type")
        self.source = data.get("source")
        self.timestamp = data.get("timestamp")
        self.tickers = data.get("tickers", [])
        self.metadata = data.get("metadata", {})
    
    def get_ticker_symbols(self) -> Set[str]:
        """Extract ticker symbols from signal."""
        return {ticker.get("ticker") for ticker in self.tickers if ticker.get("ticker")}


class TriggerDispatcher:
    """
    Trigger Dispatcher Service
    
    Consumes signals from Kafka, matches them to pipelines,
    and enqueues Celery tasks for execution.
    """
    
    def __init__(self):
        """Initialize the dispatcher."""
        self.pipeline_cache: Dict[str, Dict[str, Any]] = {}
        self.last_cache_refresh: float = 0
        self.last_cache_size: int = 0  # Track last cache size for delta calculation
        self.signal_buffer: List[Signal] = []
        self.last_batch_process: float = time.time()
        self.running = False
        self.kafka_consumer = None
        
        # Initialize telemetry
        try:
            self.meter = setup_telemetry(service_name="trigger-dispatcher")
            self._setup_metrics()
            logger.info("telemetry_initialized")
        except Exception as e:
            logger.error("telemetry_initialization_failed", error=str(e))
            self.meter = None
        
        logger.info(
            "trigger_dispatcher_initialized",
            batch_size=settings.BATCH_SIZE,
            batch_timeout=settings.BATCH_TIMEOUT_SECONDS,
            cache_refresh_interval=settings.CACHE_REFRESH_INTERVAL_SECONDS
        )
    
    def _setup_metrics(self):
        """Setup custom metrics."""
        if not self.meter:
            return
        
        self.signals_consumed = self.meter.create_counter(
            "signals_consumed_total",
            description="Total signals consumed from Kafka",
            unit="1"
        )
        
        self.pipelines_matched = self.meter.create_counter(
            "pipelines_matched_total",
            description="Total pipelines matched to signals",
            unit="1"
        )
        
        self.pipelines_enqueued = self.meter.create_counter(
            "pipelines_enqueued_total",
            description="Total pipelines enqueued for execution",
            unit="1"
        )
        
        self.pipelines_skipped = self.meter.create_counter(
            "pipelines_skipped_running_total",
            description="Total pipelines skipped (already running)",
            unit="1"
        )
        
        self.batch_size_histogram = self.meter.create_histogram(
            "batch_size",
            description="Signal batch size",
            unit="1"
        )
        
        self.batch_processing_duration = self.meter.create_histogram(
            "batch_processing_duration_seconds",
            description="Time to process a batch of signals",
            unit="s"
        )
        
        self.cache_size = self.meter.create_up_down_counter(
            "pipeline_cache_size",
            description="Number of pipelines in cache",
            unit="1"
        )
    
    def _initialize_kafka_consumer(self):
        """Initialize Kafka consumer."""
        try:
            self.kafka_consumer = KafkaConsumer(
                settings.KAFKA_SIGNAL_TOPIC,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=settings.KAFKA_CONSUMER_GROUP,
                auto_offset_reset=settings.KAFKA_AUTO_OFFSET_RESET,
                enable_auto_commit=False,  # Manual commit after processing
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                consumer_timeout_ms=100  # Non-blocking poll
            )
            logger.info(
                "kafka_consumer_initialized",
                topic=settings.KAFKA_SIGNAL_TOPIC,
                group_id=settings.KAFKA_CONSUMER_GROUP
            )
        except Exception as e:
            logger.error(
                "kafka_consumer_initialization_failed",
                error=str(e),
                exc_info=True
            )
            raise
    
    async def refresh_pipeline_cache(self):
        """
        Refresh in-memory cache of active signal-based pipelines.
        
        This runs every 30 seconds to pick up new/updated pipelines.
        Fetches scanner tickers from scanners table.
        """
        try:
            async with AsyncSessionLocal() as session:
                # Import models here to avoid circular imports
                from sqlalchemy import Table, MetaData, Column
                from sqlalchemy.dialects.postgresql import UUID, JSONB
                from sqlalchemy import String, Boolean, DateTime, Text
                
                # Define table structures
                metadata = MetaData()
                pipelines_table = Table(
                    'pipelines',
                    metadata,
                    Column('id', UUID(as_uuid=True), primary_key=True),
                    Column('user_id', UUID(as_uuid=True)),
                    Column('name', String(255)),
                    Column('is_active', Boolean),
                    Column('trigger_mode', String(50)),
                    Column('scanner_id', UUID(as_uuid=True)),
                    Column('signal_subscriptions', JSONB),
                    Column('scanner_tickers', JSONB),  # Fallback for backward compat
                )
                
                scanners_table = Table(
                    'scanners',
                    metadata,
                    Column('id', UUID(as_uuid=True), primary_key=True),
                    Column('config', JSONB),
                )
                
                # Query active signal-based pipelines with their scanners
                query = select(
                    pipelines_table.c.id,
                    pipelines_table.c.name,
                    pipelines_table.c.user_id,
                    pipelines_table.c.scanner_id,
                    pipelines_table.c.signal_subscriptions,
                    pipelines_table.c.scanner_tickers,
                    scanners_table.c.config.label('scanner_config')
                ).select_from(
                    pipelines_table.outerjoin(
                        scanners_table,
                        pipelines_table.c.scanner_id == scanners_table.c.id
                    )
                ).where(
                    and_(
                        pipelines_table.c.is_active == True,
                        cast(pipelines_table.c.trigger_mode, String) == 'signal'
                    )
                )
                
                result = await session.execute(query)
                pipelines = result.fetchall()
                
                # Build cache
                new_cache = {}
                for pipeline in pipelines:
                    # Get tickers from scanner or fallback to scanner_tickers
                    tickers = []
                    if pipeline.scanner_config:
                        # New way: Get tickers from scanner
                        tickers = pipeline.scanner_config.get('tickers', [])
                    elif pipeline.scanner_tickers:
                        # Old way: Use direct scanner_tickers (deprecated)
                        tickers = pipeline.scanner_tickers
                    
                    if tickers:  # Only cache pipelines with tickers
                        new_cache[str(pipeline.id)] = {
                            'name': pipeline.name,
                            'user_id': str(pipeline.user_id),
                            'tickers': set(tickers),
                            'signal_subscriptions': pipeline.signal_subscriptions or []
                        }
                
                self.pipeline_cache = new_cache
                self.last_cache_refresh = time.time()
                
                # Track cache size with delta (UpDownCounter accumulates)
                new_cache_size = len(new_cache)
                if self.meter:
                    delta = new_cache_size - self.last_cache_size
                    self.cache_size.add(delta)
                    self.last_cache_size = new_cache_size
                
                logger.info(
                    "pipeline_cache_refreshed",
                    pipelines_count=len(new_cache),
                    total_tickers=sum(len(p['tickers']) for p in new_cache.values())
                )
                
        except Exception as e:
            logger.error(
                "pipeline_cache_refresh_failed",
                error=str(e),
                exc_info=True
            )
    
    def match_signals_to_pipelines(self, signals: List[Signal]) -> Dict[str, List[str]]:
        """
        Match signals to pipelines using in-memory cache.
        
        Matches on:
        1. Ticker intersection (signal tickers ∩ pipeline tickers)
        2. Signal type subscription (if specified)
        3. Confidence threshold (if specified)
        
        Args:
            signals: List of signals to match
            
        Returns:
            Dict mapping pipeline_id to list of signal_ids that matched
        """
        matches: Dict[str, List[str]] = {}
        
        for signal in signals:
            signal_tickers = signal.get_ticker_symbols()
            
            if not signal_tickers:
                continue
            
            # Scan in-memory cache (fast!)
            for pipeline_id, pipeline_data in self.pipeline_cache.items():
                # Check 1: Ticker intersection
                matched_tickers = signal_tickers & pipeline_data['tickers']
                if not matched_tickers:
                    continue
                
                # Check 2: Signal type subscription (if specified)
                signal_subscriptions = pipeline_data.get('signal_subscriptions', [])
                if signal_subscriptions:
                    # Pipeline has specific signal subscriptions
                    # Check if this signal type is subscribed
                    subscribed = False
                    for subscription in signal_subscriptions:
                        if subscription.get('signal_type') == signal.signal_type:
                            # Check 3: Confidence threshold (if specified)
                            min_confidence = subscription.get('min_confidence')
                            if min_confidence is not None:
                                # For multi-ticker signals, check if any ticker meets threshold
                                # Get max confidence across matched tickers
                                max_confidence = 0
                                for ticker_signal in signal.tickers:
                                    if ticker_signal.ticker in matched_tickers:
                                        max_confidence = max(max_confidence, ticker_signal.confidence or 0)
                                
                                if max_confidence < min_confidence:
                                    logger.debug(
                                        "signal_filtered_by_confidence",
                                        signal_id=str(signal.signal_id),
                                        pipeline_id=pipeline_id,
                                        signal_confidence=max_confidence,
                                        required_confidence=min_confidence
                                    )
                                    continue  # Signal doesn't meet confidence threshold
                            
                            subscribed = True
                            break
                    
                    if not subscribed:
                        logger.debug(
                            "signal_filtered_by_subscription",
                            signal_id=str(signal.signal_id),
                            pipeline_id=pipeline_id,
                            signal_type=signal.signal_type,
                            subscriptions=[s.get('signal_type') for s in signal_subscriptions]
                        )
                        continue  # Pipeline not subscribed to this signal type
                
                # Match found!
                if pipeline_id not in matches:
                    matches[pipeline_id] = []
                matches[pipeline_id].append(str(signal.signal_id))
                
                logger.debug(
                    "signal_matched_to_pipeline",
                    signal_id=str(signal.signal_id),
                    pipeline_id=pipeline_id,
                    pipeline_name=pipeline_data['name'],
                    matched_tickers=list(matched_tickers),
                    signal_type=signal.signal_type
                )
        
        return matches
    
    async def check_running_pipelines(self, pipeline_ids: List[str]) -> Set[str]:
        """
        Check which pipelines are currently running.
        
        Args:
            pipeline_ids: List of pipeline IDs to check
            
        Returns:
            Set of pipeline IDs that are currently running
        """
        if not pipeline_ids:
            return set()
        
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import Table, MetaData, Column
                from sqlalchemy.dialects.postgresql import UUID
                from sqlalchemy import String
                
                metadata = MetaData()
                executions_table = Table(
                    'executions',
                    metadata,
                    Column('id', UUID(as_uuid=True), primary_key=True),
                    Column('pipeline_id', UUID(as_uuid=True)),
                    Column('status', String(50)),
                )
                
                # Convert string IDs to UUID
                from uuid import UUID as PyUUID
                pipeline_uuids = [PyUUID(pid) for pid in pipeline_ids]
                
                # Query for running executions
                query = select(executions_table.c.pipeline_id).where(
                    and_(
                        executions_table.c.pipeline_id.in_(pipeline_uuids),
                        cast(executions_table.c.status, String).in_(['PENDING', 'RUNNING'])
                    )
                )
                
                result = await session.execute(query)
                running = result.fetchall()
                
                return {str(row.pipeline_id) for row in running}
                
        except Exception as e:
            logger.error(
                "check_running_pipelines_failed",
                error=str(e),
                exc_info=True
            )
            return set()
    
    async def enqueue_pipeline_executions(
        self,
        pipeline_signal_map: Dict[str, List[str]],
        signals: List[Signal]  # Add signals parameter
    ):
        """
        Enqueue Celery tasks for matched pipelines.
        
        **IMPORTANT**: Enqueues ONE execution per (pipeline_id, ticker) pair.
        If a signal has multiple tickers for the same pipeline, we create
        separate executions for each ticker.
        
        Args:
            pipeline_signal_map: Dict mapping pipeline_id to list of signal_ids
            signals: List of Signal objects from the current batch
        """
        if not pipeline_signal_map:
            return
        
        # Check which pipelines are already running
        pipeline_ids = list(pipeline_signal_map.keys())
        running_ids = await self.check_running_pipelines(pipeline_ids)
        
        # Enqueue tasks for pipelines that aren't running
        enqueued_count = 0
        skipped_count = 0
        
        for pipeline_id, signal_ids in pipeline_signal_map.items():
            # Collect all unique tickers for this pipeline from the matched signals
            tickers_to_execute = set()
            signal_data_by_ticker = {}  # Store signal context per ticker
            
            logger.debug(
                "processing_pipeline_signals",
                pipeline_id=pipeline_id,
                signal_ids=signal_ids,
                signals_count=len(signals),
                signal_ids_in_batch=[str(s.signal_id) for s in signals[:5]]  # First 5
            )
            
            for signal_id in signal_ids:
                # Find the signal in the provided signals list (not self.signal_buffer which is now empty)
                for signal in signals:
                    if str(signal.signal_id) == signal_id:
                        # Extract tickers and their pipeline routing info
                        # Get pipeline routing from signal-level metadata (not ticker-level)
                        ticker_pipelines = signal.metadata.get('ticker_pipelines', {})
                        
                        logger.debug(
                            "checking_ticker_routing",
                            signal_id=str(signal.signal_id),
                            pipeline_id=pipeline_id,
                            ticker_pipelines_keys=list(ticker_pipelines.keys()) if ticker_pipelines else [],
                            has_routing_metadata=bool(ticker_pipelines)
                        )
                        
                        for ticker_signal in signal.tickers:
                            ticker = ticker_signal.get('ticker')
                            if not ticker:
                                continue
                            
                            # Check if this ticker is routed to this pipeline
                            # If routing metadata exists, verify this pipeline is listed for this ticker
                            if ticker_pipelines:
                                pipelines_for_ticker = ticker_pipelines.get(ticker, [])
                                logger.debug(
                                    "ticker_routing_check",
                                    ticker=ticker,
                                    pipeline_id=pipeline_id,
                                    pipelines_for_ticker=pipelines_for_ticker,
                                    num_pipelines=len(pipelines_for_ticker) if pipelines_for_ticker else 0
                                )
                                if pipelines_for_ticker:
                                    pipeline_match = any(
                                        p.get('pipeline_id') == pipeline_id 
                                        for p in pipelines_for_ticker
                                    )
                                    if not pipeline_match:
                                        logger.debug(
                                            "ticker_not_routed_to_pipeline",
                                            ticker=ticker,
                                            pipeline_id=pipeline_id,
                                            action="skipped"
                                        )
                                        continue  # This ticker not routed to this pipeline
                            
                        tickers_to_execute.add(ticker)
                        
                        # Store signal context for this ticker
                        # Transform to match SignalData schema expectations
                        if ticker not in signal_data_by_ticker:
                            signal_data_by_ticker[ticker] = {
                                'signal_id': str(signal.signal_id),
                                'signal_type': signal.signal_type,
                                'source': signal.source,
                                'timestamp': signal.timestamp.isoformat() if hasattr(signal.timestamp, 'isoformat') else signal.timestamp,
                                'tickers': [ticker],  # SignalData expects a list of ticker symbols
                                'confidence': ticker_signal.get('confidence', 50.0),  # Extract confidence from ticker_signal
                                'metadata': signal.metadata
                            }
                        break
            
            logger.debug(
                "tickers_collected_for_pipeline",
                pipeline_id=pipeline_id,
                tickers_to_execute=list(tickers_to_execute),
                num_tickers=len(tickers_to_execute)
            )
            
            # For each unique ticker, enqueue a separate execution
            for ticker in tickers_to_execute:
                # Check if pipeline with this ticker is already running
                # (More granular check could be added here if needed)
                if pipeline_id in running_ids:
                    skipped_count += 1
                    logger.debug(
                        "pipeline_already_running",
                        pipeline_id=pipeline_id,
                        ticker=ticker,
                        action="skipped"
                    )
                    continue
                
                try:
                    # Get user_id from pipeline cache
                    pipeline_data = self.pipeline_cache.get(pipeline_id, {})
                    user_id = pipeline_data.get('user_id')
                    
                    if not user_id:
                        logger.error(
                            "pipeline_missing_user_id",
                            pipeline_id=pipeline_id
                        )
                        continue
                    
                    # Get signal context for this ticker
                    signal_context = signal_data_by_ticker.get(ticker)
                    
                    # Enqueue Celery task with ticker-specific signal context
                    celery_app.send_task(
                        'app.orchestration.tasks.execute_pipeline',
                        kwargs={
                            'pipeline_id': pipeline_id,
                            'user_id': str(user_id),
                            'symbol': ticker,  # ✅ CRITICAL: Pass the ticker as symbol
                            'mode': 'paper',  # Signal-triggered pipelines use paper mode by default
                            'signal_context': signal_context  # Pass signal data to pipeline
                        }
                    )
                    
                    enqueued_count += 1
                    
                    logger.info(
                        "pipeline_execution_enqueued",
                        pipeline_id=pipeline_id,
                        pipeline_name=pipeline_data.get('name'),
                        user_id=str(user_id),
                        ticker=ticker,
                        signal_type=signal_context.get('signal_type') if signal_context else None,
                        mode='paper'
                    )
                    
                except Exception as e:
                    logger.error(
                        "pipeline_enqueue_failed",
                        pipeline_id=pipeline_id,
                        ticker=ticker,
                        error=str(e),
                        exc_info=True
                    )
        
        logger.info(
            "batch_enqueue_completed",
            enqueued=enqueued_count,
            skipped_running=skipped_count,
            total_matched=len(pipeline_signal_map)
        )
        
        # Track enqueue metrics
        if self.meter:
            self.pipelines_enqueued.add(enqueued_count)
            self.pipelines_skipped.add(skipped_count)
    
    async def process_signal_batch(self):
        """Process accumulated signals in batch."""
        if not self.signal_buffer:
            return
        
        batch_start = time.time()
        signals = self.signal_buffer
        self.signal_buffer = []
        
        # Track batch metrics
        if self.meter:
            self.signals_consumed.add(len(signals))
            self.batch_size_histogram.record(len(signals))
        
        logger.info(
            "processing_signal_batch",
            batch_size=len(signals),
            signal_ids=[str(s.signal_id) for s in signals]
        )
        
        # Step 1: Match signals to pipelines (in-memory, fast)
        pipeline_signal_map = self.match_signals_to_pipelines(signals)
        
        # Track matched pipelines
        if self.meter and pipeline_signal_map:
            self.pipelines_matched.add(len(pipeline_signal_map))
        
        if not pipeline_signal_map:
            logger.debug("no_pipelines_matched", signals_processed=len(signals))
            return
        
        # Step 2: Check running status + enqueue tasks
        await self.enqueue_pipeline_executions(pipeline_signal_map, signals)
        
        # Track batch processing duration
        if self.meter:
            batch_duration = time.time() - batch_start
            self.batch_processing_duration.record(batch_duration)
    
    async def consume_signals(self):
        """Main loop: consume signals from Kafka and process in batches."""
        logger.info("starting_kafka_consumer_loop")
        
        while self.running:
            try:
                # Check if cache needs refresh
                if time.time() - self.last_cache_refresh > settings.CACHE_REFRESH_INTERVAL_SECONDS:
                    await self.refresh_pipeline_cache()
                
                # Poll Kafka for messages
                msg_pack = self.kafka_consumer.poll(timeout_ms=100)
                
                for topic_partition, messages in msg_pack.items():
                    for message in messages:
                        try:
                            signal = Signal(message.value)
                            self.signal_buffer.append(signal)
                            
                            logger.debug(
                                "signal_received",
                                signal_id=str(signal.signal_id),
                                signal_type=signal.signal_type,
                                tickers=[t.get("ticker") for t in signal.tickers]
                            )
                            
                        except Exception as e:
                            logger.error(
                                "signal_deserialization_failed",
                                error=str(e),
                                message_value=message.value
                            )
                
                # Process batch if conditions met
                current_time = time.time()
                batch_ready = (
                    len(self.signal_buffer) >= settings.BATCH_SIZE or
                    (self.signal_buffer and 
                     current_time - self.last_batch_process >= settings.BATCH_TIMEOUT_SECONDS)
                )
                
                if batch_ready:
                    await self.process_signal_batch()
                    self.last_batch_process = current_time
                    
                    # Commit Kafka offsets after successful processing
                    try:
                        self.kafka_consumer.commit()
                    except Exception as e:
                        logger.error("kafka_commit_failed", error=str(e))
                
                # Small sleep to prevent busy-waiting
                await asyncio.sleep(0.01)
                
            except Exception as e:
                logger.error(
                    "consumer_loop_error",
                    error=str(e),
                    exc_info=True
                )
                await asyncio.sleep(1)  # Backoff on error
    
    async def run(self):
        """Start the trigger dispatcher service."""
        logger.info("trigger_dispatcher_starting")
        print("\n" + "="*80)
        print("🚀 Trigger Dispatcher Service Starting")
        print(f"   Kafka Topic: {settings.KAFKA_SIGNAL_TOPIC}")
        print(f"   Consumer Group: {settings.KAFKA_CONSUMER_GROUP}")
        print(f"   Batch Size: {settings.BATCH_SIZE}")
        print(f"   Batch Timeout: {settings.BATCH_TIMEOUT_SECONDS}s")
        print(f"   Cache Refresh: {settings.CACHE_REFRESH_INTERVAL_SECONDS}s")
        print("="*80 + "\n")
        
        self.running = True
        
        try:
            # Initialize Kafka consumer
            self._initialize_kafka_consumer()
            
            # Initial cache load
            await self.refresh_pipeline_cache()
            
            # Start consuming
            await self.consume_signals()
            
        except KeyboardInterrupt:
            logger.info("shutdown_signal_received")
        except Exception as e:
            logger.error("dispatcher_fatal_error", error=str(e), exc_info=True)
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown."""
        self.running = False
        
        logger.info("trigger_dispatcher_shutting_down")
        print("\n🛑 Trigger Dispatcher Shutting Down...\n")
        
        # Process any remaining signals
        if self.signal_buffer:
            logger.info("processing_remaining_signals", count=len(self.signal_buffer))
            await self.process_signal_batch()
        
        # Close Kafka consumer
        if self.kafka_consumer:
            try:
                self.kafka_consumer.commit()
                self.kafka_consumer.close()
                logger.info("kafka_consumer_closed")
            except Exception as e:
                logger.error("kafka_consumer_close_error", error=str(e))
        
        # Close database engine
        await engine.dispose()
        logger.info("database_engine_closed")


async def main():
    """Main entry point."""
    dispatcher = TriggerDispatcher()
    await dispatcher.run()


if __name__ == "__main__":
    asyncio.run(main())

