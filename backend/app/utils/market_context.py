"""
Market-Wide Risk Context (TP-024)

Fetches VIX and SPY (or ES/NQ for futures) data from the Data Plane API
to support deterministic market-wide risk controls during position monitoring.

Used by TradeManagerAgent._evaluate_exit_conditions to replace the three
commented-out TODO blocks for VIX spike, SPY crash, and news detection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

_DATA_PLANE_URL: str = getattr(settings, "DATA_PLANE_URL", "http://data-plane:8000")

# How much of SPY's daily range constitutes a "crash"
SPY_CRASH_THRESHOLD_PCT: float = -3.0  # -3% intraday

# Default VIX danger level when user doesn't specify
DEFAULT_VIX_DANGER: float = 30.0


@dataclass
class MarketSnapshot:
    """Point-in-time market-wide metrics."""
    vix: Optional[float] = None           # CBOE VIX
    spy_change_pct: Optional[float] = None  # SPY % change from prior close
    spy_price: Optional[float] = None
    error: Optional[str] = None           # Set if data fetch failed


async def _get_quote(symbol: str, client: httpx.AsyncClient) -> Optional[dict]:
    """Fetch a single quote from the Data Plane."""
    try:
        resp = await client.get(
            f"{_DATA_PLANE_URL}/api/v1/data/quote/{symbol}",
            timeout=5.0,
        )
        if resp.is_success:
            return resp.json()
    except Exception as exc:
        logger.debug("market_context_quote_failed", symbol=symbol, error=str(exc))
    return None


async def get_market_snapshot() -> MarketSnapshot:
    """
    Return a MarketSnapshot with VIX and SPY data.

    Returns a snapshot with None values (plus error message) if the data
    plane is unreachable — callers must treat None as "data unavailable"
    and NOT trigger exits based on missing data.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            import asyncio
            vix_data, spy_data = await asyncio.gather(
                _get_quote("VIX", client),
                _get_quote("SPY", client),
                return_exceptions=True,
            )

        snap = MarketSnapshot()

        if isinstance(vix_data, dict):
            snap.vix = vix_data.get("price") or vix_data.get("last") or vix_data.get("current_price")

        if isinstance(spy_data, dict):
            price     = spy_data.get("price") or spy_data.get("last") or spy_data.get("current_price")
            prev_close = spy_data.get("prev_close") or spy_data.get("previous_close")
            snap.spy_price = price
            if price and prev_close and float(prev_close) > 0:
                snap.spy_change_pct = (float(price) - float(prev_close)) / float(prev_close) * 100

        return snap

    except Exception as exc:
        logger.warning("market_context_fetch_failed", error=str(exc))
        return MarketSnapshot(error=str(exc))


def check_vix_spike(snap: MarketSnapshot, threshold: float) -> tuple[bool, str]:
    """
    Return (True, reason) if VIX exceeds threshold; (False, "") otherwise.
    If VIX data is unavailable, returns (False, "") — never false-positive exits.
    """
    if snap.vix is None:
        return False, ""
    if snap.vix > threshold:
        return True, f"VIX spike: {snap.vix:.1f} > {threshold:.0f} (market fear elevated)"
    return False, ""


def check_spy_crash(snap: MarketSnapshot, threshold_pct: float = SPY_CRASH_THRESHOLD_PCT) -> tuple[bool, str]:
    """
    Return (True, reason) if SPY is down more than threshold_pct today.
    If SPY data is unavailable, returns (False, "") — never false-positive exits.
    """
    if snap.spy_change_pct is None:
        return False, ""
    if snap.spy_change_pct < threshold_pct:
        return True, f"Market crash: SPY {snap.spy_change_pct:+.1f}% (threshold: {threshold_pct:+.0f}%)"
    return False, ""
