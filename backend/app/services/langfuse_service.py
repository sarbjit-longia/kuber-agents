"""
Langfuse Integration Service.

Provides safe tracing helpers for pipeline, agent, tool, and report execution.
The implementation is defensive because Langfuse may be unavailable locally and
the deployed SDK surface can vary across versions.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional, Dict, Any, Iterator
from uuid import uuid4

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# Global Langfuse client
_langfuse_client = None
_current_trace: ContextVar[Optional["LangfuseObservation"]] = ContextVar(
    "langfuse_current_trace",
    default=None,
)
_current_observation: ContextVar[Optional["LangfuseObservation"]] = ContextVar(
    "langfuse_current_observation",
    default=None,
)


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


def _clean_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {key: value for key, value in (metadata or {}).items() if value is not None}


def _observation_id(raw: Any) -> Optional[str]:
    for attr in ("id", "observation_id"):
        value = getattr(raw, attr, None)
        if value:
            return str(value)
    return None


def _trace_id(raw: Any) -> Optional[str]:
    for attr in ("trace_id", "id"):
        value = getattr(raw, attr, None)
        if value:
            return str(value)
    return None


def _call_with_fallbacks(callables: list) -> Any:
    last_error: Optional[Exception] = None
    for candidate in callables:
        try:
            return candidate()
        except TypeError as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return None


class LangfuseObservation:
    """Best-effort wrapper over a Langfuse trace/span/generation parent."""

    def __init__(
        self,
        *,
        client: Any,
        raw: Any,
        context_manager: Any = None,
        trace_id: Optional[str],
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        kind: str = "span",
    ):
        self.client = client
        self.raw = raw
        self.context_manager = context_manager
        self.trace_id = trace_id
        self.name = name
        self.metadata = _clean_metadata(metadata)
        self.kind = kind

    def close(self) -> None:
        if self.context_manager is not None:
            try:
                self.context_manager.__exit__(None, None, None)
            except Exception:
                logger.warning("langfuse_context_exit_failed", observation=self.name, exc_info=True)
            finally:
                self.context_manager = None
                return

        if self.raw is not None and hasattr(self.raw, "end"):
            safe_langfuse_operation("observation_end", self.raw.end)

    @property
    def observation_id(self) -> Optional[str]:
        return _observation_id(self.raw)

    def span(
        self,
        *,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        input: Any = None,
    ) -> Optional["LangfuseObservation"]:
        return create_span(name=name, parent=self, metadata=metadata, input=input)

    def generation(
        self,
        *,
        name: str,
        model: str,
        input: Any = None,
        output: Any = None,
        usage: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        payload = {
            "name": name,
            "model": model,
            "input": input,
            "output": output,
            "usage": usage or {},
            "metadata": _clean_metadata(metadata),
        }

        def create_generation():
            if hasattr(self.client, "_start_as_current_otel_span_with_processed_media"):
                context_manager = self.client._start_as_current_otel_span_with_processed_media(
                    name=name,
                    as_type="generation",
                    input=input,
                    output=output,
                    metadata=_clean_metadata(metadata),
                    model=model,
                    usage_details=usage or {},
                )
                generation = context_manager.__enter__()
                generation_id = getattr(generation, "id", None)
                context_manager.__exit__(None, None, None)
                return generation_id

            if self.raw and hasattr(self.raw, "generation"):
                return _call_with_fallbacks(
                    [
                        lambda: self.raw.generation(**payload),
                        lambda: self.raw.generation(
                            name=name,
                            model=model,
                            input=input,
                            output=output,
                            metadata=_clean_metadata(metadata),
                        ),
                    ]
                )

            parent_id = self.observation_id
            if hasattr(self.client, "generation"):
                return _call_with_fallbacks(
                    [
                        lambda: self.client.generation(
                            trace_id=self.trace_id,
                            parent_observation_id=parent_id,
                            **payload,
                        ),
                        lambda: self.client.generation(trace_id=self.trace_id, **payload),
                        lambda: self.client.generation(**payload),
                    ]
                )

            if hasattr(self.client, "create_event"):
                return self.client.create_event(
                    name=name,
                    metadata={
                        **_clean_metadata(metadata),
                        "model": model,
                        "usage": usage or {},
                        "trace_id": self.trace_id,
                        "parent_observation_id": parent_id,
                    },
                    input=input,
                    output=output,
                )

            return None

        return safe_langfuse_operation("generation", create_generation)


def trace_agent_execution(
    execution_id: str,
    agent_type: str,
    agent_id: str,
    pipeline_id: str,
    user_id: str,
) -> Optional[LangfuseObservation]:
    """
    Get the active agent span if one exists, otherwise create a trace and span.
    """
    active_observation = get_current_observation()
    metadata = {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "pipeline_id": str(pipeline_id),
        "execution_id": str(execution_id),
        "user_id": str(user_id),
    }

    if active_observation and active_observation.metadata.get("agent_id") == agent_id:
        return active_observation

    root_trace = get_current_trace()
    if not root_trace:
        root_trace = start_or_resume_trace(
            name="pipeline_execution",
            session_id=str(execution_id),
            user_id=str(user_id),
            metadata=metadata,
        )

    if not root_trace:
        return None

    return create_span(name=f"agent:{agent_type}", parent=root_trace, metadata=metadata)


def get_current_trace() -> Optional[LangfuseObservation]:
    return _current_trace.get()


def get_current_observation() -> Optional[LangfuseObservation]:
    return _current_observation.get()


@contextmanager
def activate_observation(
    observation: Optional[LangfuseObservation],
    *,
    as_trace: bool = False,
) -> Iterator[Optional[LangfuseObservation]]:
    if not observation:
        yield None
        return

    trace_token = None
    observation_token = _current_observation.set(observation)
    if as_trace:
        trace_token = _current_trace.set(observation)

    try:
        yield observation
    finally:
        _current_observation.reset(observation_token)
        if trace_token is not None:
            _current_trace.reset(trace_token)
        observation.close()


def start_or_resume_trace(
    *,
    name: str,
    session_id: str,
    user_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[LangfuseObservation]:
    client = get_langfuse_client()
    if not client:
        return None

    metadata = _clean_metadata(metadata)

    def create_trace():
        requested_trace_id = trace_id
        raw = None
        context_manager = None
        if hasattr(client, "_start_as_current_otel_span_with_processed_media"):
            if requested_trace_id:
                remote_parent_span = client._create_remote_parent_span(
                    trace_id=requested_trace_id,
                    parent_span_id=None,
                )
                context_manager = client._create_span_with_parent_context(
                    name=name,
                    remote_parent_span=remote_parent_span,
                    as_type="span",
                    metadata=metadata,
                )
            else:
                context_manager = client._start_as_current_otel_span_with_processed_media(
                    name=name,
                    as_type="span",
                    metadata=metadata,
                )
            raw = context_manager.__enter__()
        elif hasattr(client, "trace"):
            trace_payload = {
                "name": name,
                "session_id": session_id,
                "user_id": user_id,
                "metadata": metadata,
            }
            raw = _call_with_fallbacks(
                [
                    lambda: client.trace(id=requested_trace_id, **trace_payload)
                    if requested_trace_id
                    else client.trace(**trace_payload),
                    lambda: client.trace(**trace_payload),
                    lambda: client.trace(name=name, metadata=metadata),
                ]
            )

        resolved_trace_id = requested_trace_id or _trace_id(raw)
        if not resolved_trace_id:
            if hasattr(client, "create_trace_id"):
                resolved_trace_id = str(client.create_trace_id())
            else:
                resolved_trace_id = str(uuid4())

        return LangfuseObservation(
            client=client,
            raw=raw,
            context_manager=context_manager,
            trace_id=resolved_trace_id,
            name=name,
            metadata=metadata,
            kind="trace",
        )

    return safe_langfuse_operation("trace_creation", create_trace)


def resume_execution_trace(
    *,
    trace_id: Optional[str],
    session_id: str,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[LangfuseObservation]:
    if not trace_id:
        return None

    return start_or_resume_trace(
        name="pipeline_execution",
        trace_id=trace_id,
        session_id=session_id,
        user_id=user_id,
        metadata=metadata,
    )


def create_span(
    *,
    name: str,
    parent: Optional[LangfuseObservation] = None,
    metadata: Optional[Dict[str, Any]] = None,
    input: Any = None,
) -> Optional[LangfuseObservation]:
    client = get_langfuse_client()
    parent = parent or get_current_observation() or get_current_trace()
    if not client or not parent:
        return None

    metadata = _clean_metadata(metadata)

    def create_child():
        raw = None
        context_manager = None
        if hasattr(client, "_start_as_current_otel_span_with_processed_media"):
            if parent.raw is None and parent.trace_id and hasattr(client, "_create_remote_parent_span"):
                remote_parent_span = client._create_remote_parent_span(
                    trace_id=parent.trace_id,
                    parent_span_id=parent.observation_id,
                )
                context_manager = client._create_span_with_parent_context(
                    name=name,
                    remote_parent_span=remote_parent_span,
                    as_type="span",
                    metadata=metadata,
                    input=input,
                )
            else:
                context_manager = client._start_as_current_otel_span_with_processed_media(
                    name=name,
                    as_type="span",
                    metadata=metadata,
                    input=input,
                )
            raw = context_manager.__enter__()
        elif parent.raw and hasattr(parent.raw, "span"):
            raw = _call_with_fallbacks(
                [
                    lambda: parent.raw.span(name=name, metadata=metadata, input=input),
                    lambda: parent.raw.span(name=name, metadata=metadata),
                    lambda: parent.raw.span(name=name),
                ]
            )
        elif hasattr(client, "span"):
            raw = _call_with_fallbacks(
                [
                    lambda: client.span(
                        trace_id=parent.trace_id,
                        parent_observation_id=parent.observation_id,
                        name=name,
                        metadata=metadata,
                        input=input,
                    ),
                    lambda: client.span(
                        trace_id=parent.trace_id,
                        name=name,
                        metadata=metadata,
                        input=input,
                    ),
                    lambda: client.span(name=name, metadata=metadata),
                ]
            )

        return LangfuseObservation(
            client=client,
            raw=raw,
            context_manager=context_manager,
            trace_id=parent.trace_id,
            name=name,
            metadata={**parent.metadata, **metadata},
            kind="span",
        )

    return safe_langfuse_operation("span_creation", create_child)


@contextmanager
def span_context(
    *,
    name: str,
    parent: Optional[LangfuseObservation] = None,
    metadata: Optional[Dict[str, Any]] = None,
    input: Any = None,
) -> Iterator[Optional[LangfuseObservation]]:
    observation = create_span(name=name, parent=parent, metadata=metadata, input=input)
    with activate_observation(observation, as_trace=False):
        yield observation


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

    if isinstance(trace, LangfuseObservation):
        trace.generation(
            name="llm_call",
            model=model,
            input=prompt[:2000] if prompt else None,
            output=response[:2000] if response else None,
            usage=tokens_used or {},
            metadata={"cost": cost, "agent": trace.name},
        )
    elif hasattr(client, "create_event"):
        safe_langfuse_operation(
            "llm_generation",
            lambda: client.create_event(
                name="llm_call",
                metadata={
                    "model": model,
                    "cost": cost,
                    "tokens": tokens_used or {},
                    "trace_id": getattr(trace, "trace_id", None),
                },
                input=prompt[:2000] if prompt else None,
                output=response[:2000] if response else None,
            ),
        )

    if cost and getattr(trace, "trace_id", None) and hasattr(client, "create_score"):
        safe_langfuse_operation(
            "llm_cost_score",
            lambda: client.create_score(
                trace_id=trace.trace_id,
                name="cost",
                value=cost,
            ),
        )


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

    if isinstance(trace, LangfuseObservation):
        with span_context(
            name=f"tool:{tool_name}",
            parent=trace,
            metadata={"tool_name": tool_name},
            input=arguments,
        ) as tool_span:
            if tool_span:
                tool_span.generation(
                    name=f"tool_{tool_name}",
                    model="tool",
                    input=arguments,
                    output=str(output)[:2000] if output else None,
                    metadata={"tool_name": tool_name},
                )
        return

    if hasattr(client, "create_event"):
        safe_langfuse_operation(
            "tool_span",
            lambda: client.create_event(
                name=f"tool_{tool_name}",
                metadata={
                    "tool_name": tool_name,
                    "trace_id": getattr(trace, "trace_id", None),
                },
                input=arguments,
                output=str(output)[:2000] if output else None,
            ),
        )


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
