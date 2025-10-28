"""
Pipeline Orchestration Package

This package contains the pipeline execution engine, including:
- Pipeline executor service
- CrewAI Flow integration
- Celery task definitions
- Execution state management
"""

from app.orchestration.executor import PipelineExecutor
from app.orchestration.flow import TradingPipelineFlow

__all__ = ["PipelineExecutor", "TradingPipelineFlow"]
