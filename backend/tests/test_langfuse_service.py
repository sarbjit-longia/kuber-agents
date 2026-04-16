from app.services import langfuse_service


class MockObservation:
    _counter = 0

    def __init__(self, *, name, trace_id, metadata=None, parent=None):
        MockObservation._counter += 1
        self.id = f"obs-{MockObservation._counter}"
        self.name = name
        self.trace_id = trace_id
        self.metadata = metadata or {}
        self.parent = parent
        self.spans = []
        self.generations = []

    def span(self, name, metadata=None, input=None):
        child = MockObservation(
            name=name,
            trace_id=self.trace_id,
            metadata=metadata,
            parent=self,
        )
        child.input = input
        self.spans.append(child)
        return child

    def generation(self, **payload):
        self.generations.append(payload)
        return payload


class MockLangfuseClient:
    def __init__(self):
        self.traces = []
        self.events = []
        self.scores = []

    def trace(self, name, session_id=None, user_id=None, metadata=None, id=None):
        trace = MockObservation(
            name=name,
            trace_id=id or f"trace-{len(self.traces) + 1}",
            metadata={
                "session_id": session_id,
                "user_id": user_id,
                **(metadata or {}),
            },
        )
        self.traces.append(trace)
        return trace

    def create_score(self, **payload):
        self.scores.append(payload)

    def create_event(self, **payload):
        self.events.append(payload)


def test_trace_agent_execution_reuses_active_agent_span(monkeypatch):
    client = MockLangfuseClient()
    monkeypatch.setattr(langfuse_service, "get_langfuse_client", lambda: client)

    trace = langfuse_service.start_or_resume_trace(
        name="pipeline_execution",
        session_id="exec-1",
        user_id="user-1",
        metadata={"execution_id": "exec-1"},
    )

    with langfuse_service.activate_observation(trace, as_trace=True):
        with langfuse_service.span_context(
            name="agent:bias_agent",
            parent=trace,
            metadata={"agent_id": "bias-1", "agent_type": "bias_agent"},
        ) as agent_span:
            resolved = langfuse_service.trace_agent_execution(
                execution_id="exec-1",
                agent_type="bias_agent",
                agent_id="bias-1",
                pipeline_id="pipe-1",
                user_id="user-1",
            )

    assert resolved is agent_span


def test_tool_and_llm_calls_attach_under_agent_span(monkeypatch):
    client = MockLangfuseClient()
    monkeypatch.setattr(langfuse_service, "get_langfuse_client", lambda: client)

    trace = langfuse_service.start_or_resume_trace(
        name="pipeline_execution",
        session_id="exec-2",
        user_id="user-1",
        metadata={"execution_id": "exec-2"},
    )

    with langfuse_service.activate_observation(trace, as_trace=True):
        with langfuse_service.span_context(
            name="agent:strategy_agent",
            parent=trace,
            metadata={"agent_id": "strategy-1", "agent_type": "strategy_agent"},
        ) as agent_span:
            langfuse_service.trace_llm_call(
                trace=agent_span,
                model="gpt-4o",
                prompt="prompt",
                response="response",
                tokens_used={"total_tokens": 10},
                cost=0.12,
            )
            langfuse_service.trace_tool_call(
                trace=agent_span,
                tool_name="rsi_calculator",
                arguments={"period": 14},
                output="42",
            )

    raw_agent_span = agent_span.raw
    assert raw_agent_span.generations[0]["name"] == "llm_call"
    assert raw_agent_span.spans[0].name == "tool:rsi_calculator"
    assert raw_agent_span.spans[0].generations[0]["name"] == "tool_rsi_calculator"
    assert client.scores[0]["trace_id"] == trace.trace_id
