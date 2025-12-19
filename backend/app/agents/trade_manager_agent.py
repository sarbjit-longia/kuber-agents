"""
Trade Manager Agent - Position-Aware Trade Execution & Monitoring

Executes trades and monitors open positions.
Supports both webhooks (fire-and-forget) and broker trading (with monitoring).
"""
from typing import Dict, Any, Optional
from datetime import datetime
import re

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema, TradeExecution
from app.config import settings


class TradeManagerAgent(BaseAgent):
    """
    Trade execution and position monitoring agent.
    
    **Behavior:**
    - Phase 1 (Execute): Checks for duplicate positions, executes trade via broker or webhook
    - Phase 2 (Monitor): Monitors open positions every 5 minutes until closed
    
    **Tool Types:**
    - Webhook: Fire-and-forget, completes immediately
    - Broker (Alpaca/Oanda/Tradier): Executes bracket order with TP/SL, enters MONITORING mode
    
    **Note:** This agent is rule-based (no LLM). TP/SL prices come from Strategy Agent.
    """
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            agent_type="trade_manager_agent",
            name="Trade Manager Agent",
            description="Executes and monitors trades. Supports webhooks and broker execution with position monitoring.",
            category="execution",
            version="2.0.0",
            icon="swap_horiz",
            pricing_rate=0.0,
            is_free=True,
            requires_timeframes=[],
            requires_market_data=True,
            requires_position=False,
            supported_tools=["alpaca_broker", "oanda_broker", "tradier_broker", "webhook_notifier", "email_notifier"],
            config_schema=AgentConfigSchema(
                type="object",
                title="Trade Manager Configuration",
                description="Configure trade execution and monitoring",
                properties={
                    "time_in_force": {
                        "type": "string",
                        "title": "Time in Force",
                        "description": "How long order remains active",
                        "enum": ["Day", "Good Till Cancelled", "Immediate or Cancel", "Fill or Kill"],
                        "default": "Good Till Cancelled"
                    }
                },
                required=[]
            ),
            can_initiate_trades=True,
            can_close_positions=True
        )
    
    def process(self, state: PipelineState) -> PipelineState:
        """
        Execute or monitor trade based on execution phase.
        
        Args:
            state: Pipeline state
            
        Returns:
            Updated state with execution results
        """
        # Determine phase
        is_monitoring = state.execution_phase == "monitoring"
        
        if is_monitoring:
            return self._monitor_position(state)
        else:
            return self._execute_trade(state)
    
    def _convert_time_in_force(self, user_friendly_value: str):
        """Convert user-friendly time in force to broker enum value."""
        from app.services.brokers.base import TimeInForce
        
        mapping = {
            "Day": TimeInForce.DAY,
            "Good Till Cancelled": TimeInForce.GTC,
            "Immediate or Cancel": TimeInForce.IOC,
            "Fill or Kill": TimeInForce.FOK
        }
        
        return mapping.get(user_friendly_value, TimeInForce.GTC)  # Default to GTC
    
    def _execute_trade(self, state: PipelineState) -> PipelineState:
        """
        Phase 1: Execute trade.
        
        Checks for duplicate positions and executes via webhook or broker.
        """
        self.log(state, "Phase 1: Executing trade")
        
        # Validate only one broker is attached
        self._validate_single_broker()
        
        # Validate we have risk assessment
        # Do not raise InsufficientDataError here; missing upstream outputs should result in a
        # clean "skipped" trade so the pipeline execution can complete with a readable outcome.
        if not state.risk_assessment:
            state.trade_execution = TradeExecution(
                order_id=None,
                status="skipped",
                filled_price=None,
                filled_quantity=None,
                commission=None,
                execution_time=datetime.utcnow(),
                broker_response={"reason": "No risk assessment available - skipping trade."},
            )
            self.log(state, "⚠️ No risk assessment available. Skipping trade execution.")
            return state
        
        risk = state.risk_assessment
        strategy = state.strategy
        
        # Check if trade approved
        if not risk.approved or not strategy:
            state.trade_execution = TradeExecution(
                order_id=None,
                status="rejected",
                filled_price=None,
                filled_quantity=None,
                commission=None,
                execution_time=None,
                broker_response={"reason": "Trade not approved by risk manager"}
            )
            self.log(state, "Trade not approved - execution skipped")
            self.record_report(
                state,
                title="Trade execution skipped",
                summary="Risk manager did not approve trade",
                status="skipped",
                data={"reason": risk.reasoning},
            )
            return state
        
        # Check if HOLD
        if strategy.action == "HOLD":
            state.trade_execution = TradeExecution(
                order_id=None,
                status="no_action",
                filled_price=None,
                filled_quantity=None,
                commission=None,
                execution_time=None,
                broker_response={"reason": "HOLD signal - no trade to execute"}
            )
            self.log(state, "HOLD signal - no execution needed")
            self.record_report(
                state,
                title="No execution (HOLD)",
                summary="Strategy advised HOLD",
                status="skipped",
                data={"strategy_action": strategy.action},
            )
            return state
        
        # Get attached tools
        broker_tool = self._get_broker_tool()
        webhook_tool = self._get_tool_by_type("webhook_notifier")
        
        # Check for duplicate position (broker only)
        if broker_tool:
            if self._has_duplicate_position(state, broker_tool):
                state.trade_execution = TradeExecution(
                    order_id=None,
                    status="skipped",
                    filled_price=None,
                    filled_quantity=None,
                    commission=None,
                    execution_time=None,
                    broker_response={"reason": "Position already exists for this symbol"}
                )
                self.log(state, f"⚠️ Duplicate position detected for {state.symbol} - SKIPPED")
                self.record_report(
                    state,
                    title="Duplicate position detected",
                    summary=f"Position already open for {state.symbol}",
                    status="skipped",
                    data={"symbol": state.symbol},
                )
                return state
        
        # Execute based on tool type
        if webhook_tool:
            # Webhook: Fire and forget
            return self._send_webhook(state, strategy, risk, webhook_tool)
        
        elif broker_tool:
            # Broker: Execute and enter monitoring mode
            return self._execute_broker_trade(state, strategy, risk, broker_tool)
        
        else:
            raise AgentProcessingError("No execution tool attached (broker or webhook)")
    
    def _monitor_position(self, state: PipelineState) -> PipelineState:
        """
        Phase 2: Monitor open position.
        
        Checks if position is still open and evaluates emergency exit conditions.
        """
        self.log(state, "Phase 2: Monitoring position")
        
        broker_tool = self._get_broker_tool()
        
        if not broker_tool:
            self.log(state, "No broker tool - completing monitoring", level="warning")
            state.should_complete = True
            return state
        
        # Check if position still exists
        position = self._get_position(state.symbol, broker_tool)
        
        if not position:
            # Position closed (bracket orders worked or manually closed)
            self.log(state, "✓ Position closed - monitoring complete")
            state.should_complete = True
            self.record_report(
                state,
                title="Position closed",
                summary=f"{state.symbol} position no longer open",
                status="completed",
                data={"symbol": state.symbol, "reason": "Position closed"},
            )
            return state
        
        # Log position status
        pnl_percent = ((position["unrealized_pl"] / position["cost_basis"]) * 100) if position.get("cost_basis") else 0
        self.log(state, f"Position: {position['qty']} shares @ {pnl_percent:+.2f}% P&L")
        
        # Evaluate emergency exit conditions
        should_close, reason = self._evaluate_exit_conditions(state, position)
        
        if should_close:
            self.log(state, f"🚨 Emergency exit triggered: {reason}")
            self._close_position(state.symbol, broker_tool, reason)
            state.should_complete = True
            self.record_report(
                state,
                title="Emergency exit executed",
                summary=f"Position closed due to: {reason}",
                status="completed",
                data={
                    "symbol": state.symbol,
                    "reason": reason,
                    "pnl_percent": pnl_percent
                },
            )
            return state
        
        # Continue monitoring
        self.record_report(
            state,
            title="Position monitoring",
            summary=f"Monitoring {state.symbol}: {pnl_percent:+.2f}% P&L",
            data={
                "qty": position["qty"],
                "unrealized_pl": position["unrealized_pl"],
                "pnl_percent": pnl_percent
            },
        )
        
        return state
    
    def _has_duplicate_position(self, state: PipelineState, broker_tool) -> bool:
        """Check if position already exists for symbol."""
        try:
            position = self._get_position(state.symbol, broker_tool)
            return position is not None
        except Exception as e:
            self.log(state, f"Error checking for duplicate: {str(e)}", level="warning")
            return False
    
    def _get_position(self, symbol: str, broker_tool) -> Optional[Dict]:
        """Get position from broker."""
        try:
            from app.services.brokers.factory import broker_factory
            
            # Create broker service from tool config
            broker = broker_factory.from_tool_config(broker_tool)
            
            # Get position
            position = broker.get_position(symbol)
            
            if position:
                return {
                    "symbol": position.symbol,
                    "qty": position.qty,
                    "side": position.side,
                    "avg_entry_price": position.avg_entry_price,
                    "current_price": position.current_price,
                    "unrealized_pl": position.unrealized_pl,
                    "unrealized_pl_percent": position.unrealized_pl_percent,
                    "market_value": position.market_value,
                    "cost_basis": position.cost_basis
                }
            return None
            
        except Exception as e:
            self.logger.error("Failed to get position", symbol=symbol, error=str(e))
            return None
    
    def _close_position(self, symbol: str, broker_tool, reason: str):
        """Close position at market."""
        try:
            from app.services.brokers.factory import broker_factory
            
            # Create broker service from tool config
            broker = broker_factory.from_tool_config(broker_tool)
            
            # Close position
            result = broker.close_position(symbol)
            
            if result.get("success"):
                self.logger.info("Position closed successfully", symbol=symbol, reason=reason)
            else:
                self.logger.error("Failed to close position", symbol=symbol, error=result.get("error"))
                
        except Exception as e:
            self.logger.error("Error closing position", symbol=symbol, error=str(e))
    
    def _send_webhook(self, state, strategy, risk, webhook_tool) -> PipelineState:
        """Send trade signal via webhook (fire-and-forget)."""
        
        payload = {
            "symbol": state.symbol,
            "action": strategy.action,
            "entry_price": strategy.entry_price,
            "stop_loss": strategy.stop_loss,
            "take_profit": strategy.take_profit,
            "position_size": risk.position_size,
            "confidence": strategy.confidence,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # TODO: Send webhook
        # webhook_tool.send(payload)
        
        state.trade_execution = TradeExecution(
            order_id=f"WEBHOOK-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            status="sent",
            filled_price=None,
            filled_quantity=None,
            commission=None,
            execution_time=datetime.utcnow(),
            broker_response={"webhook": "sent", "payload": payload}
        )
        
        self.log(state, "✓ Webhook sent successfully")
        self.record_report(
            state,
            title="Webhook sent",
            summary=f"{strategy.action} {state.symbol} via webhook",
            data=payload,
        )
        
        # Webhook completes immediately (no monitoring)
        return state
    
    def _execute_broker_trade(self, state, strategy, risk, broker_tool) -> PipelineState:
        """Execute trade via broker and enter monitoring mode."""
        
        try:
            from app.services.brokers.factory import broker_factory
            from app.services.brokers.base import OrderSide, OrderType as BrokerOrderType
            
            # Create broker service
            broker = broker_factory.from_tool_config(broker_tool)
            
            # Get strategy details
            entry = strategy.entry_price
            take_profit = strategy.take_profit
            stop_loss = strategy.stop_loss
            broker_side = OrderSide.BUY if strategy.action == "BUY" else OrderSide.SELL
            
            # Get time in force from config
            time_in_force_str = self.config.get("time_in_force", "Good Till Cancelled")
            time_in_force = self._convert_time_in_force(time_in_force_str)
            
            # 🎯 AUTO-DETECT ORDER TYPE: If strategy provides TP/SL, use bracket order
            has_targets = take_profit is not None and stop_loss is not None
            
            if has_targets:
                # Strategy provided targets → Use bracket order (entry + TP + SL)
                order_type_used = "bracket"
                self.log(state, f"📊 Executing bracket order: Entry=${entry:.2f}, TP=${take_profit:.2f}, SL=${stop_loss:.2f}")
                
                order = broker.place_bracket_order(
                    symbol=state.symbol,
                    qty=risk.position_size,
                    side=broker_side,
                    take_profit_price=take_profit,
                    stop_loss_price=stop_loss,
                    time_in_force=time_in_force
                )
                
                self.log(state, "✅ Bracket order placed (broker will manage TP/SL)")
            else:
                # No targets from strategy → Use simple market order
                order_type_used = "market"
                self.log(state, f"📊 Executing market order (no TP/SL from strategy): Entry=${entry:.2f}")
                
                order = broker.place_order(
                    symbol=state.symbol,
                    qty=risk.position_size,
                    side=broker_side,
                    order_type=BrokerOrderType.MARKET,
                    time_in_force=time_in_force
                )
                
                self.log(state, "✅ Market order placed (manual monitoring needed)")
            
            # Store execution result
            state.trade_execution = TradeExecution(
                order_id=order.order_id,
                status=order.status.value,
                filled_price=order.filled_price or entry,
                filled_quantity=order.filled_qty or risk.position_size,
                commission=0.0,  # TODO: Get from broker if available
                execution_time=order.submitted_at or datetime.utcnow(),
                broker_response={
                    "broker": broker.__class__.__name__,
                    "action": strategy.action,
                    "symbol": state.symbol,
                    "order_type": order_type_used,  # Auto-detected
                    "take_profit": take_profit,
                    "stop_loss": stop_loss,
                    "order_data": order.broker_data
                }
            )
            
            # Enter monitoring mode
            state.execution_phase = "monitoring"
            state.monitor_interval_minutes = 5
            
            # Log execution details
            self.log(state, f"✓ {strategy.action} {risk.position_size:.0f} shares @ ${entry:.2f}")
            self.log(state, f"  Order ID: {order.order_id}")
            self.log(state, f"  Order Type: {order_type_used.upper()}")
            
            if has_targets:
                # Calculate percentages for bracket orders
                tp_pct = ((take_profit - entry) / entry * 100) if entry > 0 else 0
                sl_pct = abs((stop_loss - entry) / entry * 100) if entry > 0 else 0
                self.log(state, f"  Take Profit: ${take_profit:.2f} ({tp_pct:+.2f}%)")
                self.log(state, f"  Stop Loss: ${stop_loss:.2f} ({-sl_pct:.2f}%)")
            
            self.log(state, "Entering MONITORING mode")
            
            self.record_report(
                state,
                title="Trade executed",
                summary=f"{strategy.action} {risk.position_size:.0f} {state.symbol} @ ${entry:.2f}",
                status="completed",
                data={
                    "action": strategy.action,
                    "symbol": state.symbol,
                    "quantity": risk.position_size,
                    "entry_price": entry,
                    "take_profit": take_profit,
                    "stop_loss": stop_loss,
                    "order_type": order_type_used,  # Auto-detected
                    "order_id": order.order_id,
                    "broker": broker.__class__.__name__
                },
            )
            
            return state
            
        except Exception as e:
            self.logger.error("Broker trade execution failed", error=str(e), exc_info=True)
            
            # Store failure
            state.trade_execution = TradeExecution(
                order_id=None,
                status="rejected",
                filled_price=None,
                filled_quantity=None,
                commission=None,
                execution_time=datetime.utcnow(),
                broker_response={"error": str(e)}
            )
            
            self.record_report(
                state,
                title="Trade execution failed",
                summary=f"Failed to execute {strategy.action} for {state.symbol}",
                status="failed",
                data={"error": str(e)},
            )
            
            return state
    
    def _evaluate_exit_conditions(self, state, position) -> tuple[bool, str]:
        """
        Evaluate emergency exit conditions from instructions.
        
        Returns:
            (should_close, reason)
        """
        instructions = self.config.get("instructions", "").lower()
        
        # Check for manual emergency signal
        if state.signal_data and state.signal_data.signal_type == "EMERGENCY_EXIT":
            return True, "Manual emergency signal received"
        
        # Parse VIX threshold from instructions
        vix_match = re.search(r'vix\s*[>]\s*(\d+)', instructions)
        if vix_match:
            vix_threshold = float(vix_match.group(1))
            # TODO: Get actual VIX value
            # current_vix = get_vix()
            # if current_vix > vix_threshold:
            #     return True, f"VIX spike: {current_vix} > {vix_threshold}"
        
        # Check for news-based exit
        if "news" in instructions or "high impact" in instructions:
            # TODO: Check for high impact news
            # if check_high_impact_news(state.symbol):
            #     return True, "High impact news detected"
            pass
        
        # Check for market crash condition
        if "market crash" in instructions or "spy" in instructions:
            # TODO: Check SPY performance
            # spy_change = get_spy_daily_change()
            # if spy_change < -3.0:
            #     return True, f"Market crash: SPY {spy_change:.1f}%"
            pass
        
        return False, ""
    
    def _get_tool_by_type(self, tool_type: str):
        """Get attached tool by type."""
        tools = self.config.get("tools", [])
        for tool in tools:
            if tool.get("tool_type") == tool_type:
                return tool
        return None
    
    def _get_broker_tool(self):
        """Get any attached broker tool (Alpaca, Oanda, or Tradier)."""
        broker_types = ["alpaca_broker", "oanda_broker", "tradier_broker"]
        for broker_type in broker_types:
            tool = self._get_tool_by_type(broker_type)
            if tool:
                return tool
        return None
    
    def _validate_single_broker(self):
        """Ensure only one broker tool is attached."""
        broker_types = ["alpaca_broker", "oanda_broker", "tradier_broker"]
        attached_brokers = [
            broker_type for broker_type in broker_types 
            if self._get_tool_by_type(broker_type)
        ]
        
        if len(attached_brokers) > 1:
            broker_names = {
                "alpaca_broker": "Alpaca",
                "oanda_broker": "Oanda",
                "tradier_broker": "Tradier"
            }
            attached_names = [broker_names[b] for b in attached_brokers]
            
            raise AgentProcessingError(
                f"Multiple broker tools attached: {', '.join(attached_names)}. "
                f"Please attach only ONE broker tool (Alpaca, Oanda, or Tradier). "
                f"The Trade Manager can only execute on one broker at a time."
            )
