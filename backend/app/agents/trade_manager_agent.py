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
from enum import Enum
from typing import Tuple


class PositionCheckResult(Enum):
    """Result of checking broker for position/order status."""
    FOUND = "found"  # Position or order exists
    NOT_FOUND = "not_found"  # Confirmed doesn't exist (closed/cancelled)
    API_ERROR = "api_error"  # Could not check (network/API failure)


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
            # Mark pipeline as complete - trade was rejected
            state.should_complete = True
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
            # Mark pipeline as complete - no execution needed
            state.should_complete = True
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
                # Mark pipeline as complete - no need to monitor since we didn't trade
                state.should_complete = True
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
        Phase 2: Monitor open position or pending limit order.
        
        Checks if limit order is pending or position is open, and evaluates exit conditions.
        """
        self.log(state, "Phase 2: Monitoring position/order")
        
        broker_tool = self._get_broker_tool()
        
        if not broker_tool:
            self.log(state, "No broker tool - completing monitoring", level="warning")
            state.should_complete = True
            return state
        
        # Create broker instance once (avoid duplicate instantiation)
        from app.services.brokers.factory import broker_factory
        try:
            broker = broker_factory.from_tool_config(broker_tool)
        except Exception as e:
            self.log(state, f"❌ Failed to create broker instance: {str(e)}", level="error")
            self._handle_api_error(state, f"Failed to create broker: {str(e)}")
            return state
        
        # STEP 1: Check for pending limit order first
        order_id = state.trade_execution.order_id if state.trade_execution else None
        trade_id = state.trade_execution.trade_id if state.trade_execution else None
        pending_order = None
        
        if order_id and not trade_id:  # Only check if order not yet filled (no trade_id)
            # Check if the order is still pending (limit not filled yet)
            try:
                open_orders = broker.get_orders()
                for order in open_orders:
                    if order.order_id == order_id:
                        pending_order = order
                        break
                
                # Successfully checked - reset error counter
                if state.trade_execution:
                    state.trade_execution.api_error_count = 0
                    state.trade_execution.last_successful_check = datetime.now()
                    
            except Exception as e:
                self.log(state, f"❌ API error checking orders: {str(e)}", level="error")
                self._handle_api_error(state, f"Failed to check orders: {str(e)}")
                return state
        
        # STEP 2: If order is still pending, check if we should cancel it
        if pending_order:
            self.log(state, f"📋 Limit order still pending: {order_id}")
            
            # Check if order should be cancelled (setup invalidated)
            if state.strategy and state.strategy.entry_price:
                current_price, price_error = self._get_current_price(state.symbol, broker)
                
                if price_error:
                    self.log(state, f"❌ Failed to get current price: {price_error}", level="error")
                    self._handle_api_error(state, f"Failed to get price: {price_error}")
                    return state
                
                entry = state.strategy.entry_price
                stop_loss = state.strategy.stop_loss
                take_profit = state.strategy.take_profit
                price_precision = self._get_price_precision(state.symbol)
                
                should_cancel = False
                cancel_reason = None
                
                # CANCEL CONDITIONS:
                # 1. Price moved AWAY from entry and breached SL (setup invalidated)
                # 2. Price hit TP level without hitting entry first (missed entire move)
                
                if state.strategy.action == "BUY":
                    # BUY limit order: We want to buy when price comes DOWN to entry
                    # Entry < Current, SL < Entry, TP > Entry
                    # Cancel if:
                    # - Price went DOWN past SL (setup invalidated - too far down)
                    # - Price went UP past TP (missed the move - already at target)
                    
                    if stop_loss and current_price <= stop_loss:
                        # Price moved way down past our stop loss level
                        # Setup is invalidated - price moved against us too much
                        should_cancel = True
                        cancel_reason = f"Price ${current_price:.{price_precision}f} breached stop loss ${stop_loss:.{price_precision}f} before filling entry ${entry:.{price_precision}f} - setup invalidated"
                    
                    elif take_profit and current_price >= take_profit:
                        # Price already at take profit level without hitting our entry
                        # We missed the entire move
                        should_cancel = True
                        cancel_reason = f"Price ${current_price:.{price_precision}f} reached take profit ${take_profit:.{price_precision}f} without filling entry ${entry:.{price_precision}f} - missed opportunity"
                
                elif state.strategy.action == "SELL":
                    # SELL limit order: We want to sell when price comes UP to entry
                    # Entry > Current, SL > Entry, TP < Entry
                    # Cancel if:
                    # - Price went UP past SL (setup invalidated - too far up)
                    # - Price went DOWN past TP (missed the move - already at target)
                    
                    if stop_loss and current_price >= stop_loss:
                        # Price moved way up past our stop loss level
                        # Setup is invalidated - price moved against us too much
                        should_cancel = True
                        cancel_reason = f"Price ${current_price:.{price_precision}f} breached stop loss ${stop_loss:.{price_precision}f} before filling entry ${entry:.{price_precision}f} - setup invalidated"
                    
                    elif take_profit and current_price <= take_profit:
                        # Price already at take profit level without hitting our entry
                        # We missed the entire move
                        should_cancel = True
                        cancel_reason = f"Price ${current_price:.{price_precision}f} reached take profit ${take_profit:.{price_precision}f} without filling entry ${entry:.{price_precision}f} - missed opportunity"
                
                # Execute cancellation if needed
                if should_cancel:
                    try:
                        self.log(state, f"🚨 Cancelling limit order: {cancel_reason}")
                        broker.cancel_order(order_id)
                        state.should_complete = True
                        
                        self.record_report(
                            state,
                            title="Limit order cancelled",
                            summary=f"Setup invalidated - order cancelled",
                            status="completed",
                            data={
                                "symbol": state.symbol,
                                "reason": cancel_reason,
                                "order_id": order_id,
                                "current_price": current_price,
                                "entry_price": entry,
                                "stop_loss": stop_loss,
                                "take_profit": take_profit
                            },
                        )
                        return state
                    except Exception as e:
                        self.log(state, f"❌ Failed to cancel order: {str(e)}", level="error")
                        self._handle_api_error(state, f"Failed to cancel order: {str(e)}")
                        return state
            
            # Order still valid, keep monitoring
            self.log(state, f"Order still valid - waiting for fill")
            self.record_report(
                state,
                title="Monitoring limit order",
                summary=f"Waiting for limit order to fill: {state.symbol}",
                data={
                    "symbol": state.symbol,
                    "order_id": order_id,
                    "order_status": "pending",
                    "order_type": "limit",
                    "entry_price": state.strategy.entry_price if state.strategy else None,
                    "stop_loss": state.strategy.stop_loss if state.strategy else None,
                    "take_profit": state.strategy.take_profit if state.strategy else None
                },
            )
            return state
        
        # STEP 3: Order filled or not found, check for position
        # If order was pending but now gone, it might have filled - try to get trade_id
        if order_id and not trade_id and not pending_order:
            self.log(state, f"🔄 Limit order {order_id} no longer pending - checking if filled...")
            # TODO: Query broker for trade_id (broker-specific implementation)
            # For now, we'll discover it in position check
        
        # Check position with proper error handling
        position_result, position_data = self._get_position(state.symbol, broker_tool)
        
        if position_result == PositionCheckResult.API_ERROR:
            # Cannot reach broker - mark as communication error and retry
            self.log(state, f"❌ API error checking position for {state.symbol}", level="error")
            self._handle_api_error(state, f"Failed to check position for {state.symbol}")
            return state
        
        elif position_result == PositionCheckResult.FOUND:
            # Position exists - monitor it
            position = position_data
            
            # Successfully checked - reset error counter
            if state.trade_execution:
                state.trade_execution.api_error_count = 0
                state.trade_execution.last_successful_check = datetime.now()
            
            # Extract trade_id if we don't have it yet (order filled)
            if not trade_id and position and 'trade_id' in position:
                self.log(state, f"✅ Order filled! Discovered trade_id: {position['trade_id']}")
                if state.trade_execution:
                    state.trade_execution.trade_id = position['trade_id']
            
            # Log position status
            pnl_percent = ((position["unrealized_pl"] / position["cost_basis"]) * 100) if position.get("cost_basis") else 0
            self.log(state, f"Position: {position['qty']} shares @ {pnl_percent:+.2f}% P&L")
            
            # Evaluate emergency exit conditions
            should_close, reason = self._evaluate_exit_conditions(state, position)
            
            if should_close:
                self.log(state, f"🚨 Emergency exit triggered: {reason}")
                try:
                    self._close_position(state.symbol, broker_tool, reason)
                    state.should_complete = True
                    
                    unrealized_pl = position.get("unrealized_pl", 0)
                    
                    self.record_report(
                        state,
                        title="Emergency exit executed",
                        summary=f"Position closed due to: {reason} | P&L: ${unrealized_pl:+.2f} ({pnl_percent:+.2f}%)",
                        status="completed",
                        data={
                            "symbol": state.symbol,
                            "reason": reason,
                            "unrealized_pl": unrealized_pl,
                            "pnl_percent": pnl_percent,
                            "closed_at": datetime.now().isoformat(),
                            "order_id": order_id,
                            "trade_id": trade_id
                        },
                    )
                    return state
                except Exception as e:
                    self.log(state, f"❌ Failed to close position: {str(e)}", level="error")
                    self._handle_api_error(state, f"Failed to close position: {str(e)}")
                    return state
            
            # Continue monitoring
            unrealized_pl = position.get("unrealized_pl", 0)
            
            self.record_report(
                state,
                title="Position monitoring",
                summary=f"Monitoring {state.symbol}: ${unrealized_pl:+.2f} ({pnl_percent:+.2f}%)",
                data={
                    "symbol": state.symbol,
                    "qty": position["qty"],
                    "unrealized_pl": unrealized_pl,
                    "pnl_percent": pnl_percent,
                    "current_price": position.get("current_price"),
                    "cost_basis": position.get("cost_basis"),
                    "entry_price": state.strategy.entry_price if state.strategy else None,
                    "stop_loss": state.strategy.stop_loss if state.strategy else None,
                    "take_profit": state.strategy.take_profit if state.strategy else None,
                    "order_id": order_id,
                    "trade_id": trade_id
                },
            )
            
            return state
        
        elif position_result == PositionCheckResult.NOT_FOUND:
            # Position confirmed closed
            # ⚠️ CRITICAL: Verify we expected this (don't assume orphaned trade is closed)
            
            # If we had a trade_id or order_id, log warning about position not found
            if (order_id or trade_id) and state.trade_execution:
                last_check = state.trade_execution.last_successful_check
                if last_check:
                    time_since_last_check = (datetime.now() - last_check).total_seconds()
                    self.log(
                        state, 
                        f"⚠️ Position not found for {state.symbol} (order_id={order_id}, trade_id={trade_id}). "
                        f"Last successful check: {time_since_last_check:.0f}s ago",
                        level="warning"
                    )
                else:
                    self.log(
                        state,
                        f"⚠️ Position not found for {state.symbol} (order_id={order_id}, trade_id={trade_id}). "
                        "This is the first monitoring check - position may have closed via bracket orders.",
                        level="warning"
                    )
            
            # Position closed (bracket orders worked or manually closed)
            self.log(state, "✓ Position closed - monitoring complete")
            state.should_complete = True
            
            # Try to get final P&L from trade_execution or last monitoring report
            final_pnl = None
            final_pnl_percent = None
            
            # Check if we have trade execution data with entry price
            if state.trade_execution and state.strategy:
                # Get last known P&L from previous reports if available
                if hasattr(state, 'agent_reports') and self.agent_id in state.agent_reports:
                    last_report = state.agent_reports[self.agent_id]
                    if isinstance(last_report, dict) and 'data' in last_report:
                        final_pnl = last_report['data'].get('unrealized_pl')
                        final_pnl_percent = last_report['data'].get('pnl_percent')
            
            self.record_report(
                state,
                title="Position closed",
                summary=f"{state.symbol} position closed" + (f" | Final P&L: ${final_pnl:+.2f} ({final_pnl_percent:+.2f}%)" if final_pnl is not None else ""),
                status="completed",
                data={
                    "symbol": state.symbol,
                    "reason": "Position closed",
                    "final_pnl": final_pnl,
                    "final_pnl_percent": final_pnl_percent,
                    "closed_at": datetime.now().isoformat(),
                    "order_id": order_id,
                    "trade_id": trade_id
                },
            )
            return state
    
    def _has_duplicate_position(self, state: PipelineState, broker_tool) -> bool:
        """Check if position or pending order already exists for symbol."""
        try:
            # Check for existing position
            position_result, position_data = self._get_position(state.symbol, broker_tool)
            if position_result == PositionCheckResult.FOUND:
                self.log(state, f"Found existing position for {state.symbol}")
                return True
            
            # If API error, be conservative and assume duplicate to avoid double-entry
            if position_result == PositionCheckResult.API_ERROR:
                self.log(state, f"⚠️ API error checking position - conservatively assuming duplicate", level="warning")
                return True
            
            # Check for pending limit orders
            from app.services.brokers.factory import broker_factory
            broker = broker_factory.from_tool_config(broker_tool)
            
            try:
                open_orders = broker.get_orders()
                for order in open_orders:
                    # Normalize symbol formats for comparison
                    order_symbol = order.symbol.replace("_", "/")
                    state_symbol = state.symbol.replace("_", "/")
                    
                    if order_symbol == state_symbol or order.symbol == state.symbol:
                        self.log(state, f"Found pending order {order.order_id} for {state.symbol}")
                        return True
            except Exception as e:
                self.log(state, f"⚠️ API error checking orders - conservatively assuming duplicate: {str(e)}", level="warning")
                # Be conservative - assume duplicate to avoid double-entry
                return True
            
            return False
        except Exception as e:
            self.log(state, f"⚠️ Error checking for duplicate - conservatively assuming duplicate: {str(e)}", level="warning")
            # Be conservative - assume duplicate to avoid double-entry
            return True
    
    def _get_position(self, symbol: str, broker_tool) -> Tuple[PositionCheckResult, Optional[Dict]]:
        """
        Get position from broker with proper error handling.
        
        Returns:
            Tuple of (PositionCheckResult, position_data)
            - FOUND: position exists, data included
            - NOT_FOUND: confirmed no position (closed)
            - API_ERROR: could not check (network/API failure)
        """
        try:
            from app.services.brokers.factory import broker_factory
            
            # Create broker service from tool config
            broker = broker_factory.from_tool_config(broker_tool)
            
            # Get position
            position = broker.get_position(symbol)
            
            if position:
                return (PositionCheckResult.FOUND, {
                    "symbol": position.symbol,
                    "qty": position.qty,
                    "side": position.side,
                    "avg_entry_price": position.avg_entry_price,
                    "current_price": position.current_price,
                    "unrealized_pl": position.unrealized_pl,
                    "unrealized_pl_percent": position.unrealized_pl_percent,
                    "market_value": position.market_value,
                    "cost_basis": position.cost_basis
                })
            else:
                # No position found - confirmed closed/doesn't exist
                return (PositionCheckResult.NOT_FOUND, None)
            
        except Exception as e:
            # API error - could not check broker
            self.logger.error(f"API error checking position for {symbol}: {str(e)}")
            return (PositionCheckResult.API_ERROR, None)
    
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
                self.logger.error(f"Failed to close position for {symbol}: {result.get('error')}")
                
        except Exception as e:
            self.logger.error(f"Error closing position for {symbol}: {str(e)}")
    
    def _get_current_price(self, symbol: str, broker) -> Tuple[float, Optional[str]]:
        """
        Get current market price for a symbol.
        
        Returns:
            Tuple of (price, error_message)
            - On success: (price, None)
            - On failure: (0.0, error_message)
        """
        try:
            # Try to get position first (includes current price)
            position = broker.get_position(symbol)
            if position and position.current_price:
                return (position.current_price, None)
            
            # No position found - could be valid (closed) or could be error
            # For limit order monitoring, we need current price even without position
            # This would require broker API enhancement to get quotes
            return (0.0, f"No position for {symbol}, cannot determine current price")
            
        except Exception as e:
            error_msg = f"API error getting current price for {symbol}: {str(e)}"
            self.logger.error(error_msg)
            return (0.0, error_msg)
    
    def _get_price_precision(self, symbol: str) -> int:
        """
        Get the price precision (decimal places) for a symbol.
        
        Forex pairs typically use 5 decimal places, stocks use 2.
        """
        # Forex symbols typically have underscore (e.g., EUR_USD)
        if "_" in symbol or "/" in symbol:
            return 5
        return 2
    
    def _handle_api_error(self, state: PipelineState, error_message: str):
        """
        Handle API error during monitoring.
        
        Tracks consecutive failures and marks execution as COMMUNICATION_ERROR
        if threshold exceeded, requiring manual intervention.
        """
        if not state.trade_execution:
            state.trade_execution = TradeExecution(
                order_id=None,
                status="monitoring",
                api_error_count=1,
                last_api_error=error_message
            )
        else:
            state.trade_execution.api_error_count += 1
            state.trade_execution.last_api_error = error_message
        
        error_count = state.trade_execution.api_error_count
        
        self.log(
            state,
            f"🔴 API error #{error_count}: {error_message}",
            level="error"
        )
        
        # After 5 consecutive failures, mark as communication error requiring intervention
        if error_count >= 5:
            self.log(
                state,
                f"🚨 COMMUNICATION ERROR: {error_count} consecutive API failures. Manual intervention required!",
                level="error"
            )
            
            # Set execution status to COMMUNICATION_ERROR (handled in tasks.py)
            state.communication_error = True
            state.communication_error_message = error_message
            
            self.record_report(
                state,
                title="Communication Error",
                summary=f"Cannot reach broker API after {error_count} attempts",
                status="error",
                data={
                    "symbol": state.symbol,
                    "error_count": error_count,
                    "last_error": error_message,
                    "order_id": state.trade_execution.order_id,
                    "trade_id": state.trade_execution.trade_id,
                    "last_successful_check": state.trade_execution.last_successful_check.isoformat() if state.trade_execution.last_successful_check else None
                },
            )
        else:
            # Still retrying
            self.record_report(
                state,
                title="Monitoring (API Error)",
                summary=f"Temporary API error ({error_count}/5 failures) - retrying...",
                status="retrying",
                data={
                    "symbol": state.symbol,
                    "error_count": error_count,
                    "last_error": error_message,
                    "order_id": state.trade_execution.order_id,
                    "trade_id": state.trade_execution.trade_id
                },
            )
    
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
            
            # Check for duplicate open orders first
            existing_orders = broker.get_orders()
            for order in existing_orders:
                if order.symbol == state.symbol or order.symbol.replace("_", "/") == state.symbol.replace("_", "/"):
                    self.log(state, f"⚠️ Duplicate order detected: {order.order_id} for {state.symbol}")
                    state.trade_execution = TradeExecution(
                        order_id=None,
                        status="skipped",
                        filled_price=None,
                        filled_quantity=None,
                        commission=None,
                        execution_time=datetime.utcnow(),
                        broker_response={"reason": f"Duplicate order exists: {order.order_id}"}
                    )
                    self.record_report(
                        state,
                        title="Trade skipped - duplicate order",
                        summary=f"Skipped {strategy.action} for {state.symbol} - open order already exists",
                        status="skipped",
                        data={"reason": "Duplicate open order detected", "existing_order_id": order.order_id},
                    )
                    return state
            
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
            
            # Determine price precision for logging
            is_forex = "_" in state.symbol
            price_precision = 5 if is_forex else 2
            
            if has_targets:
                # Strategy provided targets → Use LIMIT bracket order (wait for entry price)
                order_type_used = "limit_bracket"
                self.log(state, f"📊 Placing LIMIT bracket order: Entry=${entry:.{price_precision}f}, TP=${take_profit:.{price_precision}f}, SL=${stop_loss:.{price_precision}f}")
                
                order = broker.place_limit_bracket_order(
                    symbol=state.symbol,
                    qty=risk.position_size,
                    side=broker_side,
                    limit_price=entry,
                    take_profit_price=take_profit,
                    stop_loss_price=stop_loss,
                    time_in_force=time_in_force
                )
                
                self.log(state, "✅ Limit bracket order placed (will fill at entry price with TP/SL)")
            else:
                # No targets from strategy → Use simple market order
                order_type_used = "market"
                self.log(state, f"📊 Executing market order (no TP/SL from strategy): Entry=${entry:.{price_precision}f}")
                
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
            state.monitor_interval_minutes = 0.25  # Check every 15 seconds
            
            # Determine price precision for display
            is_forex = "_" in state.symbol
            price_precision = 5 if is_forex else 2
            
            # Log execution details
            self.log(state, f"✓ {strategy.action} {risk.position_size:.0f} units @ ${entry:.{price_precision}f}")
            self.log(state, f"  Order ID: {order.order_id}")
            self.log(state, f"  Order Type: {order_type_used.upper()}")
            
            if has_targets:
                # Calculate percentages for bracket orders
                tp_pct = ((take_profit - entry) / entry * 100) if entry > 0 else 0
                sl_pct = abs((stop_loss - entry) / entry * 100) if entry > 0 else 0
                self.log(state, f"  Take Profit: ${take_profit:.{price_precision}f} ({tp_pct:+.2f}%)")
                self.log(state, f"  Stop Loss: ${stop_loss:.{price_precision}f} ({-sl_pct:.2f}%)")
            
            self.log(state, "Entering MONITORING mode")
            
            # Determine price precision for display
            is_forex = "_" in state.symbol
            price_precision = 5 if is_forex else 2
            
            self.record_report(
                state,
                title="Trade executed",
                summary=f"{strategy.action} {risk.position_size:.0f} {state.symbol} @ ${entry:.{price_precision}f} (LIMIT ORDER)",
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
            self.logger.error(f"Broker trade execution failed: {str(e)}", exc_info=True)
            
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
