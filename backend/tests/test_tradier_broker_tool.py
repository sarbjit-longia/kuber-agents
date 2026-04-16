from types import SimpleNamespace

from app.services.brokers.factory import _account_type_to_paper
from app.tools.tradier_broker import TradierBrokerTool


def test_tradier_tool_prefers_explicit_credentials_over_env(monkeypatch):
    monkeypatch.setattr(
        "app.tools.tradier_broker.settings",
        SimpleNamespace(TRADIER_API_TOKEN="env-token", TRADIER_ACCOUNT_ID="ENV123"),
    )

    tool = TradierBrokerTool(
        config={
            "account_type": "Live",
            "api_token": "config-token",
            "account_id": "LIVE123",
            "use_env_credentials": True,
        }
    )

    assert tool._resolve_credentials() == ("config-token", "LIVE123")


def test_tradier_tool_normalizes_account_type_labels():
    sandbox_tool = TradierBrokerTool(config={"account_type": "Sandbox", "api_token": "x", "account_id": "y"})
    live_tool = TradierBrokerTool(config={"account_type": "Live", "api_token": "x", "account_id": "y"})

    assert sandbox_tool._normalized_account_type() == "sandbox"
    assert live_tool._normalized_account_type() == "live"


def test_account_type_to_paper_handles_tradier_ui_values():
    assert _account_type_to_paper("Sandbox", default=False) is True
    assert _account_type_to_paper("Live", default=True) is False
    assert _account_type_to_paper("paper", default=False) is True
    assert _account_type_to_paper("production", default=True) is False
