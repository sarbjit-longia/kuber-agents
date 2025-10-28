"""
Cost Tracking Model

Tracks API costs, LLM token usage, and agent execution costs.
"""
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class CostTracking(Base):
    """
    Tracks costs for pipeline executions, LLM API calls, and agent usage.
    
    This enables:
    - Budget monitoring per user
    - Agent cost analysis
    - LLM usage tracking
    - Cost optimization insights
    """
    __tablename__ = "cost_tracking"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Relations
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    pipeline_id = Column(UUID(as_uuid=True), ForeignKey("pipelines.id"), nullable=True, index=True)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("executions.id"), nullable=True, index=True)
    
    # Cost details
    agent_type = Column(String(100), nullable=False, index=True)  # Which agent incurred the cost
    agent_id = Column(String(255), nullable=True)  # Specific agent instance ID
    
    # Token usage (for LLM agents)
    tokens_input = Column(Integer, default=0)
    tokens_output = Column(Integer, default=0)
    tokens_total = Column(Integer, default=0)
    
    # Cost breakdown
    cost_amount = Column(Float, nullable=False, default=0.0)  # USD
    cost_type = Column(String(50), nullable=False)  # "llm_api", "data_api", "compute", "storage"
    
    # API details
    api_provider = Column(String(100), nullable=True)  # "openai", "finnhub", "alpaca", etc.
    api_model = Column(String(100), nullable=True)  # "gpt-4o", "gpt-3.5-turbo", etc.
    api_endpoint = Column(String(255), nullable=True)
    
    # Additional context
    extra_metadata = Column(JSONB, nullable=True)  # Flexible field for additional data
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("User", back_populates="cost_tracking")
    pipeline = relationship("Pipeline", back_populates="cost_tracking")
    execution = relationship("Execution", back_populates="cost_tracking")
    
    def __repr__(self):
        return f"<CostTracking(id={self.id}, agent={self.agent_type}, cost=${self.cost_amount:.4f})>"


class UserBudget(Base):
    """
    User budget limits and tracking.
    
    Enables:
    - Daily/monthly spending limits
    - Budget alerts
    - Auto-pause on budget exceeded
    """
    __tablename__ = "user_budgets"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    
    # Budget limits (USD)
    daily_limit = Column(Float, nullable=True)  # None = no limit
    monthly_limit = Column(Float, nullable=True)  # None = no limit
    
    # Current spending (resets daily/monthly)
    daily_spent = Column(Float, default=0.0)
    monthly_spent = Column(Float, default=0.0)
    
    # Last reset timestamps
    daily_reset_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    monthly_reset_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Alert settings
    alert_threshold_percent = Column(Integer, default=80)  # Alert at 80% of limit
    alert_sent_daily = Column(DateTime, nullable=True)
    alert_sent_monthly = Column(DateTime, nullable=True)
    
    # Actions on budget exceeded
    pause_pipelines_on_exceeded = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="budget")
    
    def __repr__(self):
        return f"<UserBudget(user_id={self.user_id}, daily=${self.daily_spent:.2f}/${self.daily_limit or 'unlimited'})>"
    
    def check_budget_exceeded(self) -> tuple[bool, str]:
        """
        Check if user has exceeded their budget.
        
        Returns:
            (exceeded: bool, reason: str)
        """
        if self.daily_limit and self.daily_spent >= self.daily_limit:
            return True, f"Daily budget exceeded: ${self.daily_spent:.2f} >= ${self.daily_limit:.2f}"
        
        if self.monthly_limit and self.monthly_spent >= self.monthly_limit:
            return True, f"Monthly budget exceeded: ${self.monthly_spent:.2f} >= ${self.monthly_limit:.2f}"
        
        return False, ""
    
    def should_send_alert(self) -> tuple[bool, str]:
        """
        Check if budget alert should be sent.
        
        Returns:
            (should_alert: bool, reason: str)
        """
        threshold = self.alert_threshold_percent / 100.0
        
        # Check daily
        if self.daily_limit:
            daily_percent = self.daily_spent / self.daily_limit
            if daily_percent >= threshold and self.alert_sent_daily is None:
                return True, f"Daily budget at {daily_percent*100:.0f}%"
        
        # Check monthly
        if self.monthly_limit:
            monthly_percent = self.monthly_spent / self.monthly_limit
            if monthly_percent >= threshold and self.alert_sent_monthly is None:
                return True, f"Monthly budget at {monthly_percent*100:.0f}%"
        
        return False, ""

