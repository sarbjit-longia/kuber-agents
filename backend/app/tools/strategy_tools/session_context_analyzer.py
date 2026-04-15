"""
Session context analyzer for ICT time-and-price and killzone workflows.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


NY_TZ = ZoneInfo("America/New_York")


class SessionContextAnalyzer:
    """Derive trading session and killzone context from candle timestamps."""

    def __init__(self, timeframe: str):
        self.timeframe = timeframe

    async def analyze(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not candles:
            return self._empty_result()

        est_candles: List[tuple[datetime, Dict[str, Any]]] = []
        for candle in candles:
            dt = self._parse_timestamp(candle.get("timestamp"))
            if dt is None:
                continue
            est_candles.append((dt.astimezone(NY_TZ), candle))

        if not est_candles:
            return self._empty_result()

        current_dt, _ = est_candles[-1]
        current_session = self._session_name(current_dt.timetz().replace(tzinfo=None))
        current_killzone = self._killzone_name(current_dt.timetz().replace(tzinfo=None))

        midnight_open = self._find_open_at_or_after(est_candles, current_dt.date(), time(0, 0))
        true_session_open = self._find_open_at_or_after(est_candles, current_dt.date(), time(7, 30))

        asia_high_low = self._range_between(
            est_candles,
            start_dt=datetime.combine(current_dt.date() - timedelta(days=1), time(18, 0), tzinfo=NY_TZ),
            end_dt=datetime.combine(current_dt.date(), time(0, 0), tzinfo=NY_TZ),
        )
        london_high_low = self._range_between(
            est_candles,
            start_dt=datetime.combine(current_dt.date(), time(0, 0), tzinfo=NY_TZ),
            end_dt=datetime.combine(current_dt.date(), time(6, 0), tzinfo=NY_TZ),
        )
        premarket_high_low = self._range_between(
            est_candles,
            start_dt=datetime.combine(current_dt.date(), time(6, 0), tzinfo=NY_TZ),
            end_dt=datetime.combine(current_dt.date(), time(7, 30), tzinfo=NY_TZ),
        )

        return {
            "timeframe": self.timeframe,
            "current_est_time": current_dt.isoformat(),
            "current_session": current_session,
            "current_killzone": current_killzone,
            "midnight_open": midnight_open,
            "true_session_open": true_session_open,
            "asia_session": asia_high_low,
            "london_session": london_high_low,
            "premarket_session": premarket_high_low,
        }

    def _parse_timestamp(self, raw: Any) -> Optional[datetime]:
        if not raw:
            return None
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=ZoneInfo("UTC"))
        text = str(raw).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("UTC"))

    def _find_open_at_or_after(
        self,
        est_candles: List[tuple[datetime, Dict[str, Any]]],
        session_date,
        target_time: time,
    ) -> Optional[float]:
        for dt, candle in est_candles:
            if dt.date() == session_date and dt.time() >= target_time:
                return float(candle["open"])
        return None

    def _range_between(
        self,
        est_candles: List[tuple[datetime, Dict[str, Any]]],
        *,
        start_dt: datetime,
        end_dt: datetime,
    ) -> Dict[str, Optional[float]]:
        session = [candle for dt, candle in est_candles if start_dt <= dt < end_dt]
        if not session:
            return {"high": None, "low": None}
        return {
            "high": max(float(c["high"]) for c in session),
            "low": min(float(c["low"]) for c in session),
        }

    def _session_name(self, current_time: time) -> str:
        if time(18, 0) <= current_time or current_time < time(0, 0):
            return "asia"
        if time(0, 0) <= current_time < time(6, 0):
            return "london"
        if time(6, 0) <= current_time < time(7, 30):
            return "pre_market"
        if time(7, 30) <= current_time < time(12, 0):
            return "ny_am"
        if time(12, 0) <= current_time < time(16, 0):
            return "ny_pm"
        return "ny_close"

    def _killzone_name(self, current_time: time) -> Optional[str]:
        windows = [
            ("london_killzone", time(1, 30), time(4, 30)),
            ("ny_killzone", time(7, 30), time(10, 30)),
            ("ny_am_focus", time(9, 0), time(10, 30)),
            ("silver_bullet_am", time(10, 0), time(11, 0)),
            ("silver_bullet_pm", time(14, 0), time(15, 0)),
        ]
        for name, start, end in windows:
            if start <= current_time < end:
                return name
        return None

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "current_est_time": None,
            "current_session": None,
            "current_killzone": None,
            "midnight_open": None,
            "true_session_open": None,
            "asia_session": {"high": None, "low": None},
            "london_session": {"high": None, "low": None},
            "premarket_session": {"high": None, "low": None},
        }
