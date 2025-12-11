"""Universe Manager - Tracks which tickers need data fetching"""
import structlog
from typing import Set, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis
from opentelemetry import metrics

logger = structlog.get_logger()


class UniverseManager:
    """Manages the universe of tickers across all users"""
    
    def __init__(self, backend_db: AsyncSession, redis: aioredis.Redis, meter: Optional[metrics.Meter] = None):
        self.backend_db = backend_db
        self.redis = redis
        self.meter = meter
        
        # Metrics (optional)
        if meter:
            self.refresh_counter = meter.create_counter(
                name="universe_refresh_total",
                description="Total universe refreshes"
            )
        else:
            self.refresh_counter = None
    
    async def refresh_universe(self) -> Dict[str, list]:
        """
        Query backend DB for all tickers in active scanners.
        Categorize into hot/warm tiers.
        """
        logger.info("refreshing_universe")
        
        try:
            # Query 1: Hot tickers (in currently running executions)
            hot_tickers = await self._get_hot_tickers()
            
            # Query 2: Warm tickers (in active pipelines/scanners)
            warm_tickers = await self._get_warm_tickers()
            
            # Remove hot tickers from warm (no duplicates)
            warm_tickers = warm_tickers - hot_tickers
            
            # Update Redis sets
            pipe = self.redis.pipeline()
            pipe.delete("tickers:hot")
            pipe.delete("tickers:warm")
            
            if hot_tickers:
                pipe.sadd("tickers:hot", *hot_tickers)
            if warm_tickers:
                pipe.sadd("tickers:warm", *warm_tickers)
            
            await pipe.execute()
            
            # Store sizes in Redis for metrics
            await self.redis.set("metrics:universe:hot", len(hot_tickers))
            await self.redis.set("metrics:universe:warm", len(warm_tickers))
            await self.redis.set("metrics:universe:total", len(hot_tickers) + len(warm_tickers))
            
            # Increment counter (if metrics enabled)
            if self.refresh_counter:
                self.refresh_counter.add(1)
            
            logger.info(
                "universe_refreshed",
                hot=len(hot_tickers),
                warm=len(warm_tickers),
                total=len(hot_tickers) + len(warm_tickers)
            )
            
            return {
                "hot": sorted(list(hot_tickers)),
                "warm": sorted(list(warm_tickers))
            }
            
        except Exception as e:
            logger.error("universe_refresh_failed", error=str(e))
            raise
    
    async def _get_hot_tickers(self) -> Set[str]:
        """Get tickers from currently running executions"""
        try:
            query = text("""
                SELECT DISTINCT jsonb_array_elements_text(s.config->'tickers') as ticker
                FROM executions e
                JOIN pipelines p ON e.pipeline_id = p.id
                LEFT JOIN scanners s ON p.scanner_id = s.id
                WHERE e.status IN ('PENDING', 'RUNNING')
                  AND s.config IS NOT NULL
                  AND s.config->'tickers' IS NOT NULL
            """)
            
            result = await self.backend_db.execute(query)
            tickers = {row[0] for row in result.fetchall() if row[0]}
            
            logger.debug("hot_tickers_found", count=len(tickers))
            return tickers
            
        except Exception as e:
            logger.error("hot_tickers_query_failed", error=str(e))
            return set()
    
    async def _get_warm_tickers(self) -> Set[str]:
        """Get tickers from active pipelines"""
        try:
            query = text("""
                SELECT DISTINCT jsonb_array_elements_text(s.config->'tickers') as ticker
                FROM pipelines p
                LEFT JOIN scanners s ON p.scanner_id = s.id
                WHERE p.is_active = true
                  AND s.config IS NOT NULL
                  AND s.config->'tickers' IS NOT NULL
            """)
            
            result = await self.backend_db.execute(query)
            tickers = {row[0] for row in result.fetchall() if row[0]}
            
            logger.debug("warm_tickers_found", count=len(tickers))
            return tickers
            
        except Exception as e:
            logger.error("warm_tickers_query_failed", error=str(e))
            return set()

