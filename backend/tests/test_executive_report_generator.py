from types import SimpleNamespace

from app.services.executive_report_generator import ExecutiveReportGenerator


def test_extract_response_text_handles_none_content():
    generator = ExecutiveReportGenerator()
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
    )

    assert generator._extract_response_text(response) == ""


def test_generate_summary_falls_back_when_provider_returns_no_content(monkeypatch):
    generator = ExecutiveReportGenerator()

    async def fake_create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))],
            usage=SimpleNamespace(total_tokens=0, prompt_tokens=0, completion_tokens=0),
        )

    monkeypatch.setattr(
        generator,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )

    result = __import__("asyncio").run(
        generator.generate_executive_summary(
            {
                "id": "exec-1",
                "pipeline": "Test Pipeline",
                "symbol": "AAPL",
                "mode": "paper",
                "strategy": {"action": "BUY", "confidence": 0.74},
                "risk_assessment": {"risk_level": "medium"},
                "trade_execution": {"status": "submitted"},
            }
        )
    )

    assert result["executive_summary"] != "Failed to generate executive summary"
    assert "AAPL" in result["executive_summary"]
