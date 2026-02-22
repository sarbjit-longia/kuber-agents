"""TimescaleDB Writer - Hypertable, continuous aggregates, and OHLCV persistence

Architecture:
  1. Raw 1m candles are written to the `ohlcv` hypertable
  2. TimescaleDB continuous aggregates automatically derive 5m/15m/1h/4h/D
  3. Celery reads from continuous aggregates → caches in Redis
  4. EOD candles from Tiingo are also persisted to `ohlcv` with timeframe='D'
  5. All aggregation happens inside the database — zero Python compute
"""
import structlog
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text

from app.database import timescale_engine, TimescaleSessionLocal

logger = structlog.get_logger()

# Continuous aggregate definitions
# Each entry: view_name, time_bucket interval, refresh policy params
CONTINUOUS_AGGREGATES = {
    "5m": {
        "view": "ohlcv_5m",
        "bucket": "5 minutes",
        "refresh_schedule": "1 minute",
        "refresh_start": "2 hours",
        "refresh_end": "1 minute",
    },
    "15m": {
        "view": "ohlcv_15m",
        "bucket": "15 minutes",
        "refresh_schedule": "5 minutes",
        "refresh_start": "4 hours",
        "refresh_end": "1 minute",
    },
    "1h": {
        "view": "ohlcv_1h",
        "bucket": "1 hour",
        "refresh_schedule": "10 minutes",
        "refresh_start": "12 hours",
        "refresh_end": "1 minute",
    },
    "4h": {
        "view": "ohlcv_4h",
        "bucket": "4 hours",
        "refresh_schedule": "30 minutes",
        "refresh_start": "2 days",
        "refresh_end": "1 minute",
    },
    "D": {
        "view": "ohlcv_daily",
        "bucket": "1 day",
        "refresh_schedule": "1 hour",
        "refresh_start": "7 days",
        "refresh_end": "1 minute",
    },
}

# Map timeframe strings to their view name (for read queries)
TIMEFRAME_TO_VIEW = {tf: cfg["view"] for tf, cfg in CONTINUOUS_AGGREGATES.items()}


async def init_hypertable():
    """
    Create the ohlcv hypertable and continuous aggregates.

    All operations are idempotent — safe to call on every startup.
    """
    async with timescale_engine.begin() as conn:
        # ---- 1. Base hypertable ----
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ohlcv (
                ticker    VARCHAR(10)      NOT NULL,
                timeframe VARCHAR(5)       NOT NULL,
                timestamp TIMESTAMPTZ      NOT NULL,
                open      DOUBLE PRECISION NOT NULL,
                high      DOUBLE PRECISION NOT NULL,
                low       DOUBLE PRECISION NOT NULL,
                close     DOUBLE PRECISION NOT NULL,
                volume    BIGINT           NOT NULL,
                PRIMARY KEY (ticker, timeframe, timestamp)
            )
        """))

        await conn.execute(text("""
            SELECT create_hypertable(
                'ohlcv', 'timestamp',
                if_not_exists => TRUE,
                migrate_data  => TRUE
            )
        """))

        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ohlcv_ticker_tf_ts
            ON ohlcv (ticker, timeframe, timestamp DESC)
        """))

        logger.info("ohlcv_hypertable_initialized")

        # ---- 2. Compression (best-effort) ----
        try:
            await conn.execute(text("""
                ALTER TABLE ohlcv SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'ticker,timeframe'
                )
            """))
            await conn.execute(text("""
                SELECT add_compression_policy(
                    'ohlcv', INTERVAL '7 days', if_not_exists => TRUE
                )
            """))
        except Exception as e:
            logger.warning("ohlcv_compression_setup_skipped", error=str(e))

        # ---- 3. Continuous aggregates ----
        for tf, cfg in CONTINUOUS_AGGREGATES.items():
            view = cfg["view"]
            bucket = cfg["bucket"]
            try:
                # Check if the view already exists
                result = await conn.execute(text(
                    "SELECT 1 FROM timescaledb_information.continuous_aggregates "
                    "WHERE view_name = :view"
                ), {"view": view})
                exists = result.fetchone() is not None

                if not exists:
                    # CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)
                    # Note: CREATE OR REPLACE is not supported for continuous aggregates
                    await conn.execute(text(f"""
                        CREATE MATERIALIZED VIEW {view}
                        WITH (timescaledb.continuous) AS
                        SELECT
                            ticker,
                            time_bucket('{bucket}', timestamp) AS bucket,
                            first(open, timestamp)  AS open,
                            max(high)               AS high,
                            min(low)                AS low,
                            last(close, timestamp)  AS close,
                            sum(volume)             AS volume
                        FROM ohlcv
                        WHERE timeframe = '1m'
                        GROUP BY ticker, bucket
                        WITH NO DATA
                    """))
                    logger.info("continuous_aggregate_created", view=view, bucket=bucket)

                # Add refresh policy (idempotent via if_not_exists)
                await conn.execute(text(f"""
                    SELECT add_continuous_aggregate_policy(
                        '{view}',
                        start_offset  => INTERVAL '{cfg["refresh_start"]}',
                        end_offset    => INTERVAL '{cfg["refresh_end"]}',
                        schedule_interval => INTERVAL '{cfg["refresh_schedule"]}',
                        if_not_exists => TRUE
                    )
                """))

            except Exception as e:
                logger.warning(
                    "continuous_aggregate_setup_failed",
                    view=view,
                    error=str(e),
                )

        logger.info("ohlcv_hypertable_ready")


async def write_candles(
    candles: List[Dict],
    ticker: str,
    timeframe: str = "1m",
) -> int:
    """
    Bulk upsert OHLCV candles into TimescaleDB.

    Uses INSERT ... ON CONFLICT DO NOTHING to avoid overwriting existing rows.

    Args:
        candles: List of candle dicts (keys: time, open, high, low, close, volume)
        ticker: Symbol (e.g. "AAPL")
        timeframe: Timeframe string (default "1m")

    Returns:
        Number of rows inserted.
    """
    if not candles:
        return 0

    async with TimescaleSessionLocal() as session:
        async with session.begin():
            stmt = text("""
                INSERT INTO ohlcv
                    (ticker, timeframe, timestamp, open, high, low, close, volume)
                VALUES
                    (:ticker, :timeframe, :timestamp, :open, :high, :low, :close, :volume)
                ON CONFLICT (ticker, timeframe, timestamp) DO NOTHING
            """)

            rows = []
            for c in candles:
                ts = c.get("time", "")
                if not ts:
                    continue
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
                rows.append({
                    "ticker": ticker,
                    "timeframe": timeframe,
                    "timestamp": dt,
                    "open": float(c.get("open", 0)),
                    "high": float(c.get("high", 0)),
                    "low": float(c.get("low", 0)),
                    "close": float(c.get("close", 0)),
                    "volume": int(c.get("volume", 0)),
                })

            if rows:
                await session.execute(stmt, rows)

            # Track TimescaleDB write metrics
            if rows:
                try:
                    from app.telemetry import timescale_candles_written_total
                    timescale_candles_written_total.labels(timeframe=timeframe).inc(len(rows))
                except Exception:
                    pass  # Telemetry not initialized (e.g., during tests)

            logger.debug(
                "candles_written_to_timescale",
                ticker=ticker,
                timeframe=timeframe,
                count=len(rows),
            )
            return len(rows)


async def refresh_aggregates():
    """
    Manually refresh all continuous aggregates for the recent time window.

    Called by the prefetch Celery task after writing new 1m candles to
    ensure the aggregated views are up-to-date before reading.
    """
    import time as _time
    start = _time.time()

    async with timescale_engine.begin() as conn:
        for tf, cfg in CONTINUOUS_AGGREGATES.items():
            view = cfg["view"]
            try:
                await conn.execute(text(f"""
                    CALL refresh_continuous_aggregate(
                        '{view}',
                        NOW() - INTERVAL '{cfg["refresh_start"]}',
                        NOW()
                    )
                """))
            except Exception as e:
                logger.warning(
                    "continuous_aggregate_refresh_failed",
                    view=view,
                    error=str(e),
                )

    duration = _time.time() - start
    try:
        from app.telemetry import timescale_aggregate_refresh_seconds
        timescale_aggregate_refresh_seconds.observe(duration)
    except Exception:
        pass

    logger.debug("continuous_aggregates_refreshed", duration_seconds=round(duration, 2))


async def read_aggregated_candles(
    ticker: str,
    timeframe: str,
    limit: int = 200,
) -> Optional[List[Dict]]:
    """
    Read pre-aggregated candles from a TimescaleDB continuous aggregate.

    For daily ('D') timeframe this merges two sources:
      - ``ohlcv_daily`` continuous aggregate (current forming day from 1m data)
      - Seeded EOD rows in ``ohlcv`` with ``timeframe = 'D'`` (historical)
    The aggregate takes priority for overlapping dates.

    Args:
        ticker: Symbol (e.g. "AAPL")
        timeframe: One of 5m, 15m, 1h, 4h, D
        limit: Max candles to return

    Returns:
        List of candle dicts, or None if timeframe has no continuous aggregate.
    """
    view = TIMEFRAME_TO_VIEW.get(timeframe)
    if view is None:
        return None

    async with TimescaleSessionLocal() as session:
        if timeframe == "D":
            # Merge continuous aggregate (forming days from 1m) with seeded EOD history.
            # Prefer aggregate rows when dates overlap (more up-to-date intraday data).
            result = await session.execute(
                text(f"""
                    WITH daily_agg AS (
                        SELECT bucket::date AS day,
                               open, high, low, close, volume
                        FROM {view}
                        WHERE ticker = :ticker
                    ),
                    daily_seeded AS (
                        SELECT timestamp::date AS day,
                               open, high, low, close, volume
                        FROM ohlcv
                        WHERE ticker = :ticker
                          AND timeframe = 'D'
                          AND timestamp::date NOT IN (SELECT day FROM daily_agg)
                    )
                    SELECT day, open, high, low, close, volume
                    FROM (
                        SELECT * FROM daily_agg
                        UNION ALL
                        SELECT * FROM daily_seeded
                    ) combined
                    ORDER BY day DESC
                    LIMIT :limit
                """),
                {"ticker": ticker, "limit": limit},
            )
        else:
            result = await session.execute(
                text(f"""
                    SELECT bucket, open, high, low, close, volume
                    FROM {view}
                    WHERE ticker = :ticker
                    ORDER BY bucket DESC
                    LIMIT :limit
                """),
                {"ticker": ticker, "limit": limit},
            )

        rows = result.fetchall()

    if not rows:
        return None

    # Track aggregate read metrics
    try:
        from app.telemetry import timescale_aggregates_read_total
        timescale_aggregates_read_total.labels(timeframe=timeframe).inc(len(rows))
    except Exception:
        pass

    # Convert to standard candle dict format, oldest first.
    # Column name is 'day' for daily, 'bucket' for others.
    time_col = "day" if timeframe == "D" else "bucket"
    candles = [
        {
            "time": getattr(row, time_col).isoformat(),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": int(row.volume),
        }
        for row in reversed(rows)
    ]

    logger.debug(
        "aggregated_candles_read",
        ticker=ticker,
        timeframe=timeframe,
        count=len(candles),
    )
    return candles
