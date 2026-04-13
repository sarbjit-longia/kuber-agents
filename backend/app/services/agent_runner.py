"""
Internal OpenAI-compatible agent runtime.

This replaces CrewAI for the pipeline agents while preserving the existing
prompt contracts and output schemas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

from app.services.langfuse_service import trace_llm_call, trace_tool_call
from app.services.llm_provider import create_openai_client, resolve_chat_model

logger = structlog.get_logger()


@dataclass
class AgentRunnerResult:
    content: str
    usage: Dict[str, int] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


class AgentRunnerError(RuntimeError):
    pass


class AgentRunner:
    def __init__(self, *, model: str, temperature: float = 0.2, timeout: int = 45):
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.client = create_openai_client()

    def run(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        trace: Any = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_handlers: Optional[Dict[str, Callable[[Dict[str, Any]], str]]] = None,
        max_iterations: int = 6,
        response_temperature: Optional[float] = None,
    ) -> AgentRunnerResult:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        all_tool_calls: List[Dict[str, Any]] = []
        usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        model_id = resolve_chat_model(self.model)

        for iteration in range(max_iterations):
            response = self.client.chat.completions.create(
                model=model_id,
                messages=messages,
                tools=tools or None,
                temperature=self.temperature if response_temperature is None else response_temperature,
                timeout=self.timeout,
            )

            usage = getattr(response, "usage", None)
            if usage:
                usage_totals["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
                usage_totals["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
                usage_totals["total_tokens"] += getattr(usage, "total_tokens", 0) or 0

            message = response.choices[0].message
            content = (message.content or "").strip()
            trace_llm_call(
                trace=trace,
                model=model_id,
                prompt=user_prompt if iteration == 0 else json.dumps(messages[-2:], default=str),
                response=content or "[tool-call]",
                tokens_used=usage_totals,
            )

            if not getattr(message, "tool_calls", None):
                return AgentRunnerResult(content=content, usage=usage_totals, tool_calls=all_tool_calls)

            if not tool_handlers:
                raise AgentRunnerError("LLM requested tool calls but no tool handlers were provided")

            assistant_message = message.model_dump(exclude_none=True)
            messages.append(assistant_message)

            for tool_call in message.tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    raise AgentRunnerError(f"Invalid tool arguments for {tool_call.function.name}: {exc}") from exc

                handler = tool_handlers.get(tool_call.function.name)
                if not handler:
                    raise AgentRunnerError(f"No tool handler registered for {tool_call.function.name}")

                logger.info("agent_tool_call", name=tool_call.function.name, arguments=arguments)
                tool_output = handler(arguments)
                all_tool_calls.append(
                    {
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": arguments,
                        "output": tool_output,
                    }
                )
                trace_tool_call(trace, tool_call.function.name, arguments, tool_output)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_output,
                    }
                )

        raise AgentRunnerError(f"Agent tool loop exceeded max_iterations={max_iterations}")
