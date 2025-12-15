"""
Langfuse Integration Service

Provides tracing and observability for LLM calls and agent executions.
"""
from typing import Optional, Dict, Any
import structlog
from app.config import settings

logger = structlog.get_logger(__name__)

# Global Langfuse client
_langfuse_client = None


def get_langfuse_client():
    """Get or create Langfuse client singleton."""
    global _langfuse_client
    
    if not settings.LANGFUSE_ENABLED:
        return None
    
    if _langfuse_client is None:
        try:
            from langfuse import Langfuse
            
            _langfuse_client = Langfuse(
                secret_key=settings.LANGFUSE_SECRET_KEY,
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                host=settings.LANGFUSE_BASE_URL,
            )
            logger.info("langfuse_initialized", host=settings.LANGFUSE_BASE_URL)
        except Exception as e:
            logger.error("langfuse_initialization_failed", error=str(e))
            return None
    
    return _langfuse_client


def trace_agent_execution(
    execution_id: str,
    agent_type: str,
    agent_id: str,
    pipeline_id: str,
    user_id: str,
) -> Optional[Any]:
    """
    Create a Langfuse trace for an agent execution.
    
    Returns a trace object that can be used to add spans.
    """
    client = get_langfuse_client()
    if not client:
        return None
    
    try:
        trace = client.trace(
            name=f"agent_{agent_type}",
            user_id=str(user_id),
            session_id=str(execution_id),
            metadata={
                "agent_id": agent_id,
                "agent_type": agent_type,
                "pipeline_id": str(pipeline_id),
                "execution_id": str(execution_id),
            },
        )
        return trace
    except Exception as e:
        logger.error("langfuse_trace_creation_failed", error=str(e))
        return None


def trace_llm_call(
    trace: Any,
    model: str,
    prompt: str,
    response: str,
    tokens_used: Optional[Dict[str, int]] = None,
    cost: Optional[float] = None,
) -> None:
    """
    Add LLM call span to a trace.
    """
    if not trace:
        return
    
    try:
        generation = trace.generation(
            name="llm_call",
            model=model,
            input=prompt,
            output=response,
            usage=tokens_used or {},
            metadata={
                "cost": cost,
            },
        )
        
        if cost:
            generation.score(
                name="cost",
                value=cost,
            )
            
    except Exception as e:
        logger.error("langfuse_llm_span_failed", error=str(e))


def flush_langfuse():
    """Flush any pending Langfuse data."""
    client = get_langfuse_client()
    if client:
        try:
            client.flush()
        except Exception as e:
            logger.error("langfuse_flush_failed", error=str(e))

