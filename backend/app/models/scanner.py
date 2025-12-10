"""
Scanner Model

Scanners are reusable ticker lists that pipelines use to determine which stocks to monitor.
"""
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy import Column, String, Boolean, Integer, DateTime, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey
import enum

from app.database import Base


class ScannerType(str, enum.Enum):
    """Type of scanner implementation."""
    MANUAL = "manual"  # User manually enters tickers
    FILTER = "filter"  # Filter-based scanner (Phase 2)
    API = "api"  # External API integration (Phase 3)


class Scanner(Base):
    """
    Scanner model for ticker list management.
    
    A Scanner generates a list of ticker symbols that pipelines can monitor.
    Phase 1: Manual ticker entry only.
    Future: Filter-based, API-based scanners.
    """
    __tablename__ = "scanners"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # Basic info
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # Scanner configuration
    scanner_type = Column(
        SQLEnum(
            ScannerType, 
            name="scannertype", 
            create_type=False,
            values_callable=lambda x: [e.value for e in x]
        ),
        default=ScannerType.MANUAL,
        nullable=False
    )
    config = Column(JSONB, nullable=False, default=dict)
    # Example config for manual:
    # {
    #   "tickers": ["AAPL", "MSFT", "GOOGL"]
    # }
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Refresh configuration (for future use)
    refresh_interval = Column(Integer, nullable=True)  # minutes
    last_refreshed_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    # user = relationship("User", back_populates="scanners")
    # pipelines = relationship("Pipeline", back_populates="scanner")
    
    def __repr__(self):
        return f"<Scanner(id={self.id}, name={self.name}, type={self.scanner_type})>"
    
    @property
    def ticker_count(self) -> int:
        """Get the number of tickers in this scanner."""
        if self.scanner_type == ScannerType.MANUAL:
            return len(self.config.get("tickers", []))
        return 0  # For other types, will be computed differently
    
    def get_tickers(self) -> List[str]:
        """
        Get the list of tickers from this scanner.
        
        Returns:
            List of ticker symbols (uppercase)
        """
        if self.scanner_type == ScannerType.MANUAL:
            return self.config.get("tickers", [])
        # For other scanner types, this will be implemented in Phase 2/3
        return []
    
    def set_tickers(self, tickers: List[str]):
        """
        Set tickers for manual scanner.
        
        Args:
            tickers: List of ticker symbols
        """
        if self.scanner_type == ScannerType.MANUAL:
            # Normalize tickers (uppercase, strip whitespace)
            normalized_tickers = [t.strip().upper() for t in tickers if t.strip()]
            self.config["tickers"] = normalized_tickers
            self.last_refreshed_at = datetime.utcnow()

