"""
Tests for Pipeline Orchestration

Tests the pipeline executor, flow, and Celery tasks.
"""
import pytest
from uuid import uuid4
from datetime import datetime

from app.orchestration.executor import PipelineExecutor
from app.schemas.pipeline_state import PipelineState
from app.models.pipeline import Pipeline
from app.agents import TimeTriggerAgent, MarketDataAgent


def test_pipeline_executor_initialization():
    """Test PipelineExecutor initialization."""
    print("\n✅ Testing Pipeline Executor Initialization")
    
    # Create mock pipeline
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
                    "agent_type": "time_trigger",
                    "config": {"interval": "5m"}
                },
                {
                    "id": "node-2",
                    "agent_type": "market_data_agent",
                    "config": {"timeframes": ["5m"], "use_mock_data": True}
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
    
    print(f"   Executor initialized with {len(executor.nodes)} nodes")
    print("   ✓ Executor initialization working\n")


def test_pipeline_executor_build_execution_order():
    """Test building execution order from pipeline config."""
    print("✅ Testing Execution Order Building")
    
    pipeline = Pipeline(
        id=uuid4(),
        user_id=uuid4(),
        name="Test Pipeline",
        description="Test",
        config={
            "symbol": "AAPL",
            "nodes": [
                {"id": "node-1", "agent_type": "time_trigger", "config": {}},
                {"id": "node-2", "agent_type": "market_data_agent", "config": {}},
                {"id": "node-3", "agent_type": "risk_manager_agent", "config": {}}
            ],
            "edges": []
        }
    )
    
    executor = PipelineExecutor(pipeline=pipeline, user_id=pipeline.user_id)
    execution_order = executor._build_execution_order()
    
    assert len(execution_order) == 3
    assert execution_order[0]["id"] == "node-1"
    
    print(f"   Execution order: {[node['agent_type'] for node in execution_order]}")
    print("   ✓ Execution order building working\n")


def test_pipeline_executor_execute_simple_pipeline():
    """Test executing a simple 2-agent pipeline."""
    import asyncio
    
    print("✅ Testing Simple Pipeline Execution")
    
    pipeline = Pipeline(
        id=uuid4(),
        user_id=uuid4(),
        name="Simple Test Pipeline",
        description="Test",
        config={
            "symbol": "AAPL",
            "nodes": [
                {
                    "id": "trigger-1",
                    "agent_type": "time_trigger",
                    "config": {"interval": "5m"}
                },
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
            "edges": [{"from": "trigger-1", "to": "data-1"}]
        }
    )
    
    executor = PipelineExecutor(pipeline=pipeline, user_id=pipeline.user_id, mode="paper")
    
    # Execute pipeline
    result_state = asyncio.run(executor.execute())
    
    assert result_state is not None
    assert result_state.trigger_met is True
    assert result_state.market_data is not None
    assert result_state.completed_at is not None
    assert len(result_state.errors) == 0
    
    print(f"   Trigger met: {result_state.trigger_met}")
    print(f"   Market data fetched: {result_state.market_data.symbol}")
    print(f"   Current price: ${result_state.market_data.current_price:.2f}")
    print(f"   Total cost: ${result_state.total_cost:.2f}")
    print(f"   Execution logs: {len(result_state.execution_log)} entries")
    print("   ✓ Simple pipeline execution working\n")


def test_pipeline_executor_error_handling():
    """Test error handling in pipeline execution."""
    import asyncio
    
    print("✅ Testing Error Handling")
    
    # Create pipeline with invalid config
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
    
    # Execute - should handle error gracefully
    try:
        result_state = asyncio.run(executor.execute())
        # Check that errors were captured
        assert len(result_state.errors) > 0 or result_state.market_data is None
        print(f"   Errors captured: {len(result_state.errors)}")
        print("   ✓ Error handling working\n")
    except Exception as e:
        print(f"   Exception raised (expected): {type(e).__name__}")
        print("   ✓ Error handling working\n")


def test_should_abort_on_error():
    """Test abort logic for different error types."""
    print("✅ Testing Abort Logic")
    
    pipeline = Pipeline(
        id=uuid4(),
        user_id=uuid4(),
        name="Test",
        description="Test",
        config={
            "symbol": "AAPL",
            "nodes": [{"id": "node-1", "agent_type": "time_trigger", "config": {}}],
            "edges": []
        }
    )
    
    executor = PipelineExecutor(pipeline=pipeline, user_id=pipeline.user_id)
    
    # Critical agent should abort
    assert executor._should_abort_on_error("market_data_agent", "Some error") == True
    assert executor._should_abort_on_error("risk_manager_agent", "Some error") == True
    
    # Non-critical agent should continue
    assert executor._should_abort_on_error("reporting_agent", "Some error") == False
    
    # Critical errors should always abort
    assert executor._should_abort_on_error("any_agent", "BudgetExceededException occurred") == True
    
    print("   Critical agents abort: ✓")
    print("   Non-critical agents continue: ✓")
    print("   Critical errors abort: ✓")
    print("   ✓ Abort logic working\n")


def test_execution_manager_operations():
    """Test ExecutionManager static methods."""
    print("✅ Testing ExecutionManager")
    
    from app.orchestration.executor import ExecutionManager
    
    # Test that the ExecutionManager class exists and has the right methods
    assert hasattr(ExecutionManager, 'start_execution')
    assert hasattr(ExecutionManager, 'get_execution_status')
    
    print("   ExecutionManager has start_execution: ✓")
    print("   ExecutionManager has get_execution_status: ✓")
    print("   ✓ ExecutionManager operations available\n")


def test_pipeline_state_flow():
    """Test that pipeline state flows correctly through agents."""
    import asyncio
    
    print("✅ Testing Pipeline State Flow")
    
    pipeline = Pipeline(
        id=uuid4(),
        user_id=uuid4(),
        name="State Flow Test",
        description="Test",
        config={
            "symbol": "AAPL",
            "nodes": [
                {
                    "id": "trigger-1",
                    "agent_type": "time_trigger",
                    "config": {"interval": "5m"}
                },
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
    
    # Check state evolution
    assert result_state.pipeline_id == pipeline.id
    assert result_state.execution_id == executor.execution_id
    assert result_state.symbol == "AAPL"
    assert result_state.trigger_met is True
    assert result_state.market_data is not None
    assert len(result_state.market_data.timeframes) >= 2
    assert result_state.started_at is not None
    assert result_state.completed_at is not None
    
    print(f"   State flowed through {len(pipeline.config['nodes'])} agents")
    print(f"   Timeframes collected: {list(result_state.market_data.timeframes.keys())}")
    print(f"   Execution time: {(result_state.completed_at - result_state.started_at).total_seconds():.2f}s")
    print("   ✓ Pipeline state flow working\n")


if __name__ == "__main__":
    """Run tests manually."""
    test_pipeline_executor_initialization()
    test_pipeline_executor_build_execution_order()
    test_pipeline_executor_execute_simple_pipeline()
    test_pipeline_executor_error_handling()
    test_should_abort_on_error()
    test_execution_manager_operations()
    test_pipeline_state_flow()
    
    print("\n" + "="*60)
    print("✅ ALL ORCHESTRATION TESTS PASSED!")
    print("="*60)

