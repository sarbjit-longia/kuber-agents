"""
Langfuse Integration Service

Provides tracing and observability for LLM calls and agent executions.
Compatible with Langfuse SDK v4 (OpenTelemetry-based).
"""
from typing import Optional, Dict, Any
import structlog
from app.config import settings

logger = structlog.get_logger(__name__)

# Global Langfuse client
_langfuse_client = None


def get_langfuse_client():
    """
    Get or create Langfuse client singleton.

    In SDK v4, the client is obtained via langfuse.get_client() which reads
    LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST from env.
    """
    global _langfuse_client

    if not settings.LANGFUSE_ENABLED:
        return None

    if _langfuse_client is None:
        try:
            from langfuse import get_client

            _langfuse_client = get_client()
            # Verify auth
            if _langfuse_client.auth_check():
                logger.info(
                    "langfuse_initialized",
                    host=settings.LANGFUSE_BASE_URL or settings.LANGFUSE_HOST,
                )
            else:
                logger.warning("langfuse_auth_failed", hint="Check API keys in .env")
                _langfuse_client = None
                return None
        except ImportError:
            logger.warning("langfuse_not_installed", hint="Install with: pip install langfuse")
            return None
        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ["quota", "rate limit", "429"]):
                logger.warning("langfuse_quota_exceeded", error=str(e))
            elif any(keyword in error_msg for keyword in ["401", "403", "key", "auth"]):
                logger.warning(
                    "langfuse_auth_failed", error=str(e), hint="Check API keys in .env"
                )
            else:
                logger.warning("langfuse_initialization_failed", error=str(e))
            return None

    return _langfuse_client


class LangfuseTrace:
    """
    Wrapper that provides a v2-compatible trace interface on top of the v4 SDK.

    In v4, tracing is done via OpenTelemetry spans. This wrapper uses the
    @observe decorator pattern under the hood but exposes the same API
    that callers (agent_runner.py, agents) expect.
    """

    def __init__(self, trace_id: str, name: str, metadata: Dict[str, Any]):
        self.trace_id = trace_id
        self.name = name
        self.metadata = metadata


def trace_agent_execution(
    execution_id: str,
    agent_type: str,
    agent_id: str,
    pipeline_id: str,
    user_id: str,
) -> Optional[LangfuseTrace]:
    """
    Create a Langfuse trace for an agent execution.

    Returns a LangfuseTrace wrapper that can be passed to trace_llm_call
    and trace_tool_call for span creation.
    """
    client = get_langfuse_client()
    if not client:
        return None

    def create_trace():
        trace_id = client.create_trace_id()
        return LangfuseTrace(
            trace_id=trace_id,
            name=f"agent_{agent_type}",
            metadata={
                "agent_id": agent_id,
                "agent_type": agent_type,
                "pipeline_id": str(pipeline_id),
                "execution_id": str(execution_id),
                "user_id": str(user_id),
            },
        )

    return safe_langfuse_operation("trace_creation", create_trace)


def trace_llm_call(
    trace: Any,
    model: str,
    prompt: str,
    response: str,
    tokens_used: Optional[Dict[str, int]] = None,
    cost: Optional[float] = None,
) -> None:
    """
    Record an LLM call. In v4, OpenAI calls are auto-traced via the
    langfuse.openai wrapper. This function serves as a manual fallback
    for non-OpenAI calls or additional metadata.
    """
    if not trace:
        return

    client = get_langfuse_client()
    if not client:
        return

    def create_event():
        client.create_event(
            name="llm_call",
            metadata={
                "model": model,
                "cost": cost,
                "tokens": tokens_used or {},
                "trace_id": trace.trace_id if hasattr(trace, "trace_id") else None,
                "agent": trace.name if hasattr(trace, "name") else None,
            },
            input=prompt[:2000] if prompt else None,
            output=response[:2000] if response else None,
        )
        # Also record cost as a score for dashboards
        if cost and hasattr(trace, "trace_id"):
            client.create_score(
                trace_id=trace.trace_id,
                name="cost",
                value=cost,
            )

    safe_langfuse_operation("llm_generation", create_event)


def trace_tool_call(
    trace: Any,
    tool_name: str,
    arguments: Dict[str, Any],
    output: Any,
) -> None:
    """
    Record a tool call as a Langfuse event.
    """
    if not trace:
        return

    client = get_langfuse_client()
    if not client:
        return

    def create_event():
        client.create_event(
            name=f"tool_{tool_name}",
            metadata={
                "tool_name": tool_name,
                "trace_id": trace.trace_id if hasattr(trace, "trace_id") else None,
            },
            input=arguments,
            output=str(output)[:2000] if output else None,
        )

    safe_langfuse_operation("tool_span", create_event)


def safe_langfuse_operation(operation_name: str, func, *args, **kwargs) -> Optional[Any]:
    """
    Execute a Langfuse operation safely, catching all errors.

    This ensures that Langfuse quota exhaustion, rate limiting, or API errors
    never break the main application flow.
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        error_msg = str(e).lower()

        if any(
            keyword in error_msg
            for keyword in ["quota", "rate limit", "429", "too many requests"]
        ):
            logger.warning(
                f"langfuse_{operation_name}_quota_exceeded",
                error=str(e),
                hint="Langfuse quota exhausted or rate limited",
            )
        elif any(
            keyword in error_msg for keyword in ["401", "403", "unauthorized", "forbidden"]
        ):
            logger.warning(
                f"langfuse_{operation_name}_auth_failed",
                error=str(e),
                hint="Check Langfuse API keys",
            )
        else:
            logger.warning(
                f"langfuse_{operation_name}_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

        return None


def flush_langfuse():
    """Flush any pending Langfuse data."""
    client = get_langfuse_client()
    if client:
        safe_langfuse_operation("flush", client.flush)
