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
    """
    Get or create Langfuse client singleton.
    
    Handles initialization errors gracefully, including quota exhaustion
    and authentication issues.
    """
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
        except ImportError:
            logger.warning("langfuse_not_installed", hint="Install with: pip install langfuse")
            return None
        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['quota', 'rate limit', '429']):
                logger.warning("langfuse_quota_exceeded", error=str(e))
            elif any(keyword in error_msg for keyword in ['401', '403', 'key', 'auth']):
                logger.warning("langfuse_auth_failed", error=str(e), hint="Check API keys in .env")
            else:
                logger.warning("langfuse_initialization_failed", error=str(e))
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
    Handles quota exhaustion, rate limiting, and API errors gracefully.
    """
    client = get_langfuse_client()
    if not client:
        return None
    
    def create_trace():
        return client.trace(
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
    Add LLM call span to a trace.
    Handles rate limiting and API errors gracefully.
    """
    if not trace:
        return
    
    def create_generation():
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
        
        if cost and generation:
            generation.score(
                name="cost",
                value=cost,
            )
        
        return generation
    
    safe_langfuse_operation("llm_generation", create_generation)


def safe_langfuse_operation(operation_name: str, func, *args, **kwargs) -> Optional[Any]:
    """
    Execute a Langfuse operation safely, catching all errors.
    
    This ensures that Langfuse quota exhaustion, rate limiting, or API errors
    never break the main application flow.
    
    Args:
        operation_name: Name of the operation for logging
        func: Function to execute
        *args, **kwargs: Arguments to pass to the function
        
    Returns:
        Result of the function or None if it fails
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        error_msg = str(e).lower()
        
        # Identify specific Langfuse errors
        if any(keyword in error_msg for keyword in ['quota', 'rate limit', '429', 'too many requests']):
            logger.warning(
                f"langfuse_{operation_name}_quota_exceeded",
                error=str(e),
                hint="Langfuse quota exhausted or rate limited"
            )
        elif any(keyword in error_msg for keyword in ['401', '403', 'unauthorized', 'forbidden']):
            logger.warning(
                f"langfuse_{operation_name}_auth_failed",
                error=str(e),
                hint="Check Langfuse API keys"
            )
        else:
            logger.warning(
                f"langfuse_{operation_name}_failed",
                error=str(e),
                error_type=type(e).__name__
            )
        
        return None


def flush_langfuse():
    """Flush any pending Langfuse data."""
    client = get_langfuse_client()
    if client:
        safe_langfuse_operation("flush", client.flush)

