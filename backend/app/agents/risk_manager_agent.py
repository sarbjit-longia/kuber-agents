"""
Risk Manager Agent

Instruction-driven risk management and position sizing using LLM.
Queries broker for account state and calculates safe position sizes.
"""
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.agents.prompts import load_prompt
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema, RiskAssessment
from app.services.agent_runner import AgentRunner
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
                        "default": "gpt-4o" if "gpt-4o" in model_choices else (model_choices[0] if model_choices else "gpt-4o")
                    }
                },
                required=["instructions"]
            ),
            can_initiate_trades=False,
            can_close_positions=False
        )

    def __init__(self, agent_id: str, config: Dict[str, Any]):
        super().__init__(agent_id, config)
        self.runner = AgentRunner(
            model=self.config.get("model", settings.OPENAI_MODEL),
            temperature=0.2,
            timeout=45,
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
            
            model_id = self.config.get("model", "gpt-4o")
            
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
            broker_error = broker_info.get("error")
            if broker_error:
                reason = (
                    "Risk assessment blocked because broker account information could not be "
                    f"retrieved: {broker_error}"
                )
                state.risk_assessment = RiskAssessment(
                    approved=False,
                    risk_score=1.0,
                    position_size=0.0,
                    max_loss_amount=0.0,
                    risk_reward_ratio=0.0,
                    warnings=[reason],
                    reasoning=reason,
                )
                self.log(state, f"✗ {reason}")
                self.record_report(
                    state,
                    title="Risk Assessment Blocked",
                    summary="Broker account lookup failed — trade rejected",
                    status="rejected",
                    data={
                        "Decision": "❌ REJECTED",
                        "Broker Error": broker_error,
                        "Account Info": f"Source: {broker_info.get('source', 'unknown')}",
                        "Risk Analysis": reason,
                    },
                )
                return state

            # Prepare context for LLM
            context = self._prepare_risk_context(state, broker_info)
            
            system_prompt = load_prompt("risk_manager_system") + """

CORE PRINCIPLES:
1. You follow user's risk instructions EXACTLY - if they say "1% risk", use 1% not 2%
2. You do NOT add your own rules - if user doesn't mention RR ratio, don't enforce one
3. You calculate position size mathematically based on user's specifications
4. You approve trades that meet user's rules, reject those that don't

Your job is to EXECUTE the user's risk rules, not add your own "conservative" interpretations."""
            
            user_prompt = f"""
═══════════════════════════════════════════════════════════
USER'S RISK MANAGEMENT INSTRUCTIONS:
═══════════════════════════════════════════════════════════
{instructions}

═══════════════════════════════════════════════════════════
TRADE PROPOSAL TO EVALUATE:
═══════════════════════════════════════════════════════════
{context}

═══════════════════════════════════════════════════════════
YOUR TASK:
═══════════════════════════════════════════════════════════
Read the user's risk instructions above and execute them exactly.

Calculate position size using:
1. User's specified risk percentage (e.g., "1% risk" means use 1%, not 2%)
2. Distance from entry to stop loss (in dollars/pips)
3. Account balance
4. ONLY enforce risk rules the user mentioned (don't add your own restrictions)

Formula for position size:
- Risk Amount = Account Balance × Risk Percentage
- Position Size = Risk Amount ÷ Distance to Stop Loss

CRITICAL RULES:
- If the user does NOT specify a risk percentage, default to 2% of account balance.
- If the user says to "approve all trades", "don't worry about risk", or similar,
  you STILL MUST calculate a valid position size using the 2% default risk rule.
- POSITION_SIZE must ALWAYS be greater than 0 when APPROVED is Yes.
- A position size of 0 means the trade cannot be executed — never return 0 if approving.
- Always round position size to a whole number (no decimals).

BUYING POWER CONSTRAINT (MANDATORY — NEVER VIOLATE):
- Total position value = Position Size × Entry Price
- Total position value MUST NOT exceed Buying Power
- Maximum affordable shares = Buying Power ÷ Entry Price (rounded down)
- If the risk-based position size exceeds this, cap it at the maximum affordable shares
- Example: If risk-based size = 882 but Buying Power = $10,000 and Entry = $683.75,
  max affordable = floor(10000 / 683.75) = 14 shares. Use 14, NOT 882.

═══════════════════════════════════════════════════════════
OUTPUT FORMAT (CRITICAL):
═══════════════════════════════════════════════════════════
You MUST provide your response in this EXACT format:
APPROVED: Yes/No
POSITION_SIZE: <number of shares/contracts — MUST be > 0 if APPROVED is Yes>
RISK_SCORE: <0.0 to 1.0>
MAX_LOSS: <dollar amount>
WARNINGS: <list any warnings, or "None">
REASONING: <brief explanation of your calculation including the formula used>
                """
            
            result = self.runner.run(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                trace=trace,
                max_iterations=1,
            ).content
            
            # Parse LLM response — use LLM for approval decision + narrative only
            risk_decision = self._parse_risk_decision(str(result), strategy)
            llm_warnings = list(risk_decision["warnings"])

            if risk_decision["approved"] and risk_decision["position_size"] <= 0:
                reason = "Risk manager approved the trade but did not return a valid position size."
                risk_decision["approved"] = False
                risk_decision["warnings"].append(reason)
                risk_decision["reasoning"] = reason

            # HARD SAFETY CAP: position value must not exceed buying power
            # This prevents LLM hallucinations from causing absurd orders
            if (risk_decision["approved"]
                    and risk_decision["position_size"] > 0
                    and strategy.entry_price
                    and strategy.entry_price > 0):
                buying_power = broker_info.get("buying_power", broker_info.get("equity", 10000))
                total_position_value = risk_decision["position_size"] * strategy.entry_price
                max_affordable = int(buying_power / strategy.entry_price)
                
                if total_position_value > buying_power:
                    original_size = risk_decision["position_size"]
                    risk_decision["position_size"] = max(1, max_affordable)
                    risk_decision["warnings"].append(
                        f"Position size capped from {int(original_size)} to {int(risk_decision['position_size'])} shares "
                        f"(total value ${total_position_value:,.2f} exceeded buying power ${buying_power:,.2f})"
                    )
                    # Recalculate max loss with capped position size
                    if strategy.stop_loss is not None:
                        risk_per_share = abs(strategy.entry_price - strategy.stop_loss)
                        risk_decision["max_loss"] = risk_decision["position_size"] * risk_per_share
                    self.log(
                        state,
                        f"⚠️ Position size capped: {int(original_size)} → {int(risk_decision['position_size'])} shares "
                        f"(${total_position_value:,.2f} > buying power ${buying_power:,.2f})"
                    )

            if risk_decision["approved"]:
                portfolio_adjustment = self._portfolio_risk_check(
                    state, broker_info, risk_decision["position_size"]
                )
                if portfolio_adjustment["rejected"]:
                    risk_decision["approved"] = False
                    risk_decision["position_size"] = 0.0
                    risk_decision["max_loss"] = 0.0
                    risk_decision["warnings"] = [portfolio_adjustment["reason"]]
                    risk_decision["reasoning"] = f"Portfolio risk limit: {portfolio_adjustment['reason']}"
                    self.log(state, f"✗ Portfolio gate rejected trade: {portfolio_adjustment['reason']}")
                elif portfolio_adjustment["adjusted_size"] < risk_decision["position_size"]:
                    original_size = risk_decision["position_size"]
                    risk_decision["position_size"] = portfolio_adjustment["adjusted_size"]
                    if strategy.stop_loss is not None:
                        risk_per_share = abs(float(strategy.entry_price or 0) - float(strategy.stop_loss))
                        risk_decision["max_loss"] = risk_decision["position_size"] * risk_per_share
                    self.log(
                        state,
                        f"⚠️ Exposure cap reduced size: {int(original_size)} → "
                        f"{int(risk_decision['position_size'])} shares ({portfolio_adjustment['reason']})"
                    )

            if risk_decision["approved"]:
                entry = float(strategy.entry_price or 0)
                stop = float(strategy.stop_loss or 0) if strategy.stop_loss is not None else 0.0
                if stop and entry:
                    risk_decision["max_loss"] = risk_decision["position_size"] * abs(entry - stop)
                risk_decision["warnings"] = self._build_final_warnings(
                    broker_info=broker_info,
                    llm_warnings=llm_warnings,
                    final_size=risk_decision["position_size"],
                    final_max_loss=risk_decision["max_loss"],
                )
                risk_decision["reasoning"] = self._build_final_reasoning(
                    broker_info=broker_info,
                    strategy=strategy,
                    llm_reasoning=risk_decision["reasoning"],
                    final_size=risk_decision["position_size"],
                    final_max_loss=risk_decision["max_loss"],
                    rr_ratio=risk_decision["rr_ratio"],
                )
            
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
                report_data["Account Info"] = (
                    f"Equity: ${broker_info.get('equity', 0):,.2f} | "
                    f"Buying Power: ${broker_info.get('buying_power', 0):,.2f} | "
                    f"Cash: ${broker_info.get('cash', 0):,.2f} | "
                    f"Source: {broker_info.get('source', 'unknown')}"
                )
            
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
                # Prometheus metrics
                from app.telemetry import llm_calls_total, llm_tokens_total, llm_cost_dollars
                llm_calls_total.labels(model=model_id, agent_type="risk_manager_agent").inc()
                llm_tokens_total.labels(model=model_id, direction="input").inc(800)
                llm_tokens_total.labels(model=model_id, direction="output").inc(300)
                llm_cost_dollars.labels(model=model_id, agent_type="risk_manager_agent").inc(cost)
            finally:
                db.close()

            return state
            
        except Exception as e:
            self.logger.error(f"Risk assessment failed: {str(e)}", exc_info=True)
            raise AgentProcessingError(f"Risk assessment failed: {str(e)}")
    
    def _get_broker_account_info(self, state: PipelineState) -> Dict[str, Any]:
        """Query broker for account information."""
        if state.mode == "backtest" and state.backtest_run_id:
            try:
                from app.backtesting.backtest_broker import BacktestBroker

                initial_capital = float(
                    getattr(state, "initial_capital", 0)
                    or self.config.get("initial_capital")
                    or 10000
                )
                broker = BacktestBroker(
                    run_id=state.backtest_run_id,
                    initial_capital=initial_capital,
                )
                account = broker.get_account()
                positions = list(broker.get_positions().values())
                cash = float(account.get("cash", initial_capital))
                equity = float(account.get("equity", cash))
                self.log(
                    state,
                    f"📊 Backtest account — equity: ${equity:.2f}, "
                    f"buying power: ${cash:.2f}, cash: ${cash:.2f}"
                )
                return {
                    "account_balance": equity,
                    "buying_power": cash,
                    "cash": cash,
                    "equity": equity,
                    "positions": positions,
                    "source": "backtest_broker",
                }
            except Exception as e:
                self.logger.warning(f"Failed to get backtest broker info: {e}")

        broker_tool = self._get_broker_tool()
        
        if not broker_tool:
            config_account = self._config_account_info()
            if config_account:
                self.log(
                    state,
                    f"📊 Config account — equity: ${config_account['equity']:.2f}, "
                    f"buying power: ${config_account['buying_power']:.2f}, cash: ${config_account['cash']:.2f}"
                )
                return config_account
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
            
            if "error" in account_info:
                self.log(state, f"⚠️ Broker returned error: {account_info['error']}")
                config_account = self._config_account_info()
                if config_account:
                    config_account["source"] = "config_fallback"
                    config_account["broker_error"] = account_info["error"]
                    return config_account
                return {
                    "positions": [],
                    "source": "broker_error",
                    "error": account_info["error"],
                }
            
            # Normalize keys: different brokers return different key names
            # Alpaca uses "equity", Tradier uses "balance", Oanda uses "balance"/"nav"
            equity = (
                account_info.get("equity")
                or account_info.get("balance")
                or account_info.get("portfolio_value")
                or account_info.get("nav")
                or 10000
            )
            buying_power = (
                account_info.get("buying_power")
                or account_info.get("margin_available")
                or equity
            )
            cash = (
                account_info.get("cash")
                or account_info.get("cash_available")
                or equity
            )
            
            self.log(state, f"📊 Broker account — equity: ${equity:.2f}, buying power: ${buying_power:.2f}, cash: ${cash:.2f}")
            
            return {
                "account_balance": equity,
                "buying_power": buying_power,
                "cash": cash,
                "equity": equity,
                "positions": account_info.get("positions", []),
                "source": "broker"
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to get broker info: {e}")
            config_account = self._config_account_info()
            if config_account:
                config_account["source"] = "config_fallback"
                config_account["broker_error"] = str(e)
                return config_account
            return {
                "positions": [],
                "source": "broker_error",
                "error": str(e),
            }
    
    def _get_broker_tool(self):
        """Get any attached broker tool from config."""
        # Check for broker tools in config
        tools = self.config.get("tools", [])
        broker_types = ["alpaca_broker", "oanda_broker", "tradier_broker"]
        
        for tool in tools:
            if tool.get("tool_type") in broker_types:
                return tool
        
        return None

    def _config_account_info(self) -> Optional[Dict[str, Any]]:
        """Use explicit config balances when no broker lookup is available."""
        raw_equity = (
            self.config.get("account_balance")
            or self.config.get("equity")
            or self.config.get("portfolio_value")
        )
        if raw_equity in (None, ""):
            return None

        equity = float(raw_equity)
        buying_power = float(self.config.get("buying_power") or equity)
        cash = float(self.config.get("cash") or buying_power)
        return {
            "account_balance": equity,
            "buying_power": buying_power,
            "cash": cash,
            "equity": equity,
            "positions": list(self.config.get("positions", [])),
            "source": "config",
        }
    
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
        
        # Determine price precision based on asset type
        is_forex = "_" in state.symbol
        price_precision = 5 if is_forex else 2
        
        context = f"""
PROPOSED TRADE:
- Symbol: {state.symbol}
- Action: {strategy.action}
- Entry Price: ${entry:.{price_precision}f}
- Stop Loss: ${stop:.{price_precision}f}
- Take Profit: ${target:.{price_precision}f}
- Risk per share: ${risk_per_share:.{price_precision}f}
- Reward per share: ${reward_per_share:.{price_precision}f}
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
    
    # ------------------------------------------------------------------
    # Portfolio-level risk controls (TP-009)
    # ------------------------------------------------------------------

    def _portfolio_risk_check(
        self,
        state: PipelineState,
        broker_info: Dict[str, Any],
        det_size: float,
    ) -> Dict[str, Any]:
        """
        Check portfolio-level constraints before approving a new trade.

        Returns a dict with:
        - rejected: whether the trade must be rejected
        - adjusted_size: max permitted size after portfolio constraints
        - reason: human-readable explanation
        """
        import re

        positions = broker_info.get("positions", [])
        equity    = float(broker_info.get("equity", broker_info.get("account_balance", 10000)))
        strategy  = state.strategy
        entry     = float(strategy.entry_price or 0)
        action    = strategy.action

        # 1. Max concurrent positions
        max_pos = int(self.config.get("max_concurrent_positions", 5))
        if len(positions) >= max_pos:
            return {
                "rejected": True,
                "adjusted_size": 0.0,
                "reason": (
                    f"Max concurrent positions reached ({len(positions)}/{max_pos}). "
                    "Close an existing position before opening a new one."
                ),
            }

        # 2. Total exposure cap
        max_exposure_pct = self.config.get("max_total_exposure_pct")
        if max_exposure_pct is None:
            return {
                "rejected": False,
                "adjusted_size": float(det_size),
                "reason": "",
            }
        max_exposure_pct = float(max_exposure_pct)
        current_exposure = sum(
            abs(float(p.get("market_value", 0) or p.get("qty", 0) * float(p.get("avg_entry_price", 0) or 0)))
            for p in positions
        )
        new_trade_value = det_size * entry if entry > 0 else 0
        if equity > 0 and (current_exposure + new_trade_value) / equity > max_exposure_pct:
            remaining_exposure_value = max(0.0, equity * max_exposure_pct - current_exposure)
            max_size_by_exposure = int(remaining_exposure_value / entry) if entry > 0 else 0
            if max_size_by_exposure < 1:
                return {
                    "rejected": True,
                    "adjusted_size": 0.0,
                    "reason": (
                        f"Adding this position would bring total exposure to "
                        f"{(current_exposure + new_trade_value) / equity * 100:.0f}% of equity "
                        f"(limit: {max_exposure_pct * 100:.0f}%)."
                    ),
                }
            return {
                "rejected": False,
                "adjusted_size": float(min(det_size, max_size_by_exposure)),
                "reason": (
                    f"Position size reduced to respect total exposure cap of "
                    f"{max_exposure_pct * 100:.0f}%."
                ),
            }

        # 3. Side imbalance — don't allow > 80% of open positions on one side
        if positions:
            longs  = sum(1 for p in positions if float(p.get("qty", 0) or p.get("side", "").lower() == "long") > 0)
            shorts = len(positions) - longs
            new_long  = longs  + (1 if action == "BUY"  else 0)
            new_short = shorts + (1 if action == "SELL" else 0)
            total = new_long + new_short
            if total > 0:
                long_pct  = new_long  / total
                short_pct = new_short / total
                if long_pct > 0.80 or short_pct > 0.80:
                    dominant = "long" if long_pct > 0.80 else "short"
                    return {
                        "rejected": True,
                        "adjusted_size": 0.0,
                        "reason": (
                            f"Portfolio is >80% {dominant}-biased after this trade. "
                            "Add some balance before adding more exposure."
                        ),
                    }

        return {
            "rejected": False,
            "adjusted_size": float(det_size),
            "reason": "",
        }

    def _build_final_warnings(
        self,
        broker_info: Dict[str, Any],
        llm_warnings: List[str],
        final_size: float,
        final_max_loss: float,
    ) -> List[str]:
        """Build stable warnings that match the final deterministic result."""
        warnings: List[str] = []
        source = broker_info.get("source")
        if source == "config_fallback" and broker_info.get("broker_error"):
            warnings.append(
                "Broker account lookup failed; sizing used explicit configured account values "
                f"instead ({broker_info['broker_error']})."
            )
        elif source == "config":
            warnings.append("Broker lookup was not used; sizing used explicit configured account values.")

        for warning in llm_warnings:
            lower = warning.lower()
            if "confidence" in lower or "volatility" in lower:
                warnings.append(warning)

        if not warnings and source == "broker":
            return []

        # Remove duplicates while keeping order.
        deduped: List[str] = []
        seen = set()
        for warning in warnings:
            if warning not in seen:
                deduped.append(warning)
                seen.add(warning)
        return deduped

    def _build_final_reasoning(
        self,
        broker_info: Dict[str, Any],
        strategy,
        llm_reasoning: str,
        final_size: float,
        final_max_loss: float,
        rr_ratio: float,
    ) -> str:
        """Append system-enforced mechanics to the LLM's policy interpretation."""
        entry = float(strategy.entry_price or 0)
        stop = float(strategy.stop_loss or 0) if strategy.stop_loss is not None else 0.0
        equity = float(broker_info.get("equity", broker_info.get("account_balance", 0)) or 0)
        buying_power = float(broker_info.get("buying_power", equity) or 0)
        max_affordable = int(buying_power / entry) if entry > 0 else 0
        position_value = final_size * entry if entry > 0 else 0.0
        actual_risk_pct = (final_max_loss / equity * 100) if equity > 0 else 0.0

        source = broker_info.get("source", "unknown")
        source_note = {
            "broker": "Broker-reported account values were used.",
            "config": "Configured account values were used.",
            "config_fallback": "Configured account values were used because broker lookup failed.",
            "backtest_broker": "Backtest broker account values were used.",
            "default": "Default account values were used because no broker or explicit account values were configured.",
        }.get(source, f"Account values came from {source}.")

        summary_parts = [source_note]
        if max_affordable > 0:
            summary_parts.append(
                f"System buying-power cap = floor(${buying_power:,.2f} / ${entry:,.2f}) = {max_affordable} shares."
            )
        summary_parts.append(
            f"Final approved size = {int(final_size)} shares (${position_value:,.2f} notional), "
            f"max loss = ${final_max_loss:,.2f} ({actual_risk_pct:.2f}% of equity), "
            f"R/R = {rr_ratio:.2f}:1."
        )
        if llm_reasoning:
            return f"{llm_reasoning}\n\nSystem enforcement summary: {' '.join(summary_parts)}"
        return " ".join(summary_parts)

    def _calculate_fallback_position_size(
        self, state: PipelineState, strategy, broker_info: Dict[str, Any]
    ) -> float:
        """Kept for backwards compatibility."""
        entry = float(strategy.entry_price or 0)
        if entry <= 0:
            return 0.0
        buying_power = float(broker_info.get("buying_power", broker_info.get("equity", 0)) or 0)
        return float(max(1, int(buying_power / entry))) if buying_power > 0 else 0.0
    
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
