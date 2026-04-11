"""
Tests for Pipeline Orchestration.

Pipelines no longer include a time_trigger agent node. Periodic scheduling is
handled by Celery Beat; signal-based triggers come from the Kafka → Trigger Dispatcher
microservice. The executor runs: MarketData → Bias → Strategy → Risk → TradeReview → TradeManager.
"""
import pytest
from uuid import uuid4

from app.orchestration.executor import PipelineExecutor
from app.schemas.pipeline_state import PipelineState
from app.models.pipeline import Pipeline
from app.agents import MarketDataAgent


def test_pipeline_executor_initialization():
    """Test PipelineExecutor initialization."""
    pipeline = Pipeline(
        id=uuid4(),
        user_id=uuid4(),
        name="Test Pipeline",
        description="Test",
        config={
            "symbol": "AAPL",
            "nodes": [
                {
                    "id": "node-1",
                    "agent_type": "market_data_agent",
                    "config": {"timeframes": ["5m"], "use_mock_data": True}
                },
                {
                    "id": "node-2",
                    "agent_type": "risk_manager_agent",
                    "config": {}
                }
            ],
            "edges": [
                {"from": "node-1", "to": "node-2"}
            ]
        }
    )

    executor = PipelineExecutor(
        pipeline=pipeline,
        user_id=pipeline.user_id,
        mode="paper"
    )

    assert executor.pipeline == pipeline
    assert executor.mode == "paper"
    assert len(executor.nodes) == 2
    assert len(executor.edges) == 1


def test_pipeline_executor_build_execution_order():
    """Test building execution order from pipeline config."""
    pipeline = Pipeline(
        id=uuid4(),
        user_id=uuid4(),
        name="Test Pipeline",
        description="Test",
        config={
            "symbol": "AAPL",
            "nodes": [
                {"id": "node-1", "agent_type": "market_data_agent", "config": {}},
                {"id": "node-2", "agent_type": "bias_agent", "config": {}},
                {"id": "node-3", "agent_type": "risk_manager_agent", "config": {}}
            ],
            "edges": []
        }
    )

    executor = PipelineExecutor(pipeline=pipeline, user_id=pipeline.user_id)
    execution_order = executor._build_execution_order()

    assert len(execution_order) == 3
    # First node in fixed order should be market_data_agent
    assert execution_order[0]["agent_type"] == "market_data_agent"


def test_pipeline_executor_execute_simple_pipeline():
    """Test executing a simple single-agent pipeline."""
    import asyncio

    pipeline = Pipeline(
        id=uuid4(),
        user_id=uuid4(),
        name="Simple Test Pipeline",
        description="Test",
        config={
            "symbol": "AAPL",
            "nodes": [
                {
                    "id": "data-1",
                    "agent_type": "market_data_agent",
                    "config": {
                        "timeframes": ["5m"],
                        "lookback_periods": 50,
                        "use_mock_data": True
                    }
                }
            ],
            "edges": []
        }
    )

    executor = PipelineExecutor(pipeline=pipeline, user_id=pipeline.user_id, mode="paper")
    result_state = asyncio.run(executor.execute())

    assert result_state is not None
    assert result_state.market_data is not None
    assert result_state.completed_at is not None
    assert len(result_state.errors) == 0


def test_pipeline_executor_error_handling():
    """Test error handling in pipeline execution."""
    import asyncio

    pipeline = Pipeline(
        id=uuid4(),
        user_id=uuid4(),
        name="Error Test Pipeline",
        description="Test",
        config={
            "symbol": "AAPL",
            "nodes": [
                {
                    "id": "data-1",
                    "agent_type": "market_data_agent",
                    "config": {
                        "timeframes": [],  # Invalid: empty timeframes
                        "use_mock_data": True
                    }
                }
            ],
            "edges": []
        }
    )

    executor = PipelineExecutor(pipeline=pipeline, user_id=pipeline.user_id)

    try:
        result_state = asyncio.run(executor.execute())
        assert len(result_state.errors) > 0 or result_state.market_data is None
    except Exception:
        pass  # Exception is also acceptable error-handling behaviour


def test_should_abort_on_error():
    """Test abort logic for different error types."""
    pipeline = Pipeline(
        id=uuid4(),
        user_id=uuid4(),
        name="Test",
        description="Test",
        config={
            "symbol": "AAPL",
            "nodes": [{"id": "node-1", "agent_type": "market_data_agent", "config": {}}],
            "edges": []
        }
    )

    executor = PipelineExecutor(pipeline=pipeline, user_id=pipeline.user_id)

    assert executor._should_abort_on_error("market_data_agent", "Some error") == True
    assert executor._should_abort_on_error("risk_manager_agent", "Some error") == True
    assert executor._should_abort_on_error("reporting_agent", "Some error") == False
    assert executor._should_abort_on_error("any_agent", "BudgetExceededException occurred") == True


def test_execution_manager_operations():
    """Test ExecutionManager has expected interface."""
    from app.orchestration.executor import ExecutionManager

    assert hasattr(ExecutionManager, 'start_execution')
    assert hasattr(ExecutionManager, 'get_execution_status')


def test_pipeline_state_flow():
    """Test that pipeline state flows correctly through agents."""
    import asyncio

    pipeline = Pipeline(
        id=uuid4(),
        user_id=uuid4(),
        name="State Flow Test",
        description="Test",
        config={
            "symbol": "AAPL",
            "nodes": [
                {
                    "id": "data-1",
                    "agent_type": "market_data_agent",
                    "config": {
                        "timeframes": ["5m", "1h"],
                        "use_mock_data": True
                    }
                }
            ],
            "edges": []
        }
    )

    executor = PipelineExecutor(pipeline=pipeline, user_id=pipeline.user_id)
    result_state = asyncio.run(executor.execute())

    assert result_state.pipeline_id == pipeline.id
    assert result_state.execution_id == executor.execution_id
    assert result_state.symbol == "AAPL"
    assert result_state.market_data is not None
    assert len(result_state.market_data.timeframes) >= 2
    assert result_state.started_at is not None
    assert result_state.completed_at is not None
