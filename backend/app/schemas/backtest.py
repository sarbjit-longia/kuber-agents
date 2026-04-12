"""
Schemas for parity backtesting APIs.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.backtest_run import BacktestRunStatus
from app.models.execution import ExecutionStatus


class BacktestCreate(BaseModel):
    pipeline_id: UUID
    symbols: List[str] = Field(default_factory=list, min_length=1)
    start_date: date
    end_date: date
    timeframe: str = "5m"
    initial_capital: float = 10_000.0
    slippage_model: str = "fixed"
    slippage_value: float = 0.01
    commission_model: str = "per_share"
    commission_value: float = 0.005
    max_cost_usd: Optional[float] = None


class BacktestProgress(BaseModel):
    current_symbol: Optional[str] = None
    current_bar: int = 0
    total_bars: int = 0
    percent_complete: float = 0.0
    current_ts: Optional[str] = None


class BacktestRunSummary(BaseModel):
    id: UUID
    pipeline_id: Optional[UUID] = None
    pipeline_name: Optional[str] = None
    status: BacktestRunStatus
    config: Dict[str, Any]
    progress: Dict[str, Any]
    metrics: Optional[Dict[str, Any]] = None
    trades_count: int
    estimated_cost: Optional[float] = None
    actual_cost: float
    failure_reason: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BacktestRunList(BaseModel):
    backtests: List[BacktestRunSummary]
    total: int


class BacktestRunResult(BacktestRunSummary):
    equity_curve: List[float] = Field(default_factory=list)
    trades: List[Dict[str, Any]] = Field(default_factory=list)


class BacktestStartResponse(BaseModel):
    run_id: UUID
    status: BacktestRunStatus


class BacktestExecutionSummary(BaseModel):
    id: UUID
    pipeline_id: UUID
    status: ExecutionStatus
    mode: str
    symbol: Optional[str] = None
    cost: float
    error_message: Optional[str] = None
    execution_phase: Optional[str] = None
    result: Dict[str, Any] = Field(default_factory=dict)
    logs: List[Dict[str, Any]] = Field(default_factory=list)
    agent_states: List[Dict[str, Any]] = Field(default_factory=list)
    reports: Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BacktestExecutionList(BaseModel):
    executions: List[BacktestExecutionSummary]
    total: int


class BacktestTimelineEvent(BaseModel):
    id: str
    ts: str
    level: str = "info"
    type: str
    title: str
    message: str
    symbol: Optional[str] = None
    execution_id: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class BacktestTimelineResponse(BaseModel):
    events: List[BacktestTimelineEvent]


class BacktestReportResponse(BaseModel):
    generated_at: str
    summary: Dict[str, Any]
    sections: List[Dict[str, Any]]
    llm_analysis: Optional[Dict[str, Any]] = None
