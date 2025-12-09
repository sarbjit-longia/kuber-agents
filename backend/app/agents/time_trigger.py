"""
Time-Based Trigger Agent (tool-driven)

This agent delegates trigger evaluation to attached trigger tools
(e.g., TimeTriggerTool) instead of hardcoding time logic.
"""
from typing import Dict, Any

from app.agents.base import BaseAgent, TriggerNotMetException, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema


class TimeTriggerAgent(BaseAgent):
    """Generic trigger agent; relies on attached trigger tools."""
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="time_trigger",
            name="Time-Based Trigger",
            description="Triggers pipeline execution using attached trigger tools (e.g., Time Trigger). Free to use.",
            category="trigger",
            version="1.0.0",
            icon="schedule",
            pricing_rate=0.0,
            is_free=True,
            requires_timeframes=[],
            requires_market_data=False,
            requires_position=False,
            supported_tools=["time_trigger"],
            config_schema=AgentConfigSchema(
                type="object",
                title="Trigger Agent Configuration",
                description="Attach a trigger tool (e.g., Time Trigger).",
                properties={},
                required=[]
            ),
            can_initiate_trades=False,
            can_close_positions=False
        )
    
    def process(self, state: PipelineState) -> PipelineState:
        """
        Check trigger condition using attached trigger tools.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Updated pipeline state
            
        Raises:
            TriggerNotMetException: If trigger condition not met
            AgentProcessingError: If no trigger tool attached
        """
        self.log(state, "Evaluating trigger via attached tools")
        
        tools = self._load_tools()
        trigger_tool = tools.get("time_trigger")
        
        if not trigger_tool:
            msg = "Trigger Agent requires a trigger tool (e.g., Time Trigger) to be attached."
            self.log(state, msg, level="error")
            raise AgentProcessingError(msg)
        
        result = trigger_tool.execute()
        trigger_met = bool(result.get("trigger_met"))
        reason = result.get("reason", "")
        
        if not trigger_met:
            self.record_report(
                state,
                title="Trigger not met",
                summary=reason or "Trigger conditions not met",
                status="skipped",
                data=result,
            )
            raise TriggerNotMetException(reason or "Trigger conditions not met")
        
        state.trigger_met = True
        state.trigger_reason = reason or "Trigger met"
        
        self.log(state, f"✓ Trigger met - proceeding with pipeline execution")
        self.record_report(
            state,
            title="Trigger fired",
            summary=state.trigger_reason,
            data=result,
        )
        
        return state

