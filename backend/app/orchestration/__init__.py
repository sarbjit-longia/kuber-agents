"""
Pipeline Orchestration Package

This package contains the pipeline execution engine, including:
- Pipeline executor service
- Celery task definitions
- Execution state management
"""

__all__ = ["PipelineExecutor"]


def __getattr__(name):
    if name == "PipelineExecutor":
        from app.orchestration.executor import PipelineExecutor

        return PipelineExecutor
    raise AttributeError(name)
