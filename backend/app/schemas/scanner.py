"""
Scanner Pydantic Schemas

Schemas for scanner creation, updates, and responses.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, validator

from app.models.scanner import ScannerType


class SignalSubscription(BaseModel):
    """Signal subscription configuration for pipelines."""
    signal_type: str = Field(..., description="Type of signal to subscribe to")
    min_confidence: Optional[float] = Field(None, ge=0, le=100, description="Minimum confidence threshold (0-100)")


class ScannerBase(BaseModel):
    """Base scanner schema with common fields."""
    name: str = Field(..., min_length=1, max_length=100, description="Scanner name")
    description: Optional[str] = Field(None, description="Scanner description")
    scanner_type: ScannerType = Field(ScannerType.MANUAL, description="Type of scanner")
    config: Dict[str, Any] = Field(default_factory=dict, description="Scanner configuration")
    is_active: bool = Field(True, description="Whether scanner is active")
    refresh_interval: Optional[int] = Field(None, gt=0, description="Refresh interval in minutes")


class ScannerCreate(ScannerBase):
    """Schema for creating a new scanner."""
    
    @validator('config')
    def validate_manual_config(cls, v, values):
        """Validate manual scanner config has tickers."""
        if values.get('scanner_type') == ScannerType.MANUAL:
            tickers = v.get('tickers', [])
            if not tickers or not isinstance(tickers, list):
                raise ValueError("Manual scanner must have a non-empty 'tickers' list in config")
            
            # Normalize tickers (uppercase, strip whitespace)
            normalized = [t.strip().upper() for t in tickers if isinstance(t, str) and t.strip()]
            if not normalized:
                raise ValueError("Manual scanner must have at least one valid ticker")
            
            # Remove duplicates while preserving order
            seen = set()
            unique_tickers = []
            for ticker in normalized:
                if ticker not in seen:
                    seen.add(ticker)
                    unique_tickers.append(ticker)
            
            v['tickers'] = unique_tickers
        
        return v


class ScannerUpdate(BaseModel):
    """Schema for updating a scanner."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    refresh_interval: Optional[int] = Field(None, gt=0)
    
    @validator('config')
    def validate_config(cls, v):
        """Validate manual scanner config."""
        if v is not None and 'tickers' in v:
            tickers = v.get('tickers', [])
            if not isinstance(tickers, list):
                raise ValueError("'tickers' must be a list")
            
            # Normalize
            normalized = [t.strip().upper() for t in tickers if isinstance(t, str) and t.strip()]
            if not normalized:
                raise ValueError("At least one valid ticker is required")
            
            # Remove duplicates
            seen = set()
            unique_tickers = []
            for ticker in normalized:
                if ticker not in seen:
                    seen.add(ticker)
                    unique_tickers.append(ticker)
            
            v['tickers'] = unique_tickers
        
        return v


class ScannerInDB(ScannerBase):
    """Scanner schema as stored in database."""
    id: UUID
    user_id: UUID
    last_refreshed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ScannerResponse(ScannerInDB):
    """Scanner response with computed fields."""
    ticker_count: int = Field(0, description="Number of tickers in scanner")
    pipeline_count: Optional[int] = Field(0, description="Number of pipelines using this scanner")
    
    @staticmethod
    def from_db_model(scanner: Any, pipeline_count: int = 0) -> "ScannerResponse":
        """
        Create response from database model.
        
        Args:
            scanner: Scanner database model
            pipeline_count: Number of pipelines using this scanner
            
        Returns:
            ScannerResponse instance
        """
        return ScannerResponse(
            id=scanner.id,
            user_id=scanner.user_id,
            name=scanner.name,
            description=scanner.description,
            scanner_type=scanner.scanner_type,
            config=scanner.config,
            is_active=scanner.is_active,
            refresh_interval=scanner.refresh_interval,
            last_refreshed_at=scanner.last_refreshed_at,
            created_at=scanner.created_at,
            updated_at=scanner.updated_at,
            ticker_count=scanner.ticker_count,
            pipeline_count=pipeline_count
        )


class ScannerTickersResponse(BaseModel):
    """Response for scanner ticker list."""
    scanner_id: UUID
    scanner_name: str
    tickers: List[str] = Field(default_factory=list)
    ticker_count: int
    last_refreshed_at: Optional[datetime] = None

