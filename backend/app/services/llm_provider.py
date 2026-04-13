"""
Shared helpers for OpenAI-compatible LLM providers.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from openai import AsyncOpenAI, OpenAI

from app.config import settings


def get_llm_provider() -> str:
    return (settings.LLM_PROVIDER or "openai").strip().lower()


def get_llm_api_key() -> Optional[str]:
    if get_llm_provider() == "openrouter":
        return settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY
    return settings.OPENAI_API_KEY


def get_llm_base_url() -> Optional[str]:
    if get_llm_provider() == "openrouter":
        return settings.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1"
    return settings.OPENAI_BASE_URL


def get_llm_default_headers() -> Dict[str, str]:
    if get_llm_provider() != "openrouter":
        return {}

    headers: Dict[str, str] = {}
    if settings.OPENROUTER_HTTP_REFERER:
        headers["HTTP-Referer"] = settings.OPENROUTER_HTTP_REFERER
    if settings.OPENROUTER_APP_NAME:
        headers["X-Title"] = settings.OPENROUTER_APP_NAME
    return headers


def create_openai_client(*, async_client: bool = False, **overrides: Any) -> OpenAI | AsyncOpenAI:
    kwargs: Dict[str, Any] = {"api_key": get_llm_api_key()}
    base_url = get_llm_base_url()
    headers = get_llm_default_headers()

    if base_url:
        kwargs["base_url"] = base_url
    if headers:
        kwargs["default_headers"] = headers

    kwargs.update(overrides)
    if async_client:
        return AsyncOpenAI(**kwargs)
    return OpenAI(**kwargs)


def resolve_chat_model(model_id: str) -> str:
    provider = get_llm_provider()
    if provider == "openrouter" and "/" not in model_id:
        return f"openai/{model_id}"
    return model_id
