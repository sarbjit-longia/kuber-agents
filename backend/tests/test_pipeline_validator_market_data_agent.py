from app.orchestration.validator import PipelineValidator


def test_pipeline_validator_accepts_market_data_agent_node():
    """
    Regression: guided builder includes a `market_data_agent` node.
    Validator must not crash on unknown agent type.
    """
    pipeline_config = {
        "nodes": [
            {"id": "node-market", "agent_type": "market_data_agent", "config": {}},
        ],
        "edges": [],
    }

    validator = PipelineValidator()
    ok, errors = validator.validate(pipeline_config, trigger_mode="signal", scanner_id="dummy")

    assert ok is True
    assert errors == []

