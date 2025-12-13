"""
Pipeline Validator

Validates pipeline configuration before execution or activation.
Ensures all required tools are attached and configuration is valid.
"""
import structlog
from typing import Dict, Any, List, Tuple
from app.agents import get_registry

logger = structlog.get_logger()


class PipelineValidator:
    """
    Validates pipeline configuration.
    
    Ensures:
    - All agents have required tools attached
    - Agent configurations are valid
    - Pipeline structure is valid
    """
    
    def __init__(self):
        self.agent_registry = get_registry()
    
    def validate(self, pipeline_config: Dict[str, Any], trigger_mode: str = "periodic", scanner_id: str = None) -> Tuple[bool, List[str]]:
        """
        Validate a pipeline configuration.
        
        Args:
            pipeline_config: Pipeline config with nodes and edges
            trigger_mode: Pipeline trigger mode ('periodic' or 'signal')
            scanner_id: Scanner ID (required for signal-based pipelines)
            
        Returns:
            Tuple of (is_valid, list_of_errors)
            
        Example:
            validator = PipelineValidator()
            is_valid, errors = validator.validate(pipeline_config, trigger_mode='signal', scanner_id='...')
            if not is_valid:
                return {"error": errors}
        """
        errors = []
        
        nodes = pipeline_config.get("nodes", [])
        edges = pipeline_config.get("edges", [])
        
        # 1. Check for empty pipeline
        if not nodes:
            errors.append("Pipeline has no agents configured")
            return False, errors
        
        # 2. Validate each agent node
        for node in nodes:
            node_errors = self._validate_node(node)
            errors.extend(node_errors)
        
        # 3. Validate pipeline structure (basic checks)
        structure_errors = self._validate_structure(nodes, edges, trigger_mode, scanner_id)
        errors.extend(structure_errors)
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def _validate_node(self, node: Dict[str, Any]) -> List[str]:
        """Validate a single agent node."""
        errors = []
        
        agent_type = node.get("agent_type")
        node_id = node.get("id", "unknown")
        config = node.get("config", {})
        
        # Get agent metadata
        metadata = self.agent_registry.get_metadata(agent_type)
        if not metadata:
            errors.append(f"Agent '{node_id}': Unknown agent type '{agent_type}'")
            return errors
        
        # Check for required tools
        if metadata.supported_tools:
            attached_tools = config.get("tools", [])
            attached_tool_types = [t.get("tool_type") for t in attached_tools if t.get("enabled", True)]
            
            # Check if agent requires tools but none are attached
            required_tool_categories = metadata.supported_tools
            
            # Special case: check if any tool from required categories is attached
            has_required_tool = False
            for required_category in required_tool_categories:
                for attached_type in attached_tool_types:
                    # Check if attached tool matches required category
                    # e.g., "market_data" matches "market_data" from MarketDataTool
                    if required_category in attached_type or attached_type == required_category:
                        has_required_tool = True
                        break
                if has_required_tool:
                    break
            
            if not has_required_tool and required_tool_categories:
                # Only require tools for agents that truly need them
                # Trade Manager Agent needs broker tool
                if agent_type in ["trade_manager_agent"]:
                    tool_names = ", ".join(required_tool_categories)
                    errors.append(
                        f"Agent '{metadata.name}' requires a tool to be attached. "
                        f"Please attach one of: {tool_names}"
                    )
        
        # Check for required configuration fields (accounting for defaults)
        schema = metadata.config_schema
        if schema and schema.required:
            for field in schema.required:
                # Check if field exists in config
                has_value = field in config and config[field] is not None
                
                # Check if field has a default value in schema
                has_default = (
                    schema.properties and 
                    field in schema.properties and 
                    "default" in schema.properties[field]
                )
                
                # Only error if no value AND no default
                if not has_value and not has_default:
                    errors.append(
                        f"Agent '{metadata.name}': Missing required configuration field '{field}'"
                    )
        
        return errors
    
    def _validate_structure(self, nodes: List[Dict], edges: List[Dict], trigger_mode: str = "periodic", scanner_id: str = None) -> List[str]:
        """Validate pipeline structure based on trigger mode."""
        errors = []
        
        # Filter out tool nodes
        agent_nodes = [n for n in nodes if n.get("node_category") != "tool"]
        
        if len(agent_nodes) == 0:
            errors.append("Pipeline has no agents (only tools)")
            return errors
        
        # Validate trigger configuration based on mode
        if trigger_mode == "periodic":
            # Periodic pipelines require a Time Trigger agent
            has_trigger = any(n.get("agent_type") == "time_trigger" for n in agent_nodes)
            if not has_trigger:
                errors.append(
                    "Periodic pipelines must have a Time Trigger agent to schedule execution"
                )
        elif trigger_mode == "signal":
            # Signal-based pipelines require a scanner
            if not scanner_id:
                errors.append(
                    "Signal-based pipelines must have a scanner assigned. "
                    "Go to Pipeline Settings and select a scanner."
                )
        
        # Check for disconnected agents (if there are edges)
        if len(edges) > 0 and len(agent_nodes) > 1:
            node_ids = {n["id"] for n in agent_nodes}
            connected_nodes = set()
            
            for edge in edges:
                from_id = edge.get("from") or edge.get("source")
                to_id = edge.get("to") or edge.get("target")
                
                if from_id in node_ids:
                    connected_nodes.add(from_id)
                if to_id in node_ids:
                    connected_nodes.add(to_id)
            
            disconnected = node_ids - connected_nodes
            if len(disconnected) > 0 and len(connected_nodes) > 0:
                errors.append(
                    f"Pipeline has {len(disconnected)} disconnected agent(s). "
                    f"All agents must be connected."
                )
        
        return errors

