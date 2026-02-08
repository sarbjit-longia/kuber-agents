"""
Scanner Universe Manager

Queries the backend database to discover tickers from active pipelines' scanners.
Only includes tickers from scanners that are attached to active pipelines.
"""
from typing import List, Set, Dict
from datetime import datetime
import structlog
from sqlalchemy import create_engine, select, and_
from sqlalchemy.orm import sessionmaker

logger = structlog.get_logger()


class ScannerUniverseManager:
    """
    Manages the universe of tickers to monitor based on active pipelines and their scanners.
    
    Logic:
    1. Query backend DB for active pipelines
    2. For each active pipeline, get its scanner_id
    3. Load scanner config and extract tickers
    4. Return deduplicated list of all tickers
    """
    
    def __init__(self, backend_db_url: str):
        """
        Initialize the manager.
        
        Args:
            backend_db_url: Connection string to backend PostgreSQL database
        """
        self.backend_db_url = backend_db_url
        self.engine = None
        self.Session = None
        self.last_refresh = None
        self.current_tickers = set()
        
    def connect(self):
        """Establish connection to backend database."""
        try:
            self.engine = create_engine(self.backend_db_url, pool_pre_ping=True)
            self.Session = sessionmaker(bind=self.engine)
            logger.info("scanner_universe_manager_connected", db_url=self.backend_db_url.split('@')[-1])
        except Exception as e:
            logger.error("scanner_universe_manager_connection_failed", error=str(e))
            raise
    
    def _parse_scanner_config(self, scanner_config):
        """
        Parse scanner config from PostgreSQL JSONB.
        
        Args:
            scanner_config: JSONB value (could be dict or string)
            
        Returns:
            Parsed dict or None
        """
        # PostgreSQL JSONB might return as dict or string
        if isinstance(scanner_config, str):
            import json
            try:
                return json.loads(scanner_config)
            except json.JSONDecodeError:
                logger.warning("invalid_scanner_config_json", config=scanner_config)
                return None
        elif isinstance(scanner_config, dict):
            return scanner_config
        else:
            logger.warning("unexpected_scanner_config_type", type=type(scanner_config).__name__)
            return None
    
    def get_active_scanner_tickers(self) -> List[str]:
        """
        Get all tickers from scanners attached to active pipelines.
        
        Returns:
            List of unique ticker symbols
        """
        if not self.Session:
            self.connect()
        
        session = self.Session()
        try:
            from sqlalchemy import text
            
            # Query: Get all active pipelines with their scanners
            query = text("""
                SELECT DISTINCT s.config
                FROM pipelines p
                JOIN scanners s ON p.scanner_id = s.id
                WHERE p.is_active = true 
                  AND s.is_active = true
                  AND p.scanner_id IS NOT NULL
            """)
            
            result = session.execute(query)
            
            tickers = set()
            scanner_count = 0
            
            for row_number, row in enumerate(result, 1):
                scanner_config = row[0]  # JSONB config
                
                logger.debug(
                    "scanner_row_fetched",
                    row_number=row_number,
                    config_type=type(scanner_config).__name__,
                    config_value=str(scanner_config)[:200]  # Truncate for logging
                )
                
                # Parse scanner config
                parsed_config = self._parse_scanner_config(scanner_config)
                if parsed_config:
                    scanner_tickers = parsed_config.get('tickers', [])
                    if scanner_tickers:
                        tickers.update(scanner_tickers)
                        scanner_count += 1
                        logger.debug(
                            "scanner_tickers_extracted",
                            scanner_count=scanner_count,
                            ticker_count=len(scanner_tickers),
                            tickers=scanner_tickers
                        )
            
            logger.info(
                "scanner_query_completed",
                rows_fetched=row_number if 'row_number' in locals() else 0,
                scanners_processed=scanner_count
            )
            
            ticker_list = sorted(list(tickers))
            
            self.current_tickers = set(ticker_list)
            self.last_refresh = datetime.utcnow()
            
            logger.info(
                "scanner_universe_refreshed",
                ticker_count=len(ticker_list),
                scanner_count=scanner_count,
                tickers=ticker_list
            )
            
            return ticker_list
        
        except Exception as e:
            logger.error("scanner_universe_refresh_failed", error=str(e), exc_info=True)
            # Return previously known tickers on error
            return sorted(list(self.current_tickers))
        
        finally:
            session.close()
    
    def get_pipeline_scanner_mapping(self) -> Dict[str, Dict]:
        """
        Get mapping of pipeline_id -> scanner info for signal routing.
        
        Returns:
            Dict mapping pipeline_id to {scanner_id, scanner_name, tickers}
        """
        if not self.Session:
            self.connect()
        
        session = self.Session()
        try:
            from sqlalchemy import text
            
            query = text("""
                SELECT 
                    p.id::text as pipeline_id,
                    p.name as pipeline_name,
                    s.id::text as scanner_id,
                    s.name as scanner_name,
                    s.config as scanner_config
                FROM pipelines p
                JOIN scanners s ON p.scanner_id = s.id
                WHERE p.is_active = true 
                  AND s.is_active = true
                  AND p.scanner_id IS NOT NULL
            """)
            
            result = session.execute(query)
            
            mapping = {}
            
            for row in result:
                pipeline_id = row[0]
                pipeline_name = row[1]
                scanner_id = row[2]
                scanner_name = row[3]
                scanner_config = row[4]
                
                # Parse scanner config
                parsed_config = self._parse_scanner_config(scanner_config)
                tickers = parsed_config.get('tickers', []) if parsed_config else []
                
                mapping[pipeline_id] = {
                    "pipeline_name": pipeline_name,
                    "scanner_id": scanner_id,
                    "scanner_name": scanner_name,
                    "tickers": tickers
                }
            
            logger.info(
                "pipeline_scanner_mapping_loaded",
                pipeline_count=len(mapping)
            )
            
            return mapping
        
        except Exception as e:
            logger.error("pipeline_scanner_mapping_failed", error=str(e), exc_info=True)
            return {}
        
        finally:
            session.close()
