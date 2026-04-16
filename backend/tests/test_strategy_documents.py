from app.services.strategy_documents import (
    compose_markdown,
    normalize_pipeline_spec,
    parse_frontmatter,
    remove_pipeline_brokers,
    remove_pipeline_secrets,
    slugify,
)


def test_parse_frontmatter_and_body():
    markdown = """---
title: London Open Sweep
visibility: private
markets: forex, futures
timeframes: 5m, 15m
tags: ict, liquidity
---

## Thesis

Trade the sweep into displacement.
"""
    frontmatter, body = parse_frontmatter(markdown)

    assert frontmatter["title"] == "London Open Sweep"
    assert frontmatter["visibility"] == "private"
    assert frontmatter["markets"] == ["forex", "futures"]
    assert frontmatter["timeframes"] == ["5m", "15m"]
    assert frontmatter["tags"] == ["ict", "liquidity"]
    assert "## Thesis" in body


def test_compose_markdown_round_trip():
    metadata = {
        "title": "Daily Bias",
        "visibility": "public",
        "tags": ["ict", "bias"],
        "timeframes": ["1h", "4h"],
    }
    markdown = compose_markdown(metadata, "## Thesis\n\nUse higher timeframe structure.")
    parsed, body = parse_frontmatter(markdown)

    assert parsed["title"] == "Daily Bias"
    assert parsed["visibility"] == "public"
    assert parsed["tags"] == ["ict", "bias"]
    assert parsed["timeframes"] == ["1h", "4h"]
    assert "higher timeframe structure" in body


def test_remove_pipeline_secrets_scrubs_nested_values():
    config = {
        "broker_tool": {
            "api_token": "secret",
            "account_id": "ABC123",
            "mode": "paper",
        },
        "notifications": {
            "telegram_chat_id": "1234",
            "enabled": True,
        },
        "nodes": [
            {"config": {"model": "gpt-4o", "api_key": "abc"}},
            {"config": {"threshold": 0.7}},
        ],
    }

    cleaned = remove_pipeline_secrets(config)

    assert cleaned["broker_tool"]["mode"] == "paper"
    assert "api_token" not in cleaned["broker_tool"]
    assert "account_id" not in cleaned["broker_tool"]
    assert "telegram_chat_id" not in cleaned["notifications"]
    assert "api_key" not in cleaned["nodes"][0]["config"]


def test_remove_pipeline_brokers_strips_top_level_and_agent_tools():
    snapshot = {
        "config": {
            "broker_tool": {
                "tool_type": "tradier_broker",
                "config": {
                    "account_type": "Sandbox",
                    "api_token": "secret",
                },
            },
            "nodes": [
                {
                    "agent_type": "risk_manager_agent",
                    "config": {
                        "tools": [
                            {"tool_type": "tradier_broker", "config": {"api_token": "secret"}},
                            {"tool_type": "rsi"},
                        ]
                    },
                },
                {
                    "agent_type": "trade_manager_agent",
                    "config": {
                        "tools": [
                            {"tool_type": "alpaca_broker"},
                            {"tool_type": "market_structure"},
                        ]
                    },
                },
            ],
        }
    }

    cleaned = remove_pipeline_brokers(snapshot)

    assert "broker_tool" not in cleaned["config"]
    assert cleaned["config"]["nodes"][0]["config"]["tools"] == [{"tool_type": "rsi"}]
    assert cleaned["config"]["nodes"][1]["config"]["tools"] == [{"tool_type": "market_structure"}]


def test_normalize_pipeline_spec_marks_runnable_when_config_present():
    normalized = normalize_pipeline_spec({"pipeline": {"config": {"nodes": [], "edges": []}}})
    assert normalized["is_runnable"] is True

    empty = normalize_pipeline_spec({})
    assert empty["is_runnable"] is False


def test_slugify_is_stable():
    assert slugify("ICT FVG Retracement") == "ict-fvg-retracement"
