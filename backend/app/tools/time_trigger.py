"""
Time Trigger Tool

Provides time-based triggering as an attachable tool so the TimeTriggerAgent
remains generic. Evaluates local-time window and interval.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List

from app.tools.base import BaseTool, ToolError
from app.schemas.tool import ToolMetadata, ToolConfigSchema


class TimeTriggerTool(BaseTool):
    """
    Time-based trigger evaluation tool.
    """

    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            tool_type="time_trigger",
            name="Time Trigger",
            description="Evaluates time windows (start/end, days of week, interval) to decide if the trigger should fire.",
            category="trigger",
            version="1.0.0",
            icon="schedule",
            requires_credentials=False,
            config_schema=ToolConfigSchema(
                type="object",
                title="Time Trigger Configuration",
                description="Configure when the trigger should fire",
                properties={
                    "interval": {
                        "type": "string",
                        "title": "Interval",
                        "description": "How often to trigger (e.g., '5m', '15m', '1h', '4h', '1d')",
                        "default": "5m",
                        "enum": ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
                    },
                    "start_time": {
                        "type": "string",
                        "title": "Start Time (Your Local Time)",
                        "description": "Start time in HH:MM format (optional, e.g., '09:30')",
                        "pattern": "^([0-1][0-9]|2[0-3]):[0-5][0-9]$",
                        "format": "time",
                        "x-timezone": "local"
                    },
                    "end_time": {
                        "type": "string",
                        "title": "End Time (Your Local Time)",
                        "description": "End time in HH:MM format (optional, e.g., '16:00')",
                        "pattern": "^([0-1][0-9]|2[0-3]):[0-5][0-9]$",
                        "format": "time",
                        "x-timezone": "local"
                    },
                    "days_of_week": {
                        "type": "array",
                        "title": "Days of Week",
                        "description": "Days to run on (0=Monday, 6=Sunday). Empty = all days",
                        "items": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 6
                        }
                    }
                },
                required=["interval"]
            )
        )

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Evaluate whether the trigger should fire now.

        Returns:
            dict: { "trigger_met": bool, "reason": str }
        """
        now = datetime.utcnow()

        interval = self.config.get("interval", "5m")
        start_time = self.config.get("start_time")
        end_time = self.config.get("end_time")
        days_of_week: List[int] = self.config.get("days_of_week", [])

        # Day-of-week check
        weekday = now.weekday()
        if days_of_week and weekday not in days_of_week:
            return {"trigger_met": False, "reason": f"Today ({weekday}) not in allowed days {days_of_week}"}

        # Time window check
        if start_time or end_time:
            current_time = now.strftime("%H:%M")
            if start_time and current_time < start_time:
                return {"trigger_met": False, "reason": f"Current time {current_time} before start {start_time}"}
            if end_time and current_time > end_time:
                return {"trigger_met": False, "reason": f"Current time {current_time} after end {end_time}"}

        # Interval parsing (ensure valid format)
        self._parse_interval(interval)  # will raise if invalid

        return {
            "trigger_met": True,
            "reason": f"Time trigger ({interval}) condition met"
        }

    def _parse_interval(self, interval: str) -> timedelta:
        unit = interval[-1]
        value_str = interval[:-1]
        if not value_str.isdigit():
            raise ToolError(f"Invalid interval format: {interval}")
        value = int(value_str)
        if unit == 'm':
            return timedelta(minutes=value)
        if unit == 'h':
            return timedelta(hours=value)
        if unit == 'd':
            return timedelta(days=value)
        raise ToolError(f"Invalid interval format: {interval}")

