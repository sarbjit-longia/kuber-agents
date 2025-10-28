"""
CrewAI Flow Integration

Provides advanced pipeline orchestration using CrewAI Flows.
This enables complex agent coordination, conditional branching, and state management.

CrewAI Flows are used for:
- Complex multi-agent coordination
- Conditional execution paths
- State persistence between agents
- Advanced error handling
"""
import structlog
from typing import Dict, Any, Optional
from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel

from app.schemas.pipeline_state import PipelineState
from app.agents import get_registry

logger = structlog.get_logger()


class TradingPipelineFlow(Flow):
    """
    CrewAI Flow for orchestrating trading pipeline agents.
    
    This provides advanced orchestration capabilities beyond simple sequential execution:
    - Conditional branching based on agent outputs
    - Parallel agent execution where possible
    - State management and checkpointing
    - Error recovery and retries
    
    Flow Steps:
    1. check_trigger - Verify trigger conditions
    2. fetch_market_data - Get market data
    3. analyze_bias - Multi-timeframe analysis (optional, if configured)
    4. generate_strategy - Create trade plan (optional, if configured)
    5. assess_risk - Validate and size position
    6. execute_trade - Place order (if approved)
    7. report - Generate execution report (optional)
    
    Usage:
        flow = TradingPipelineFlow(pipeline_config)
        result = await flow.kickoff()
    """
    
    def __init__(self, pipeline_config: Dict[str, Any], initial_state: PipelineState):
        """
        Initialize the flow.
        
        Args:
            pipeline_config: Pipeline configuration with nodes and edges
            initial_state: Initial pipeline state
        """
        super().__init__()
        self.pipeline_config = pipeline_config
        self.state_data = initial_state
        self.registry = get_registry()
        self.logger = logger.bind(
            pipeline_id=str(initial_state.pipeline_id),
            execution_id=str(initial_state.execution_id)
        )
    
    @start()
    def check_trigger(self):
        """
        Step 1: Check if trigger conditions are met.
        
        Returns:
            Updated state with trigger status
        """
        self.logger.info("flow_step_check_trigger")
        
        trigger_node = self._find_node_by_type("time_trigger")
        if not trigger_node:
            # No trigger configured - proceed
            self.state_data.trigger_met = True
            self.state_data.trigger_reason = "No trigger configured"
            return self.state_data
        
        # Execute trigger agent
        agent = self.registry.create_agent_instance(
            agent_type=trigger_node["agent_type"],
            agent_id=trigger_node["id"],
            config=trigger_node.get("config", {})
        )
        
        try:
            self.state_data = agent.process(self.state_data)
            return self.state_data
        except Exception as e:
            self.logger.error("trigger_check_failed", error=str(e))
            self.state_data.errors.append(f"Trigger check failed: {str(e)}")
            raise
    
    @listen(check_trigger)
    def fetch_market_data(self, state: PipelineState):
        """
        Step 2: Fetch market data if trigger was met.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Updated state with market data
        """
        if not state.trigger_met:
            self.logger.info("skipping_market_data_fetch", reason="trigger_not_met")
            return state
        
        self.logger.info("flow_step_fetch_market_data")
        
        data_node = self._find_node_by_type("market_data_agent")
        if not data_node:
            self.logger.warning("no_market_data_agent_configured")
            return state
        
        # Execute market data agent
        agent = self.registry.create_agent_instance(
            agent_type=data_node["agent_type"],
            agent_id=data_node["id"],
            config=data_node.get("config", {})
        )
        
        self.state_data = agent.process(state)
        return self.state_data
    
    @listen(fetch_market_data)
    def analyze_bias(self, state: PipelineState):
        """
        Step 3: Analyze market bias if configured.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Updated state with bias analysis
        """
        if not state.trigger_met or not state.market_data:
            self.logger.info("skipping_bias_analysis")
            return state
        
        self.logger.info("flow_step_analyze_bias")
        
        bias_node = self._find_node_by_type("bias_agent")
        if not bias_node:
            self.logger.info("no_bias_agent_configured")
            return state
        
        # Execute bias agent (CrewAI-powered)
        agent = self.registry.create_agent_instance(
            agent_type=bias_node["agent_type"],
            agent_id=bias_node["id"],
            config=bias_node.get("config", {})
        )
        
        self.state_data = agent.process(state)
        return self.state_data
    
    @listen(analyze_bias)
    def generate_strategy(self, state: PipelineState):
        """
        Step 4: Generate trading strategy if configured.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Updated state with strategy
        """
        if not state.trigger_met or not state.market_data:
            self.logger.info("skipping_strategy_generation")
            return state
        
        self.logger.info("flow_step_generate_strategy")
        
        strategy_node = self._find_node_by_type("strategy_agent")
        if not strategy_node:
            self.logger.info("no_strategy_agent_configured")
            return state
        
        # Execute strategy agent (CrewAI-powered)
        agent = self.registry.create_agent_instance(
            agent_type=strategy_node["agent_type"],
            agent_id=strategy_node["id"],
            config=strategy_node.get("config", {})
        )
        
        self.state_data = agent.process(state)
        return self.state_data
    
    @listen(generate_strategy)
    def assess_risk(self, state: PipelineState):
        """
        Step 5: Assess risk and validate trade.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Updated state with risk assessment
        """
        if not state.trigger_met or not state.strategy:
            self.logger.info("skipping_risk_assessment")
            return state
        
        self.logger.info("flow_step_assess_risk")
        
        risk_node = self._find_node_by_type("risk_manager_agent")
        if not risk_node:
            self.logger.warning("no_risk_manager_configured")
            return state
        
        # Execute risk manager agent
        agent = self.registry.create_agent_instance(
            agent_type=risk_node["agent_type"],
            agent_id=risk_node["id"],
            config=risk_node.get("config", {})
        )
        
        self.state_data = agent.process(state)
        return self.state_data
    
    @listen(assess_risk)
    def execute_trade(self, state: PipelineState):
        """
        Step 6: Execute trade if approved by risk manager.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Updated state with execution results
        """
        if not state.trigger_met or not state.risk_assessment:
            self.logger.info("skipping_trade_execution")
            return state
        
        if not state.risk_assessment.approved:
            self.logger.info("trade_not_approved", reason=state.risk_assessment.reasoning)
            return state
        
        self.logger.info("flow_step_execute_trade")
        
        trade_node = self._find_node_by_type("trade_manager_agent")
        if not trade_node:
            self.logger.warning("no_trade_manager_configured")
            return state
        
        # Execute trade manager agent
        agent = self.registry.create_agent_instance(
            agent_type=trade_node["agent_type"],
            agent_id=trade_node["id"],
            config=trade_node.get("config", {})
        )
        
        self.state_data = agent.process(state)
        return self.state_data
    
    def _find_node_by_type(self, agent_type: str) -> Optional[Dict[str, Any]]:
        """
        Find a node in the pipeline config by agent type.
        
        Args:
            agent_type: Agent type to find
            
        Returns:
            Node config or None if not found
        """
        nodes = self.pipeline_config.get("nodes", [])
        for node in nodes:
            if node.get("agent_type") == agent_type:
                return node
        return None


def create_flow_from_pipeline(pipeline_config: Dict[str, Any], initial_state: PipelineState) -> TradingPipelineFlow:
    """
    Factory function to create a flow from pipeline configuration.
    
    Args:
        pipeline_config: Pipeline configuration
        initial_state: Initial state
        
    Returns:
        Configured TradingPipelineFlow instance
    """
    flow = TradingPipelineFlow(pipeline_config, initial_state)
    return flow

