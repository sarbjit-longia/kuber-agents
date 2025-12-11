"""OHLCV model for TimescaleDB"""
from sqlalchemy import Column, String, Float, BigInteger, DateTime, Index
from app.database import Base
from datetime import datetime


class OHLCV(Base):
    """OHLCV candlestick data stored in TimescaleDB hypertable"""
    __tablename__ = "ohlcv"
    
    ticker = Column(String(10), primary_key=True, nullable=False)
    timeframe = Column(String(5), primary_key=True, nullable=False)  # 1m, 5m, 1h, 1d
    timestamp = Column(DateTime, primary_key=True, nullable=False)
    
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=False)
    
    __table_args__ = (
        Index("ix_ohlcv_ticker_timeframe_timestamp", "ticker", "timeframe", "timestamp"),
    )
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "ticker": self.ticker,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }

