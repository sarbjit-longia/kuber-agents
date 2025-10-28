"""
Time-Based Trigger Agent

A FREE agent that triggers pipeline execution at regular intervals.
"""
from datetime import datetime, timedelta
from typing import Dict, Any

from app.agents.base import BaseAgent, TriggerNotMetException
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema


class TimeTriggerAgent(BaseAgent):
    """
    Time-based trigger that executes at regular intervals.
    
    This is a FREE agent (no LLM calls, no costs).
    
    Configuration:
        - interval: Time interval (e.g., "5m", "1h", "1d")
        - start_time: Optional start time (HH:MM format)
        - end_time: Optional end time (HH:MM format)
        - days_of_week: Optional list of days (0=Monday, 6=Sunday)
    
    Example config:
        {
            "interval": "5m",
            "start_time": "09:30",
            "end_time": "16:00",
            "days_of_week": [0, 1, 2, 3, 4]  # Monday-Friday
        }
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="time_trigger",
            name="Time-Based Trigger",
            description="Triggers pipeline execution at regular time intervals. Free to use.",
            category="trigger",
            version="1.0.0",
            icon="schedule",
            pricing_rate=0.0,
            is_free=True,
            requires_timeframes=[],
            requires_market_data=False,
            requires_position=False,
            config_schema=AgentConfigSchema(
                type="object",
                title="Time Trigger Configuration",
                description="Configure when the pipeline should execute",
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
                        "title": "Start Time",
                        "description": "Start time in HH:MM format (optional, e.g., '09:30')",
                        "pattern": "^([0-1][0-9]|2[0-3]):[0-5][0-9]$"
                    },
                    "end_time": {
                        "type": "string",
                        "title": "End Time",
                        "description": "End time in HH:MM format (optional, e.g., '16:00')",
                        "pattern": "^([0-1][0-9]|2[0-3]):[0-5][0-9]$"
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
            ),
            can_initiate_trades=False,
            can_close_positions=False
        )
    
    def process(self, state: PipelineState) -> PipelineState:
        """
        Check if the trigger condition is met based on time.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Updated pipeline state
            
        Raises:
            TriggerNotMetException: If trigger condition not met
        """
        self.log(state, "Evaluating time-based trigger")
        
        now = datetime.utcnow()
        
        # Check day of week constraint
        days_of_week = self.config.get("days_of_week", [])
        if days_of_week and now.weekday() not in days_of_week:
            self.log(state, f"Not running today (day {now.weekday()})")
            raise TriggerNotMetException(
                f"Trigger not met: Today is day {now.weekday()}, "
                f"only running on days {days_of_week}"
            )
        
        # Check start/end time constraints
        start_time = self.config.get("start_time")
        end_time = self.config.get("end_time")
        
        if start_time or end_time:
            current_time = now.strftime("%H:%M")
            
            if start_time and current_time < start_time:
                self.log(state, f"Before start time ({start_time})")
                raise TriggerNotMetException(
                    f"Trigger not met: Current time {current_time} is before start time {start_time}"
                )
            
            if end_time and current_time > end_time:
                self.log(state, f"After end time ({end_time})")
                raise TriggerNotMetException(
                    f"Trigger not met: Current time {current_time} is after end time {end_time}"
                )
        
        # If we get here, trigger is met
        interval = self.config["interval"]
        state.trigger_met = True
        state.trigger_reason = f"Time trigger ({interval} interval) condition met"
        
        self.log(state, f"✓ Trigger met - proceeding with pipeline execution")
        
        return state
    
    def _parse_interval(self, interval: str) -> timedelta:
        """
        Parse interval string to timedelta.
        
        Args:
            interval: Interval string (e.g., "5m", "1h", "1d")
            
        Returns:
            timedelta object
        """
        unit = interval[-1]
        value = int(interval[:-1])
        
        if unit == 'm':
            return timedelta(minutes=value)
        elif unit == 'h':
            return timedelta(hours=value)
        elif unit == 'd':
            return timedelta(days=value)
        else:
            raise ValueError(f"Invalid interval format: {interval}")

