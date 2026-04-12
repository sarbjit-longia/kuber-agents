from __future__ import annotations

import pytest

from app.utils.providers.dataplane_provider import DataPlaneProvider


@pytest.mark.asyncio
async def test_dataplane_provider_normalizes_numeric_candle_resolution(monkeypatch):
    provider = DataPlaneProvider("http://data-plane:8000")
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"candles": []}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            return DummyResponse()

    monkeypatch.setattr("app.utils.providers.dataplane_provider.httpx.AsyncClient", DummyClient)

    await provider.fetch_candles("AAPL", "60", lookback_days=2)

    assert captured["params"]["timeframe"] == "1h"


@pytest.mark.asyncio
async def test_dataplane_provider_normalizes_numeric_indicator_resolution(monkeypatch):
    provider = DataPlaneProvider("http://data-plane:8000")
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"indicators": {"ema": {"value": 123.4}}, "timestamp": "2026-04-01T14:20:00+00:00"}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            return DummyResponse()

    monkeypatch.setattr("app.utils.providers.dataplane_provider.httpx.AsyncClient", DummyClient)

    result = await provider.fetch_indicator("AAPL", "ema", resolution="240", timeperiod=50)

    assert captured["params"]["timeframe"] == "4h"
    assert result["timeframe"] == "4h"
