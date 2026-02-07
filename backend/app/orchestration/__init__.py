"""
Pipeline Orchestration Package

This package contains the pipeline execution engine, including:
- Pipeline executor service
- Celery task definitions
- Execution state management
"""

from app.orchestration.executor import PipelineExecutor

__all__ = ["PipelineExecutor"]
