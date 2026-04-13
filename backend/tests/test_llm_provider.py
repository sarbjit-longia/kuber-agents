from app.config import settings
from app.services.llm_provider import (
    get_llm_api_key,
    get_llm_base_url,
    get_llm_default_headers,
    resolve_chat_model,
)


def test_openai_provider_resolution(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai", raising=False)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "openai-key", raising=False)
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", None, raising=False)

    assert get_llm_api_key() == "openai-key"
    assert get_llm_base_url() is None
    assert get_llm_default_headers() == {}


def test_openrouter_provider_resolution(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openrouter", raising=False)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "router-key", raising=False)
    monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1", raising=False)
    monkeypatch.setattr(settings, "OPENROUTER_HTTP_REFERER", "https://clovercharts.com", raising=False)
    monkeypatch.setattr(settings, "OPENROUTER_APP_NAME", "CloverCharts", raising=False)

    assert get_llm_api_key() == "router-key"
    assert get_llm_base_url() == "https://openrouter.ai/api/v1"
    assert get_llm_default_headers() == {
        "HTTP-Referer": "https://clovercharts.com",
        "X-Title": "CloverCharts",
    }

def test_resolve_chat_model_for_openrouter(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openrouter", raising=False)
    assert resolve_chat_model("gpt-4o") == "openai/gpt-4o"
    assert resolve_chat_model("moonshotai/kimi-k2.5") == "moonshotai/kimi-k2.5"
