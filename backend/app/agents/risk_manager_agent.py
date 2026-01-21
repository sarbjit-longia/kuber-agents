"""
Risk Manager Agent

Instruction-driven risk management and position sizing using LLM.
Queries broker for account state and calculates safe position sizes.
"""
from typing import Dict, Any
from datetime import datetime

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema, RiskAssessment
from app.config import settings


class RiskManagerAgent(BaseAgent):
    """
    Instruction-driven risk management and position sizing agent.
    
    Uses LLM to interpret natural language risk rules and calculate safe position sizes.
    
    The agent:
    - Queries broker for account balance and positions
    - Interprets user's risk instructions
    - Validates trade against risk rules
    - Calculates position size (shares/contracts)
    - Considers market volatility and existing exposure
    
    Example instructions:
        "Keep 60% cash on side, risk max 1% loss per trade, minimum 2:1 risk/reward,
         factor in today's volatility. Never exceed 10% of account in single position."
        
    Strategy Agent provides: Entry, Stop Loss, Take Profit
    Risk Manager provides: Position Size (shares/contracts)
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        from app.services.model_registry import model_registry
        from app.database import SessionLocal
        
        db = SessionLocal()
        try:
            model_choices = model_registry.get_model_choices_for_schema(db)
        finally:
            db.close()
        
        return AgentMetadata(
            agent_type="risk_manager_agent",
            name="Risk Manager Agent",
            description="Instruction-driven risk management and position sizing. Interprets your risk rules, queries broker for account state, and calculates safe position sizes.",
            category="risk",
            version="2.0.0",
            icon="shield",
            pricing_rate=0.10,
            is_free=False,
            requires_timeframes=[],
            requires_market_data=False,
            requires_position=False,
            supported_tools=["alpaca_broker", "oanda_broker", "tradier_broker", "webhook_notifier", "email_notifier"],
            config_schema=AgentConfigSchema(
                type="object",
                title="Risk Manager Configuration",
                description="Configure risk management via natural language instructions",
                properties={
                    "instructions": {
                        "type": "string",
                        "title": "Risk Management Instructions",
                        "description": "Natural language risk rules. Example: 'Keep 60% cash reserve, risk max 1% per trade, minimum 2:1 R/R, factor in volatility'. NOTE: Attach a broker tool (Alpaca/Oanda/Tradier) below to query your account balance automatically.",
                        "default": "Risk maximum 1% of account per trade. Maintain minimum 2:1 risk/reward ratio. Keep 50% cash reserve. Factor in market volatility when sizing positions. Reject trades if daily loss exceeds 3%."
                    },
                    "model": {
                        "type": "string",
                        "title": "AI Model",
                        "description": "LLM model for risk analysis",
                        "enum": model_choices,
                        "default": model_choices[0] if model_choices else "gpt-4"
                    }
                },
                required=["instructions"]
            ),
            can_initiate_trades=False,
            can_close_positions=False
        )
    
    def process(self, state: PipelineState) -> PipelineState:
        """
        Validate and size trade using LLM-based risk analysis.
        
        Args:
            state: Current pipeline state with strategy
            
        Returns:
            Updated pipeline state with risk assessment and position size
            
        Raises:
            AgentProcessingError: If risk assessment fails
        """
        from crewai import Agent, Task, Crew
        from app.services.langfuse_service import trace_agent_execution
        from app.services.model_registry import model_registry
        from app.database import SessionLocal
        
        self.log(state, "🛡️ Performing instruction-driven risk assessment")
        
        # If strategy is missing, do NOT throw InsufficientDataError (it causes Celery retries and
        # creates confusing RUNNING/PENDING loops). Instead, reject the trade gracefully so the
        # execution can complete and the UI shows a clear reason.
        if not state.strategy:
            state.risk_assessment = RiskAssessment(
                approved=False,
                risk_score=0.0,
                position_size=0.0,
                max_loss_amount=0.0,
                risk_reward_ratio=0.0,
                warnings=["Strategy was not generated (LLM/tooling returned empty output)."],
                reasoning="Risk assessment skipped because no strategy is available.",
            )
            self.log(state, "⚠️ No strategy available. Rejecting trade (risk assessment skipped).")
            self.record_report(
                state,
                title="Risk Assessment Skipped",
                summary="No strategy output available — trade rejected",
                status="rejected",
                metrics={
                    "approved": False,
                    "position_size": 0.0,
                    "risk_score": 0.0,
                },
                data={"reasoning": state.risk_assessment.reasoning},
            )
            return state
        
        strategy = state.strategy
        
        # If strategy is HOLD, approve with zero position
        if strategy.action == "HOLD":
            state.risk_assessment = RiskAssessment(
                approved=True,
                risk_score=0.0,
                position_size=0.0,
                max_loss_amount=0.0,
                risk_reward_ratio=0.0,
                warnings=[],
                reasoning="No trade proposed (HOLD signal)"
            )
            self.log(state, "✓ Risk assessment: HOLD signal approved")
            self.record_report(
                state,
                title="Risk review (HOLD)",
                summary="No position opened because strategy advised HOLD",
                data={"reasoning": "Strategy returned HOLD"},
            )
            return state
        
        try:
            # Get instructions
            instructions = self.config.get("instructions", "").strip()
            if not instructions:
                instructions = self.metadata.config_schema.properties["instructions"]["default"]
            
            model_id = self.config.get("model", "gpt-4")
            
            # Create Langfuse trace
            trace = trace_agent_execution(
                execution_id=str(state.execution_id),
                agent_type=self.metadata.agent_type,
                agent_id=self.agent_id,
                pipeline_id=str(state.pipeline_id),
                user_id=str(state.user_id),
            )
            
            # Get broker account info
            broker_info = self._get_broker_account_info(state)
            
            # Prepare context for LLM
            context = self._prepare_risk_context(state, broker_info)
            
            # Create CrewAI agent
            risk_analyst = Agent(
                role="Risk Manager",
                goal=f"Analyze the proposed trade and determine safe position size following these rules: {instructions}",
                backstory="""You are an expert risk manager responsible for protecting capital and ensuring
                        trades are properly sized according to the user's risk rules.""",
                verbose=False,
                allow_delegation=False,
                llm=model_id
            )
            
            # Create task
            task = Task(
                description=f"""
                Analyze this trade proposal and make a risk decision:
                
                {context}
                
                Risk Management Instructions:
                {instructions}
                
                You MUST provide your response in this EXACT format:
                APPROVED: Yes/No
                POSITION_SIZE: <number of shares/contracts>
                RISK_SCORE: <0.0 to 1.0>
                MAX_LOSS: <dollar amount>
                WARNINGS: <list any warnings, or "None">
                REASONING: <detailed explanation of your decision>
                
                Calculate position size based on:
                1. Account balance and cash requirements from instructions
                2. Maximum loss per trade (from instructions)
                3. Distance from entry to stop loss
                4. Risk/reward ratio requirements
                5. Existing positions and exposure
                
                Be conservative. Safety is paramount.
                """,
                agent=risk_analyst,
                expected_output="Risk decision with position size calculation"
            )
            
            # Execute
            crew = Crew(
                agents=[risk_analyst],
                tasks=[task],
                verbose=False
            )
            
            result = crew.kickoff()
            
            # Parse LLM response
            risk_decision = self._parse_risk_decision(str(result), strategy)
            
            # Create risk assessment
            state.risk_assessment = RiskAssessment(
                approved=risk_decision["approved"],
                risk_score=risk_decision["risk_score"],
                position_size=risk_decision["position_size"],
                max_loss_amount=risk_decision["max_loss"],
                risk_reward_ratio=risk_decision["rr_ratio"],
                warnings=risk_decision["warnings"],
                reasoning=risk_decision["reasoning"]
            )
            
            # Update strategy with position size
            strategy.position_size = risk_decision["position_size"]
            
            # Log result
            if risk_decision["approved"]:
                self.log(
                    state,
                    f"✓ Trade APPROVED: {risk_decision['position_size']:.0f} shares, "
                    f"Risk: ${risk_decision['max_loss']:.2f}, R/R: {risk_decision['rr_ratio']:.2f}:1"
                )
            else:
                self.log(
                    state,
                    f"✗ Trade REJECTED: {', '.join(risk_decision['warnings'])}"
                )
            
            # Build clean report data
            decision_status = "✅ APPROVED" if risk_decision['approved'] else "❌ REJECTED"
            warnings_text = "\n".join(f"• {w}" for w in risk_decision["warnings"]) if risk_decision["warnings"] else "None"
            
            report_data = {
                "Decision": decision_status,
                "Position Size": f"{risk_decision['position_size']:.0f} shares",
                "Risk Score": f"{risk_decision['risk_score']:.2f}",
                "Risk/Reward Ratio": f"{risk_decision['rr_ratio']:.2f}:1",
                "Maximum Loss": f"${risk_decision['max_loss']:.2f}",
            }
            
            if risk_decision["warnings"]:
                report_data["Warnings"] = warnings_text
            
            if broker_info:
                report_data["Account Info"] = f"Balance: ${broker_info.get('balance', 0):.2f} | Buying Power: ${broker_info.get('buying_power', 0):.2f}"
            
            report_data["Risk Analysis"] = risk_decision["reasoning"] or "Position sizing calculated based on account balance and risk parameters."
            
            self.record_report(
                state,
                title="Risk Assessment Completed",
                summary=f"{'APPROVED' if risk_decision['approved'] else 'REJECTED'} - Position Size: {risk_decision['position_size']:.0f} shares",
                status="completed" if risk_decision["approved"] else "rejected",
                data=report_data
            )
            
            # Calculate and track cost
            db = SessionLocal()
            try:
                cost = model_registry.calculate_agent_cost(
                    model_id=model_id,
                    db=db,
                    base_cost=0.02,
                    estimated_input_tokens=800,
                    estimated_output_tokens=300
                )
                self.track_cost(state, cost)
            finally:
                db.close()
            
            return state
            
        except Exception as e:
            self.logger.error(f"Risk assessment failed: {str(e)}", exc_info=True)
            raise AgentProcessingError(f"Risk assessment failed: {str(e)}")
    
    def _get_broker_account_info(self, state: PipelineState) -> Dict[str, Any]:
        """Query broker for account information."""
        broker_tool = self._get_broker_tool()
        
        if not broker_tool:
            self.log(state, "⚠️ No broker attached, using default account info")
            return {
                "account_balance": 10000,
                "buying_power": 10000,
                "cash": 10000,
                "equity": 10000,
                "positions": [],
                "source": "default"
            }
        
        try:
            from app.services.brokers.factory import broker_factory
            
            broker = broker_factory.from_tool_config(broker_tool)
            account_info = broker.get_account_info()
            
            self.log(state, f"📊 Broker account balance: ${account_info.get('equity', 0):.2f}")
            
            return {
                "account_balance": account_info.get("equity", 10000),
                "buying_power": account_info.get("buying_power", account_info.get("equity", 10000)),
                "cash": account_info.get("cash", account_info.get("equity", 10000)),
                "equity": account_info.get("equity", 10000),
                "positions": account_info.get("positions", []),
                "source": "broker"
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to get broker info: {e}")
            return {
                "account_balance": 10000,
                "buying_power": 10000,
                "cash": 10000,
                "equity": 10000,
                "positions": [],
                "source": "fallback"
            }
    
    def _get_broker_tool(self):
        """Get any attached broker tool from config."""
        # In the new architecture, tools are accessed via the tool registry
        # Risk Manager doesn't use attached tools anymore - it queries broker via API
        # This is kept for backward compatibility but returns None
        return None
    
    def _prepare_risk_context(self, state: PipelineState, broker_info: Dict[str, Any]) -> str:
        """Prepare context string for LLM."""
        strategy = state.strategy
        
        # Calculate risk/reward
        entry = strategy.entry_price
        stop = strategy.stop_loss
        target = strategy.take_profit
        
        # Validate price levels
        if entry is None or entry == 0:
            self.logger.error(f"Strategy missing entry_price: entry={entry}")
            raise ValueError("Strategy must provide a valid entry_price")
        
        if stop is None or target is None:
            self.logger.warning(
                f"Strategy missing price levels: entry={entry}, stop_loss={stop}, "
                f"take_profit={target}, action={strategy.action}"
            )
            # Cannot assess risk without stop loss and take profit
            raise ValueError(
                f"Strategy must provide stop_loss and take_profit for risk assessment. "
                f"Got: entry={entry}, stop_loss={stop}, take_profit={target}"
            )
        
        if strategy.action == "BUY":
            risk_per_share = abs(entry - stop)
            reward_per_share = abs(target - entry)
        else:
            risk_per_share = abs(stop - entry)
            reward_per_share = abs(entry - target)
        
        rr_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0
        
        context = f"""
PROPOSED TRADE:
- Symbol: {state.symbol}
- Action: {strategy.action}
- Entry Price: ${entry:.2f}
- Stop Loss: ${stop:.2f}
- Take Profit: ${target:.2f}
- Risk per share: ${risk_per_share:.2f}
- Reward per share: ${reward_per_share:.2f}
- Risk/Reward Ratio: {rr_ratio:.2f}:1
- Strategy Confidence: {strategy.confidence:.1%}

ACCOUNT STATUS:
- Total Equity: ${broker_info['equity']:.2f}
- Cash Available: ${broker_info['cash']:.2f}
- Buying Power: ${broker_info['buying_power']:.2f}
- Open Positions: {len(broker_info['positions'])}
- Data Source: {broker_info['source']}

MARKET CONDITIONS:
- Symbol: {state.symbol}
- Current Date: {datetime.now().strftime('%Y-%m-%d')}
"""
        
        if broker_info.get('positions'):
            context += "\nEXISTING POSITIONS:\n"
            for pos in broker_info['positions'][:5]:  # Show up to 5 positions
                context += f"- {pos.get('symbol', 'N/A')}: {pos.get('qty', 0)} shares\n"
        
        return context
    
    def _parse_risk_decision(self, llm_response: str, strategy) -> Dict[str, Any]:
        """Parse LLM response into structured risk decision."""
        import re
        
        # Default values
        decision = {
            "approved": False,
            "position_size": 0.0,
            "risk_score": 1.0,
            "max_loss": 0.0,
            "rr_ratio": 0.0,
            "warnings": [],
            "reasoning": self._clean_reasoning(llm_response)  # Clean reasoning by default
        }
        
        try:
            # Parse APPROVED
            approved_match = re.search(r'APPROVED:\s*(Yes|No)', llm_response, re.IGNORECASE)
            if approved_match:
                decision["approved"] = approved_match.group(1).lower() == "yes"
            
            # Parse POSITION_SIZE
            size_match = re.search(r'POSITION_SIZE:\s*(\d+\.?\d*)', llm_response)
            if size_match:
                decision["position_size"] = float(size_match.group(1))
            
            # Parse RISK_SCORE
            score_match = re.search(r'RISK_SCORE:\s*(\d+\.?\d*)', llm_response)
            if score_match:
                decision["risk_score"] = float(score_match.group(1))
            
            # Parse MAX_LOSS
            loss_match = re.search(r'MAX_LOSS:\s*\$?(\d+\.?\d*)', llm_response)
            if loss_match:
                decision["max_loss"] = float(loss_match.group(1))
            
            # Parse WARNINGS
            warnings_match = re.search(r'WARNINGS:\s*(.+?)(?=REASONING:|$)', llm_response, re.DOTALL)
            if warnings_match:
                warnings_text = warnings_match.group(1).strip()
                if warnings_text.lower() != "none":
                    decision["warnings"] = [w.strip() for w in warnings_text.split('\n') if w.strip()]
            
            # Parse REASONING
            reasoning_match = re.search(r'REASONING:\s*(.+)', llm_response, re.DOTALL)
            if reasoning_match:
                decision["reasoning"] = self._clean_reasoning(reasoning_match.group(1).strip())  # Clean extracted reasoning
            
            # Calculate R/R ratio from strategy
            entry = strategy.entry_price
            stop = strategy.stop_loss
            target = strategy.take_profit
            
            if strategy.action == "BUY":
                risk = abs(entry - stop)
                reward = abs(target - entry)
            else:
                risk = abs(stop - entry)
                reward = abs(entry - target)
            
            decision["rr_ratio"] = reward / risk if risk > 0 else 0
            
        except Exception as e:
            self.logger.warning(f"Error parsing risk decision: {e}")
            decision["warnings"].append(f"Parsing error: {str(e)}")
        
        return decision
    
    def _clean_reasoning(self, text: str) -> str:
        """Make reasoning safe and readable for end users."""
        import re
        if not text:
            return "Risk assessment completed based on position sizing rules and account limits."
        
        cleaned = text
        
        # Remove CrewAI tool-call artifacts (only very specific patterns)
        cleaned = re.sub(r"commentary\s+to=\w+\s+tool_code=\w+\s+json\s*\{[^}]+\}", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove code blocks with triple backticks
        cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
        
        # Remove ONLY obvious standalone JSON objects
        cleaned = re.sub(r"^\s*\{[\s\S]*?\}\s*$", "", cleaned, flags=re.MULTILINE)
        
        # Remove HTML/XML tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        
        # Collapse multiple whitespaces and newlines
        cleaned = re.sub(r"\n\s*\n", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = cleaned.strip()
        
        # If still too long, truncate smartly
        if len(cleaned) > 800:
            truncate_at = cleaned.rfind(".", 0, 800)
            if truncate_at > 400:
                cleaned = cleaned[:truncate_at + 1] + "\n\n[Analysis truncated]"
            else:
                cleaned = cleaned[:800] + "..."
        
        # If cleaned is empty or too short, return default
        if len(cleaned.strip()) < 20:
            return "Position sizing calculated based on account balance, risk tolerance, and trade parameters."
        
        return cleaned
