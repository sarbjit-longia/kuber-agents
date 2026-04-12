"""
Trade Manager Agent - Position-Aware Trade Execution & Monitoring

Executes trades and monitors open positions.
Supports both webhooks (fire-and-forget) and broker trading (with monitoring).
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import re

from app.agents.base import BaseAgent, InsufficientDataError, AgentProcessingError
from app.schemas.pipeline_state import PipelineState, AgentMetadata, AgentConfigSchema, TradeExecution, BracketLeg
from app.config import settings
from enum import Enum
from typing import Tuple
import structlog

logger = structlog.get_logger()


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

        if state.mode == "backtest" and state.backtest_run_id:
            return self._execute_backtest_trade(state)
        
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
        
        # ⚠️ MARKET HOURS CHECK: Don't execute trades outside market hours
        try:
            from app.utils.market_hours import MarketHoursChecker
            if not MarketHoursChecker.is_ticker_tradeable(state.symbol):
                state.trade_execution = TradeExecution(
                    order_id=None,
                    status="skipped",
                    filled_price=None,
                    filled_quantity=None,
                    commission=None,
                    execution_time=datetime.utcnow(),
                    broker_response={"reason": f"Market is closed for {state.symbol}"},
                )
                self.log(state, f"⚠️ Market is closed for {state.symbol} - skipping trade execution")
                self.record_report(
                    state,
                    title="Trade execution skipped - market closed",
                    summary=f"Market is closed for {state.symbol}",
                    status="skipped",
                    data={"symbol": state.symbol, "reason": "Market hours check failed"},
                )
                state.should_complete = True
                return state
        except Exception as e:
            self.logger.warning(f"Market hours check failed: {str(e)} - proceeding with execution")
            # If market hours check fails, proceed (fail-safe)
        
        # Check senior trader review (always present — injected by executor)
        if state.trade_review is not None and state.trade_review.decision == "REJECTED":
            state.trade_execution = TradeExecution(
                order_id=None,
                status="rejected",
                filled_price=None,
                filled_quantity=None,
                commission=None,
                execution_time=None,
                broker_response={"reason": f"Rejected by senior trader review: {state.trade_review.reasoning}"}
            )
            self.log(state, f"❌ Senior trader review rejected trade: {state.trade_review.reasoning[:100]}")
            self.record_report(
                state,
                title="Trade rejected by senior trader review",
                summary=state.trade_review.reasoning,
                status="warning",
                data={
                    "decision": state.trade_review.decision,
                    "key_concerns": state.trade_review.key_concerns,
                },
            )
            state.should_complete = True
            return state

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
        
        # ── Reset stale flags from previous monitoring cycles ──────────
        # When resuming from NEEDS_RECONCILIATION the pipeline_state may
        # still carry should_complete=True and a stale trade_outcome.
        # Clear them so this cycle starts fresh; they will only be set
        # again if this check actually determines the position is closed.
        state.should_complete = False
        state.communication_error = False
        state.trade_outcome = None
        
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
        order_rejected_or_cancelled = False
        
        if order_id and not trade_id:  # Only check if order not yet filled (no trade_id)
            # Check if the order is still pending (limit not filled yet)
            try:
                open_orders = broker.get_orders()
                for order in open_orders:
                    if order.order_id == order_id:
                        pending_order = order
                        break
                
                # If order_id exists but not found in open_orders, it might be rejected/cancelled
                # Check by trying to get all orders (including closed/rejected) if broker supports it
                if not pending_order:
                    # Try to check order status directly if broker supports it
                    # For now, we'll use has_active_symbol to check if there's any active order/position
                    # If has_active_symbol returns False, the order is likely rejected/cancelled
                    try:
                        has_active = broker.has_active_symbol(state.symbol)
                        if not has_active:
                            # No active position or order - order was likely rejected/cancelled
                            order_rejected_or_cancelled = True
                            self.log(state, f"⚠️ Order {order_id} not found in open orders and no active position - likely rejected/cancelled", level="warning")
                    except Exception as e:
                        self.log(state, f"⚠️ Could not verify order status: {str(e)}", level="warning")
                        # Continue monitoring - might be temporary API issue
                
                # Successfully checked - reset error counter
                if state.trade_execution:
                    state.trade_execution.api_error_count = 0
                    state.trade_execution.last_successful_check = datetime.now()
                    
            except Exception as e:
                self.log(state, f"❌ API error checking orders: {str(e)}", level="error")
                self._handle_api_error(state, f"Failed to check orders: {str(e)}")
                return state
        
        # STEP 1.5: Handle rejected/cancelled orders
        if order_rejected_or_cancelled:
            self.log(state, f"❌ Order {order_id} was rejected or cancelled - completing execution", level="warning")
            # Mark as cancelled with zero P&L
            if not state.trade_outcome:
                from app.schemas.pipeline_state import TradeOutcome
                state.trade_outcome = TradeOutcome(
                    status="cancelled",
                    pnl=0.0,
                    pnl_percent=0.0,
                    exit_reason=f"Order {order_id} was rejected or cancelled on broker",
                    exit_price=None,
                    entry_price=None,
                    closed_at=datetime.utcnow()
                )
            state.should_complete = True
            return state
        
        # STEP 2: If order is still pending, check if we should cancel it
        if pending_order:
            # ⚠️ BRACKET FIX: For bracket (OTOCO) orders, the parent order stays
            # in open_orders even after the entry leg fills (because TP/SL legs are
            # still active). Before treating this as a "pending" order, check if a
            # position already exists — if so, the entry has filled and we should
            # transition to position monitoring instead of applying stale timeouts.
            is_bracket_order = False
            if state.trade_execution and state.trade_execution.broker_response:
                order_type = state.trade_execution.broker_response.get("order_type", "")
                is_bracket_order = "bracket" in order_type.lower()

            if is_bracket_order:
                bracket_pos_result, bracket_pos_data = self._get_position(state.symbol, broker_tool)
                if bracket_pos_result == PositionCheckResult.FOUND:
                    self.log(
                        state,
                        f"🔄 Bracket entry filled — position found for {state.symbol}. "
                        f"Switching to position monitoring (skipping stale-order timeout)."
                    )
                    if state.trade_execution:
                        state.trade_execution.status = "filled"
                        # Update filled_price/filled_quantity from the actual
                        # position data — the limit price on the order may differ
                        # from the actual fill price.
                        if bracket_pos_data:
                            if bracket_pos_data.get("avg_entry_price"):
                                state.trade_execution.filled_price = bracket_pos_data["avg_entry_price"]
                            if bracket_pos_data.get("qty"):
                                state.trade_execution.filled_quantity = bracket_pos_data["qty"]
                    # Clear pending_order so we fall through to position monitoring
                    pending_order = None

            # Only run stale-order / price-based cancellation for truly pending orders
            if not pending_order:
                # Bracket entry detected as filled above — skip to position monitoring
                self.log(state, f"📋 Bracket order {order_id} entry filled — proceeding to position check")
            else:
                self.log(state, f"📋 Limit order still pending: {order_id}")

        if pending_order:
            should_cancel = False
            cancel_reason = None
            current_price = 0.0
            entry = 0.0
            stop_loss = None
            take_profit = None
            price_precision = self._get_price_precision(state.symbol)

            # TIME-BASED CANCELLATION: Cancel stale limit orders
            # Default: 1 hour max wait time for limit order to fill
            max_pending_hours = float(self.config.get("max_pending_hours", 1))
            if state.trade_execution and state.trade_execution.execution_time:
                order_age = (datetime.utcnow() - state.trade_execution.execution_time).total_seconds() / 3600
                if order_age > max_pending_hours:
                    should_cancel = True
                    cancel_reason = f"Limit order pending for {order_age:.1f}h (max: {max_pending_hours}h) - stale order timeout"
                    self.log(state, f"⏰ Order age: {order_age:.1f}h exceeds max {max_pending_hours}h")
            
            # PRICE-BASED CANCELLATION: Check if setup is invalidated
            if not should_cancel and state.strategy and state.strategy.entry_price:
                current_price, price_error = self._get_current_price(state.symbol, broker)
                
                if price_error:
                    self.log(state, f"❌ Failed to get current price: {price_error}", level="error")
                    self._handle_api_error(state, f"Failed to get price: {price_error}")
                    return state
                
                entry = state.strategy.entry_price
                stop_loss = state.strategy.stop_loss
                take_profit = state.strategy.take_profit
                
                # Debug logging: show price levels for diagnosis
                sl_str = f"{stop_loss:.{price_precision}f}" if stop_loss else "N/A"
                tp_str = f"{take_profit:.{price_precision}f}" if take_profit else "N/A"
                self.log(state, 
                    f"📊 Price check: current={current_price:.{price_precision}f}, "
                    f"entry={entry:.{price_precision}f}, "
                    f"SL={sl_str}, TP={tp_str}, "
                    f"action={state.strategy.action}")
                
                # CANCEL CONDITIONS:
                # 1. Price moved AWAY from entry and breached SL (setup invalidated)
                # 2. Price hit TP level without hitting entry first (missed entire move)
                
                if state.strategy.action == "BUY":
                    if stop_loss and current_price <= stop_loss:
                        should_cancel = True
                        cancel_reason = f"Price ${current_price:.{price_precision}f} breached stop loss ${stop_loss:.{price_precision}f} before filling entry ${entry:.{price_precision}f} - setup invalidated"
                    
                    elif take_profit and current_price >= take_profit:
                        should_cancel = True
                        cancel_reason = f"Price ${current_price:.{price_precision}f} reached take profit ${take_profit:.{price_precision}f} without filling entry ${entry:.{price_precision}f} - missed opportunity"
                
                elif state.strategy.action == "SELL":
                    if stop_loss and current_price >= stop_loss:
                        should_cancel = True
                        cancel_reason = f"Price ${current_price:.{price_precision}f} breached stop loss ${stop_loss:.{price_precision}f} before filling entry ${entry:.{price_precision}f} - setup invalidated"
                    
                    elif take_profit and current_price <= take_profit:
                        should_cancel = True
                        cancel_reason = f"Price ${current_price:.{price_precision}f} reached take profit ${take_profit:.{price_precision}f} without filling entry ${entry:.{price_precision}f} - missed opportunity"
                
                # CANDLE-BASED CANCELLATION: Check recent candle highs/lows
                # The spot-price check only sees the price at each 15-second interval.
                # If the SL/TP was breached between checks (or before monitoring started
                # but after the order was placed), we would miss it.  Fetch recent 1-min
                # candles and check the extreme values.
                if not should_cancel and (stop_loss or take_profit):
                    candle_breach = self._check_candle_breach(
                        symbol=state.symbol,
                        broker=broker,
                        action=state.strategy.action,
                        entry=entry,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        price_precision=price_precision,
                        state=state,
                    )
                    if candle_breach:
                        should_cancel = True
                        cancel_reason = candle_breach
                
            elif not should_cancel:
                self.log(state, f"⚠️ No strategy data available for cancel check (strategy={state.strategy is not None})", level="warning")
            
            # Execute cancellation if needed
            if should_cancel:
                # Get current price if not already fetched (for time-based cancellation)
                if current_price == 0.0:
                    current_price, _ = self._get_current_price(state.symbol, broker)
                    entry = state.strategy.entry_price if state.strategy else 0.0
                    stop_loss = state.strategy.stop_loss if state.strategy else None
                    take_profit = state.strategy.take_profit if state.strategy else None
                
                try:
                    self.log(state, f"🚨 Cancelling limit order: {cancel_reason}")
                    broker.cancel_order(order_id)
                    state.should_complete = True
                    
                    # Populate trade_outcome for cancelled order (limit never filled)
                    from app.schemas.pipeline_state import TradeOutcome
                    state.trade_outcome = TradeOutcome(
                        status="cancelled",  # Limit order was never filled
                        pnl=0.0,
                        pnl_percent=0.0,
                        exit_reason=cancel_reason,
                        exit_price=current_price,
                        entry_price=entry,
                        closed_at=datetime.now()
                    )
                    
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
                    "current_price": current_price if current_price > 0 else None,
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

            # Grace period: broker order books can be eventually consistent right after placement.
            # Avoid immediately treating the order as closed/cancelled on the first check.
            grace_seconds = 60
            execution_time = state.trade_execution.execution_time if state.trade_execution else None
            if execution_time:
                age_seconds = (datetime.utcnow() - execution_time).total_seconds()
                if age_seconds < grace_seconds:
                    self.log(
                        state,
                        f"⏳ Order {order_id} not visible yet (age {age_seconds:.0f}s). "
                        f"Waiting up to {grace_seconds}s before assuming cancellation."
                    )
                    self.record_report(
                        state,
                        title="Monitoring limit order",
                        summary=f"Order {order_id} not yet visible; waiting for broker sync",
                        status="pending",
                        data={
                            "symbol": state.symbol,
                            "order_id": order_id,
                            "order_status": "pending_sync",
                            "order_type": "limit",
                            "entry_price": state.strategy.entry_price if state.strategy else None,
                            "stop_loss": state.strategy.stop_loss if state.strategy else None,
                            "take_profit": state.strategy.take_profit if state.strategy else None,
                            "age_seconds": round(age_seconds, 1),
                        },
                    )
                    return state
        
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
            
            # Order was filled — update trade_execution status and trade_id
            just_filled = False
            if state.trade_execution and state.trade_execution.status in ('accepted', 'pending'):
                state.trade_execution.status = 'filled'
                just_filled = True
                self.log(state, f"✅ Limit order filled — position found for {state.symbol}")
            
            if not trade_id and position and 'trade_id' in position:
                self.log(state, f"✅ Discovered trade_id: {position['trade_id']}")
                if state.trade_execution:
                    state.trade_execution.trade_id = position['trade_id']
            
            # Log position status
            pnl_percent = ((position["unrealized_pl"] / position["cost_basis"]) * 100) if position.get("cost_basis") else 0
            self.log(state, f"Position: {position['qty']} shares @ {pnl_percent:+.2f}% P&L")
            
            # ── Update trailing-stop high-water mark (TP-020) ─────────
            unrealized_pl_for_trail = float(position.get("unrealized_pl", 0))
            if state.trade_execution and unrealized_pl_for_trail > state.trade_execution.high_water_pnl:
                state.trade_execution.high_water_pnl = unrealized_pl_for_trail

            # Evaluate all exit conditions
            should_close, reason = self._evaluate_exit_conditions(state, position)
            
            if should_close:
                self.log(state, f"🚨 Emergency exit triggered: {reason}")
                try:
                    self._close_position(state.symbol, broker_tool, reason)
                    state.should_complete = True
                    
                    unrealized_pl = position.get("unrealized_pl", 0)
                    current_price = position.get("current_price")
                    
                    # Populate trade_outcome for easy access in monitoring task
                    from app.schemas.pipeline_state import TradeOutcome
                    state.trade_outcome = TradeOutcome(
                        status="executed",  # Trade was executed and position was opened
                        pnl=unrealized_pl,
                        pnl_percent=pnl_percent,
                        exit_reason=reason,
                        exit_price=current_price,
                        entry_price=state.strategy.entry_price if state.strategy else None,
                        closed_at=datetime.now()
                    )
                    
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
                            "exit_price": current_price,
                            "entry_price": state.strategy.entry_price if state.strategy else None,
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

            # Build bracket leg summary for the monitoring report
            bracket_leg_summary = None
            if state.trade_execution and state.trade_execution.bracket_legs:
                bracket_leg_summary = [
                    {
                        "leg_id": bl.leg_id,
                        "role": bl.role,
                        "type": bl.type,
                        "status": bl.status,
                        "price": bl.price,
                        "avg_fill_price": bl.avg_fill_price,
                    }
                    for bl in state.trade_execution.bracket_legs
                ]
            
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
                    "trade_id": trade_id,
                    "bracket_legs": bracket_leg_summary,
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
            
            # ⚠️ FIX #3: Add "previously monitored" guard before marking as cancelled
            # Only mark as cancelled if we're confident the order was never filled.
            # If we previously found the position (even without trade_id), don't mark as cancelled
            # on a single NOT_FOUND result - it could be a transient API error.
            if order_id and not trade_id:
                # Check if this position was previously found (indicates it was active before)
                was_previously_found = False
                if state.trade_execution:
                    # If we have a last_successful_check, it means we successfully found the position before
                    # (even if we didn't extract trade_id, the position existed)
                    if state.trade_execution.last_successful_check:
                        was_previously_found = True
                    
                    # Also check if status was already "filled" (order was filled, position should exist)
                    if state.trade_execution.status == "filled":
                        was_previously_found = True
                    
                    # Check if we have filled_price or filled_quantity (indicates order was filled)
                    if (state.trade_execution.filled_price and state.trade_execution.filled_price > 0) or \
                       (state.trade_execution.filled_quantity and state.trade_execution.filled_quantity > 0):
                        was_previously_found = True
                
                if was_previously_found:
                    # Position was previously found but now missing.
                    # For bracket (OTOCO) orders, the position disappearing is EXPECTED
                    # when a SL/TP leg fills — the position is closed by the broker.
                    # We should immediately check the bracket order status rather than
                    # waiting for the next monitoring cycle.
                    has_bracket_legs = (
                        state.trade_execution
                        and state.trade_execution.bracket_legs
                        and len(state.trade_execution.bracket_legs) > 0
                    )

                    if has_bracket_legs:
                        self.log(
                            state,
                            f"📊 Position not found for {state.symbol} but bracket legs exist — "
                            f"checking if SL/TP leg filled on broker (order_id={order_id})",
                        )
                        # Don't return — fall through past this entire `if order_id and not trade_id`
                        # block to the broker P&L fetch section below.
                        pass  # handled below at "Position closed" section
                    else:
                        # Non-bracket order: could be a transient API error. Don't
                        # mark as cancelled yet — let the next monitoring check confirm.
                        self.log(
                            state,
                            f"⚠️ Position previously found but now missing for {state.symbol} "
                            f"(order_id={order_id}). This might be a transient API error. "
                            f"Will retry on next check.",
                            level="warning"
                        )
                        return state
                else:
                    # Position was never found - this is a legitimate "order never filled" scenario
                    # Only mark as cancelled if we're confident:
                    # 1. Order was placed (we have order_id)
                    # 2. Order was never filled (no trade_id, no filled_price, no previous successful check)
                    self.log(state, "⚠️ Limit order not found and no position opened - treating as unfilled")
                    if state.trade_execution:
                        state.trade_execution.status = "cancelled"  # Limit order was never filled
                    state.should_complete = True

                    # Set trade_outcome as "cancelled" (limit order never filled)
                    from app.schemas.pipeline_state import TradeOutcome
                    state.trade_outcome = TradeOutcome(
                        status="cancelled",  # Limit order was never filled
                        pnl=0.0,
                        pnl_percent=0.0,
                        exit_reason="Limit order never filled",
                        exit_price=None,
                        entry_price=state.strategy.entry_price if state.strategy else None,
                        closed_at=datetime.now()
                    )

                    self.record_report(
                        state,
                        title="Limit order not filled",
                        summary=f"{state.symbol} limit order was accepted but never filled",
                        status="skipped",  # This execution is being skipped (no actual trade)
                        data={
                            "symbol": state.symbol,
                            "reason": "Order not found in pending list and no position opened",
                            "order_id": order_id,
                            "trade_id": trade_id,
                            "entry_price": state.strategy.entry_price if state.strategy else None,
                            "stop_loss": state.strategy.stop_loss if state.strategy else None,
                            "take_profit": state.strategy.take_profit if state.strategy else None,
                            "checked_at": datetime.utcnow().isoformat(),
                        },
                    )
                    return state

            # Position closed (bracket orders worked or manually closed)
            self.log(state, "✓ Position closed - fetching realized P&L from broker")
            
            # ---------------------------------------------------------------
            # Broker is the SINGLE SOURCE OF TRUTH for P&L.
            # If we cannot get P&L from the broker, we mark as
            # NEEDS_RECONCILIATION — we never guess from cached data.
            # ---------------------------------------------------------------
            from app.schemas.pipeline_state import TradeOutcome
            
            id_for_display = trade_id or order_id or "N/A"
            if trade_id or order_id:
                try:
                    self.log(state, f"📊 Fetching realized P&L from broker (trade_id={trade_id}, order_id={order_id})")
                    trade_details = broker.get_trade_details(trade_id=trade_id, order_id=order_id)
                    
                    if trade_details and trade_details.get("found"):
                        broker_realized_pl = float(trade_details.get("realized_pl", 0))
                        broker_close_price = trade_details.get("close_price")
                        broker_open_price = trade_details.get("open_price")
                        broker_state = trade_details.get("state", "")

                        # ⚠️ SAFEGUARD: For Tradier (and similar brokers), get_trade_details()
                        # returns the ORDER status. A "filled" order maps to state="closed", but
                        # this means the ORDER is filled — NOT that the POSITION is closed.
                        # If we see state="closed" but no closing P&L and no exit price,
                        # the order was likely just the entry fill — mark for reconciliation
                        # rather than assuming the position is truly closed.
                        if broker_state == "closed" and broker_realized_pl == 0 and not broker_close_price:
                            self.log(
                                state,
                                f"⚠️ Broker reports state='closed' for {id_for_display} but "
                                f"realized_pl=0 and no close_price. This likely means the ORDER "
                                f"is filled (entry) but the POSITION closure was not confirmed. "
                                f"Marking as NEEDS_RECONCILIATION.",
                                level="warning"
                            )
                            state.should_complete = True
                            state.trade_outcome = TradeOutcome(
                                status="needs_reconciliation",
                                pnl=0.0,
                                pnl_percent=0.0,
                                exit_reason="Position not confirmed closed — needs reconciliation (order filled but no closing trade found)",
                                exit_price=None,
                                entry_price=broker_open_price or (state.strategy.entry_price if state.strategy else None),
                                closed_at=datetime.now()
                            )
                            self.record_report(
                                state,
                                title="Position needs reconciliation",
                                summary=f"{state.symbol} position status unclear — order filled but no closing trade data",
                                status="needs_reconciliation",
                                data={
                                    "symbol": state.symbol,
                                    "reason": "Order state='closed' (filled) but no realized P&L or exit price",
                                    "order_id": order_id,
                                    "trade_id": trade_id,
                                    "broker_state": broker_state,
                                },
                            )
                            return state

                        final_pnl = broker_realized_pl
                        exit_price = float(broker_close_price) if broker_close_price else None

                        # Calculate P&L percent from broker data
                        entry = broker_open_price or (state.strategy.entry_price if state.strategy else None)
                        if not entry and state.trade_execution:
                            entry = state.trade_execution.filled_price
                        final_pnl_percent = None
                        if entry and entry > 0 and exit_price:
                            final_pnl_percent = ((exit_price - entry) / entry) * 100

                        # Determine exit reason from bracket legs if available
                        exit_reason = "Position closed"
                        exit_via_leg = None
                        if broker_state == "closed":
                            broker_legs = trade_details.get("legs", [])
                            # Determine entry side from our own bracket_legs or
                            # from the trade_details (which resolved it from legs)
                            entry_side_for_exit = None
                            if state.trade_execution and state.trade_execution.bracket_legs:
                                for own_bl in state.trade_execution.bracket_legs:
                                    if own_bl.role == "entry":
                                        entry_side_for_exit = own_bl.side
                                        break
                            # Find a filled leg on the opposite side (= exit leg)
                            for bl in broker_legs:
                                bl_status = (bl.get("status", "") or "").lower()
                                bl_side = (bl.get("side", "") or "").lower()
                                if bl_status == "filled" and entry_side_for_exit and bl_side != entry_side_for_exit:
                                    bl_type = bl.get("type", "")
                                    if bl_type == "limit":
                                        exit_via_leg = "take-profit"
                                    elif bl_type == "stop":
                                        exit_via_leg = "stop-loss"
                                    else:
                                        exit_via_leg = bl_type
                                    break

                            if exit_via_leg:
                                exit_reason = f"Position closed by {exit_via_leg} (bracket order)"
                            else:
                                exit_reason = "Position closed by broker (SL/TP/manual)"

                        self.log(
                            state,
                            f"✅ Broker P&L for {id_for_display}: "
                            f"${broker_realized_pl:+.2f} | exit_price={exit_price} | "
                            f"state={broker_state} | exit_via={exit_via_leg or 'unknown'}"
                        )

                        # Update bracket_legs statuses from the fresh broker data
                        if state.trade_execution and state.trade_execution.bracket_legs:
                            broker_legs = trade_details.get("legs", [])
                            if broker_legs:
                                leg_status_map = {
                                    str(bl.get("leg_id", "")): bl.get("status", "")
                                    for bl in broker_legs
                                }
                                for bl in state.trade_execution.bracket_legs:
                                    if bl.leg_id in leg_status_map:
                                        bl.status = leg_status_map[bl.leg_id]
                                        # Update avg_fill_price if the leg is now filled
                                        for broker_bl in broker_legs:
                                            if str(broker_bl.get("leg_id", "")) == bl.leg_id:
                                                if broker_bl.get("avg_fill_price"):
                                                    bl.avg_fill_price = broker_bl["avg_fill_price"]
                                                break

                        state.should_complete = True
                        state.trade_outcome = TradeOutcome(
                            status="executed",
                            pnl=final_pnl,
                            pnl_percent=final_pnl_percent,
                            exit_reason=exit_reason,
                            exit_price=exit_price,
                            entry_price=entry,
                            closed_at=datetime.now()
                        )
                        
                        # Build bracket leg summary for the close report
                        close_leg_summary = None
                        if state.trade_execution and state.trade_execution.bracket_legs:
                            close_leg_summary = [
                                {
                                    "leg_id": bl.leg_id,
                                    "role": bl.role,
                                    "type": bl.type,
                                    "status": bl.status,
                                    "price": bl.price,
                                    "avg_fill_price": bl.avg_fill_price,
                                }
                                for bl in state.trade_execution.bracket_legs
                            ]

                        self.record_report(
                            state,
                            title="Position closed",
                            summary=f"{state.symbol} position closed | P&L: ${final_pnl:+.2f}" + (f" ({final_pnl_percent:+.2f}%)" if final_pnl_percent is not None else ""),
                            status="completed",
                            data={
                                "symbol": state.symbol,
                                "reason": exit_reason,
                                "exit_via": exit_via_leg,
                                "final_pnl": final_pnl,
                                "final_pnl_percent": final_pnl_percent,
                                "exit_price": exit_price,
                                "entry_price": entry,
                                "closed_at": datetime.now().isoformat(),
                                "order_id": order_id,
                                "trade_id": trade_id,
                                "bracket_legs": close_leg_summary,
                            },
                        )
                        return state
                    else:
                        # Trade not found on broker — mark for reconciliation
                        self.log(
                            state,
                            f"⚠️ {id_for_display} not found on broker — marking as NEEDS_RECONCILIATION",
                            level="warning"
                        )
                        state.should_complete = True
                        state.trade_outcome = TradeOutcome(
                            status="needs_reconciliation",
                            pnl=None,
                            pnl_percent=None,
                            exit_reason=f"{id_for_display} not found on broker — manual review required",
                            exit_price=None,
                            entry_price=state.strategy.entry_price if state.strategy else None,
                            closed_at=datetime.now()
                        )
                        self.record_report(
                            state,
                            title="Position closed — P&L unknown",
                            summary=f"{state.symbol} position closed but {id_for_display} not found on broker",
                            status="needs_reconciliation",
                            data={
                                "symbol": state.symbol,
                                "reason": f"{id_for_display} not found on broker",
                                "order_id": order_id,
                                "trade_id": trade_id
                            },
                        )
                        return state
                        
                except Exception as e:
                    # Broker API error — mark for reconciliation
                    self.log(
                        state,
                        f"⚠️ Failed to fetch trade details from broker: {str(e)} — "
                        f"marking as NEEDS_RECONCILIATION",
                        level="warning"
                    )
                    state.should_complete = True
                    state.trade_outcome = TradeOutcome(
                        status="needs_reconciliation",
                        pnl=None,
                        pnl_percent=None,
                        exit_reason=f"Cannot reach broker to fetch P&L: {str(e)}",
                        exit_price=None,
                        entry_price=state.strategy.entry_price if state.strategy else None,
                        closed_at=datetime.now()
                    )
                    self.record_report(
                        state,
                        title="Position closed — P&L unknown",
                        summary=f"{state.symbol} position closed but broker API failed: {str(e)}",
                        status="needs_reconciliation",
                        data={
                            "symbol": state.symbol,
                            "reason": f"Broker API error: {str(e)}",
                            "order_id": order_id,
                            "trade_id": trade_id
                        },
                    )
                    return state
            else:
                # No trade_id or order_id at all — mark for reconciliation
                self.log(
                    state,
                    "⚠️ No trade_id or order_id available — cannot fetch P&L from broker. "
                    "Marking as NEEDS_RECONCILIATION",
                    level="warning"
                )
                state.should_complete = True
                state.trade_outcome = TradeOutcome(
                    status="needs_reconciliation",
                    pnl=None,
                    pnl_percent=None,
                    exit_reason="No trade_id or order_id — cannot fetch P&L from broker",
                    exit_price=None,
                    entry_price=state.strategy.entry_price if state.strategy else None,
                    closed_at=datetime.now()
                )
                self.record_report(
                    state,
                    title="Position closed — P&L unknown",
                    summary=f"{state.symbol} position closed but no trade_id/order_id to fetch P&L",
                    status="needs_reconciliation",
                    data={
                        "symbol": state.symbol,
                        "reason": "No trade_id or order_id — cannot fetch P&L from broker",
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
            - FOUND: position exists, data included (with trade_id if available)
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
                position_dict = {
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
                
                # Extract trade_id from broker_data if available
                broker_data = position.broker_data or {}
                trade_id = None
                
                # ⚠️ FIX #2: Extract trade_id based on broker type
                # OANDA stores tradeIDs in the long/short position sections
                if hasattr(broker, '__class__') and 'Oanda' in broker.__class__.__name__:
                    side_key = "long" if position.side == "long" else "short"
                    side_data = broker_data.get(side_key, {})
                    trade_ids = side_data.get("tradeIDs", [])
                    if trade_ids:
                        # Use the first trade ID (most common case: single trade per position)
                        trade_id = str(trade_ids[0])
                
                # Tradier: Positions don't have individual trade IDs.
                # Check for any ID-like fields in broker position data.
                if not trade_id:
                    trade_id = (
                        broker_data.get("id") or
                        broker_data.get("position_id") or
                        broker_data.get("trade_id") or
                        broker_data.get("tradeID")
                    )
                    if trade_id:
                        trade_id = str(trade_id)
                
                if trade_id:
                    position_dict["trade_id"] = trade_id
                
                return (PositionCheckResult.FOUND, position_dict)
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
            
            # No position found - try to get quote for pending limit orders
            # (we need current price to check if order should be cancelled)
            self.logger.info(f"No position found for {symbol}, fetching quote instead")
            quote = broker.get_quote(symbol)
            
            if "error" in quote:
                error_msg = f"Failed to get quote for {symbol}: {quote['error']}"
                self.logger.error(error_msg)
                return (0.0, error_msg)
            
            # Use mid-price (average of bid/ask) or 'last' price
            price = quote.get("last") or ((quote.get("bid", 0) + quote.get("ask", 0)) / 2)
            
            if price <= 0:
                return (0.0, f"Invalid quote price for {symbol}: {price}")
            
            self.logger.info(f"Got current price for {symbol}: {price}")
            return (price, None)
            
        except Exception as e:
            error_msg = f"API error getting current price for {symbol}: {str(e)}"
            self.logger.error(error_msg)
            return (0.0, error_msg)
    
    def _extract_bracket_legs(
        self,
        broker_data: Dict[str, Any],
        action: str,
        symbol: str,
        entry_price: float,
    ) -> Optional[List[BracketLeg]]:
        """
        Extract individual leg order IDs from a bracket (OTOCO) order response.

        Tradier OTOCO responses include a ``leg`` array with child order IDs for
        the entry, take-profit, and stop-loss legs. Storing these allows the
        monitoring loop to check individual leg statuses and reliably detect
        when a SL/TP leg fills (= position closure).

        Returns:
            List of BracketLeg objects, or None if no legs found.
        """
        legs_raw = broker_data.get("leg", [])
        if isinstance(legs_raw, dict):
            legs_raw = [legs_raw]
        if not legs_raw:
            return None

        entry_side = action.lower()  # "buy" or "sell"
        exit_side = "sell" if entry_side == "buy" else "buy"

        bracket_legs: List[BracketLeg] = []
        for leg in legs_raw:
            leg_id = str(leg.get("id", ""))
            leg_side = (leg.get("side", "") or "").lower()
            leg_type = (leg.get("type", "") or "").lower()
            leg_status = (leg.get("status", "") or "").lower()
            leg_qty = float(leg.get("quantity", 0))
            leg_fill = float(leg.get("avg_fill_price", 0)) if leg.get("avg_fill_price") else None
            leg_price = float(leg.get("price", 0)) if leg.get("price") else None
            leg_stop = float(leg.get("stop_price", 0)) if leg.get("stop_price") else None

            # Determine role based on side and type
            if leg_side == entry_side:
                role = "entry"
                price_val = leg_price  # limit price for limit entries
            elif leg_type == "limit":
                role = "take_profit"
                price_val = leg_price
            elif leg_type == "stop":
                role = "stop_loss"
                price_val = leg_stop
            else:
                role = "exit"  # fallback
                price_val = leg_price or leg_stop

            bracket_legs.append(BracketLeg(
                leg_id=leg_id,
                role=role,
                type=leg_type,
                side=leg_side,
                status=leg_status,
                quantity=leg_qty,
                price=price_val,
                avg_fill_price=leg_fill,
            ))

        return bracket_legs if bracket_legs else None

    def _get_price_precision(self, symbol: str) -> int:
        """
        Get the price precision (decimal places) for a symbol.
        
        Forex pairs typically use 5 decimal places, stocks use 2.
        """
        # Forex symbols typically have underscore (e.g., EUR_USD)
        if "_" in symbol or "/" in symbol:
            return 5
        return 2
    
    def _check_candle_breach(
        self,
        symbol: str,
        broker,
        action: str,
        entry: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        price_precision: int,
        state: PipelineState,
    ) -> Optional[str]:
        """
        Check recent candle highs/lows for SL/TP breaches that the spot-price
        check might have missed.

        The spot-price check runs every ~15 seconds and only sees the price at
        that instant.  A spike that breaches SL or TP and then retraces would
        be invisible.  By fetching the last few 1-minute candles we can detect
        if the extreme (high or low) crossed the SL/TP threshold.

        Returns:
            A cancel reason string if a breach is detected, or None.
        """
        try:
            candles = broker.get_recent_candles(symbol, granularity="M1", count=5)
        except Exception as e:
            self.logger.warning(
                "candle_breach_check_failed",
                symbol=symbol,
                error=str(e),
            )
            return None

        if not candles:
            self.logger.debug("candle_breach_no_data", symbol=symbol)
            return None

        for candle in candles:
            high = candle.get("high", 0)
            low = candle.get("low", 0)
            candle_time = candle.get("time", "?")

            if action == "BUY":
                # BUY limit: SL is below entry. If candle low <= SL → invalidated.
                if stop_loss and low <= stop_loss:
                    reason = (
                        f"Candle low {low:.{price_precision}f} at {candle_time} breached "
                        f"stop loss {stop_loss:.{price_precision}f} before filling entry "
                        f"{entry:.{price_precision}f} - setup invalidated (candle check)"
                    )
                    self.log(state, f"📉 {reason}", level="warning")
                    return reason
                # If candle high >= TP → missed the move.
                if take_profit and high >= take_profit:
                    reason = (
                        f"Candle high {high:.{price_precision}f} at {candle_time} reached "
                        f"take profit {take_profit:.{price_precision}f} without filling entry "
                        f"{entry:.{price_precision}f} - missed opportunity (candle check)"
                    )
                    self.log(state, f"📈 {reason}", level="warning")
                    return reason

            elif action == "SELL":
                # SELL limit: SL is above entry. If candle high >= SL → invalidated.
                if stop_loss and high >= stop_loss:
                    reason = (
                        f"Candle high {high:.{price_precision}f} at {candle_time} breached "
                        f"stop loss {stop_loss:.{price_precision}f} before filling entry "
                        f"{entry:.{price_precision}f} - setup invalidated (candle check)"
                    )
                    self.log(state, f"📈 {reason}", level="warning")
                    return reason
                # If candle low <= TP → missed the move.
                if take_profit and low <= take_profit:
                    reason = (
                        f"Candle low {low:.{price_precision}f} at {candle_time} reached "
                        f"take profit {take_profit:.{price_precision}f} without filling entry "
                        f"{entry:.{price_precision}f} - missed opportunity (candle check)"
                    )
                    self.log(state, f"📉 {reason}", level="warning")
                    return reason

        self.log(
            state,
            f"✅ Candle check OK: no SL/TP breach in last {len(candles)} candles",
            level="info",
        )
        return None

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
        
        # ── Real HTTP delivery with retries (TP-019) ──────────────────
        url = (
            webhook_tool.get("url") or
            webhook_tool.get("webhook_url") or
            self.config.get("webhook_url", "")
        )

        delivery_status = "skipped"
        delivery_error  = None
        delivery_attempts = 0

        if url:
            from app.utils.webhook import WebhookDelivery
            extra_headers: dict = {}
            secret = webhook_tool.get("secret") or webhook_tool.get("auth_token")
            if secret:
                extra_headers["Authorization"] = f"Bearer {secret}"

            delivery = WebhookDelivery(timeout_s=10.0, max_retries=3)
            receipt  = delivery.send(url, payload, headers=extra_headers or None)

            delivery_status   = receipt.status
            delivery_error    = receipt.error
            delivery_attempts = receipt.attempts

            if receipt.status == "delivered":
                self.log(state, f"✓ Webhook delivered to {url} (attempt {receipt.attempts})")
            else:
                self.log(
                    state,
                    f"⚠️ Webhook delivery failed after {receipt.attempts} attempts: {receipt.error}",
                    level="warning",
                )
                self.add_warning(state, f"Webhook delivery failed: {receipt.error}")
        else:
            self.log(state, "⚠️ No webhook URL configured — skipping delivery", level="warning")

        state.trade_execution = TradeExecution(
            order_id=f"WEBHOOK-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            status=delivery_status,
            filled_price=None,
            filled_quantity=None,
            commission=None,
            execution_time=datetime.utcnow(),
            broker_response={
                "webhook": delivery_status,
                "url": url,
                "attempts": delivery_attempts,
                "error": delivery_error,
                "payload": payload,
            }
        )

        summary = (
            f"{strategy.action} {state.symbol} via webhook ({delivery_status})"
            if url else
            f"{strategy.action} {state.symbol} — no webhook URL configured"
        )
        self.log(state, f"✓ Webhook {delivery_status}")
        self.record_report(
            state,
            title="Webhook delivery",
            summary=summary,
            status="completed" if delivery_status == "delivered" else "warning",
            data={**payload, "delivery_status": delivery_status, "attempts": delivery_attempts},
        )
        
        # Webhook completes immediately (no monitoring)
        return state

    def _execute_backtest_trade(self, state: PipelineState) -> PipelineState:
        """Simulate trade entry through the backtest broker and complete immediately."""
        from app.backtesting.backtest_broker import BacktestBroker

        if not state.risk_assessment or not state.strategy:
            state.trade_execution = TradeExecution(
                order_id=None,
                status="skipped",
                execution_time=datetime.utcnow(),
                broker_response={"reason": "Missing risk assessment or strategy"},
            )
            state.should_complete = True
            return state

        strategy = state.strategy
        risk = state.risk_assessment
        if strategy.action == "HOLD" or not risk.approved:
            state.trade_execution = TradeExecution(
                order_id=None,
                status="skipped",
                execution_time=datetime.utcnow(),
                broker_response={"reason": "Trade not approved or HOLD action"},
            )
            state.should_complete = True
            return state

        broker = BacktestBroker(
            run_id=state.backtest_run_id,
            initial_capital=10_000.0,
        )
        if state.symbol in broker.get_positions():
            state.trade_execution = TradeExecution(
                order_id=None,
                status="skipped",
                execution_time=datetime.utcnow(),
                broker_response={"reason": f"Position already open for {state.symbol}"},
            )
            state.should_complete = True
            return state
        position = broker.open_position(
            symbol=state.symbol,
            action=strategy.action,
            qty=risk.position_size,
            entry_price=float(strategy.entry_price or (state.market_data.current_price if state.market_data else 0.0)),
            stop_loss=strategy.stop_loss,
            take_profit=strategy.take_profit,
            execution_id=str(state.execution_id),
            metadata={
                "strategy_family": getattr(getattr(strategy, "strategy_spec", None), "strategy_family", ""),
                "signal_entry_price": float(strategy.entry_price or 0.0),
            },
        )
        state.trade_execution = TradeExecution(
            order_id=str(state.execution_id),
            status="filled",
            filled_price=float(position["entry_price"]),
            filled_quantity=float(position["qty"]),
            commission=float(position["commission"]),
            execution_time=datetime.utcnow(),
            broker_response={"broker": "BacktestBroker", "symbol": state.symbol},
        )
        state.should_complete = True
        self.record_report(
            state,
            title="Backtest trade executed",
            summary=f"Simulated {strategy.action} for {state.symbol}",
            status="completed",
            data={"symbol": state.symbol, "backtest_run_id": state.backtest_run_id},
        )
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
            for existing_order in existing_orders:
                if existing_order.symbol == state.symbol or existing_order.symbol.replace("_", "/") == state.symbol.replace("_", "/"):
                    self.log(state, f"⚠️ Duplicate order detected: {existing_order.order_id} for {state.symbol}")
                    state.trade_execution = TradeExecution(
                        order_id=None,
                        status="skipped",
                        filled_price=None,
                        filled_quantity=None,
                        commission=None,
                        execution_time=datetime.utcnow(),
                        broker_response={"reason": f"Duplicate order exists: {existing_order.order_id}"}
                    )
                    self.record_report(
                        state,
                        title="Trade skipped - duplicate order",
                        summary=f"Skipped {strategy.action} for {state.symbol} - open order already exists",
                        status="skipped",
                        data={"reason": "Duplicate open order detected", "existing_order_id": existing_order.order_id},
                    )
                    return state
            
            # ── Session-aware execution gate (TP-021) ─────────────────
            session_rejection = self._check_session_execution_policy(state)
            if session_rejection:
                self.log(state, f"⏸️ Execution blocked by session policy: {session_rejection}")
                state.trade_execution = TradeExecution(
                    order_id=None,
                    status="skipped",
                    filled_price=None,
                    filled_quantity=None,
                    commission=None,
                    execution_time=datetime.utcnow(),
                    broker_response={"reason": session_rejection},
                )
                self.record_report(
                    state,
                    title="Trade skipped — session policy",
                    summary=session_rejection,
                    status="skipped",
                    data={"reason": session_rejection},
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

            # ── Pre-trade execution filters (TP-022) ──────────────────
            quote_data = {}
            if state.market_data:
                quote_data = {
                    "bid": state.market_data.bid,
                    "ask": state.market_data.ask,
                }
            filter_result = self._run_pre_trade_filter(state, float(entry or 0), quote_data)
            if not filter_result.passed:
                self.log(state, f"🚫 Pre-trade filter rejected: {filter_result.rejection_reason}")
                state.trade_execution = TradeExecution(
                    order_id=None,
                    status="skipped",
                    filled_price=None,
                    filled_quantity=None,
                    commission=None,
                    execution_time=datetime.utcnow(),
                    broker_response={"reason": filter_result.rejection_reason, "checks": filter_result.checks},
                )
                self.record_report(
                    state,
                    title="Trade skipped — pre-trade filter",
                    summary=filter_result.rejection_reason or "Pre-trade filter rejected",
                    status="skipped",
                    data={"checks": filter_result.checks},
                )
                return state
            
            # Determine price precision for logging
            is_forex = "_" in state.symbol
            price_precision = 5 if is_forex else 2
            
            # ⚠️ FIX #2: Enter monitoring mode BEFORE placing order to prevent orphaned orders
            # This ensures that even if worker crashes after broker API call, the execution
            # will be in MONITORING status and can be reconciled later
            state.execution_phase = "monitoring"
            state.monitor_interval_minutes = 0.25  # Check every 15 seconds
            
            # Now place the order with broker
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
            
            # Extract trade_id from broker response if available
            # (Oanda may return tradeOpenedID or tradeID in fill transactions)
            broker_trade_id = None
            broker_data = order.broker_data or {}
            
            # Check orderFillTransaction for immediate fills (market orders or limit fills)
            fill_txn = broker_data.get("orderFillTransaction", {})
            if fill_txn:
                # Oanda returns tradeOpened with tradeID for new positions
                trade_opened = fill_txn.get("tradeOpened", {})
                if trade_opened:
                    broker_trade_id = str(trade_opened.get("tradeID", ""))
            
            # Also check for tradeID in the order create transaction itself
            if not broker_trade_id:
                broker_trade_id = broker_data.get("tradeID") or broker_data.get("trade_id")
            
            # Store execution result
            state.trade_execution = TradeExecution(
                order_id=order.order_id,
                trade_id=broker_trade_id or None,  # Set if available (market fills)
                status=order.status.value,
                filled_price=order.filled_price or entry,
                filled_quantity=order.filled_qty or risk.position_size,
                commission=self._extract_commission(order.broker_data or {}),
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

            # ── Extract bracket (OTOCO) leg order IDs for monitoring ─────
            # When a bracket order is placed, the broker response contains
            # child leg order IDs for SL and TP. Store them so monitoring
            # can check individual leg statuses for reliable closure detection.
            if has_targets and order.broker_data:
                bracket_legs = self._extract_bracket_legs(
                    order.broker_data, strategy.action, state.symbol, entry
                )
                if bracket_legs:
                    state.trade_execution.bracket_legs = bracket_legs
                    leg_ids = [f"{l.role}={l.leg_id}" for l in bracket_legs]
                    self.log(state, f"  Bracket legs tracked: {', '.join(leg_ids)}")
            
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
                summary=f"{strategy.action} {risk.position_size:.0f} {state.symbol} @ ${entry:.{price_precision}f} ({order_type_used.upper()})",
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
                    "trade_id": broker_trade_id,  # May be None for limit orders until filled
                    "broker": broker.__class__.__name__
                },
            )
            
            # 📱 Send Telegram notification if configured
            self._send_trade_notification(state, strategy, risk, entry, take_profit, stop_loss)
            
            return state
            
        except Exception as e:
            self.logger.error(f"Broker trade execution failed: {str(e)}", exc_info=True)
            
            # ⚠️ FIX #2: If we already entered monitoring (before or after order placement),
            # preserve that state so the executor transitions to MONITORING and doesn't orphan
            # the order. The monitoring task will detect and handle the issue.
            if state.execution_phase == "monitoring":
                self.log(state, f"⚠️ Post-order error but already in MONITORING mode — keeping monitoring state: {str(e)}", level="warning")
                
                # Ensure trade_execution is created so monitoring knows there was an attempt
                if not state.trade_execution:
                    state.trade_execution = TradeExecution(
                        order_id=None,  # Unknown if order was placed
                        status="unknown",
                        filled_price=None,
                        filled_quantity=None,
                        commission=None,
                        execution_time=datetime.utcnow(),
                        broker_response={
                            "warning": f"Error during/after order placement: {str(e)}",
                            "monitoring_will_reconcile": True
                        }
                    )
                
                self.record_report(
                    state,
                    title="Trade executed (with errors - monitoring active)",
                    summary=f"Error occurred during order placement for {state.symbol}, monitoring will reconcile",
                    status="monitoring",
                    data={"warning": str(e), "monitoring_active": True},
                )
                return state
            
            # Order was NOT placed (error before setting monitoring phase) — safe to mark as failed
            state.trade_execution = TradeExecution(
                order_id=None,
                status="rejected",
                filled_price=None,
                filled_quantity=None,
                commission=None,
                execution_time=datetime.utcnow(),
                broker_response={"error": str(e)}
            )
            
            # Set trade_outcome as "failed" (broker call failed)
            from app.schemas.pipeline_state import TradeOutcome
            state.trade_outcome = TradeOutcome(
                status="failed",  # Broker call failed
                pnl=None,
                pnl_percent=None,
                exit_reason=f"Broker execution failed: {str(e)}",
                exit_price=None,
                entry_price=state.strategy.entry_price if state.strategy else None,
                closed_at=datetime.now()
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
        Evaluate all exit conditions during position monitoring (TP-020/TP-024).

        Checks (in priority order):
          1. Manual EMERGENCY_EXIT signal
          2. Break-even soft stop (TP-020)
          3. Trailing stop (TP-020)
          4. Session / EOD time stop (TP-020)
          5. VIX spike (TP-024)
          6. SPY market crash (TP-024)

        Returns:
            (should_close, reason)  — reason is "" when should_close is False
        """
        instructions = self.config.get("instructions", "").lower()
        current_price = float(position.get("current_price") or 0)
        unrealized_pl = float(position.get("unrealized_pl", 0))
        entry_price   = float(
            (state.strategy.entry_price if state.strategy else None) or
            position.get("avg_entry_price", 0) or
            current_price
        )
        action = (state.strategy.action if state.strategy else None) or position.get("side", "")

        # ── 1. Manual emergency signal ────────────────────────────────
        if state.signal_data and state.signal_data.signal_type == "EMERGENCY_EXIT":
            return True, "Manual emergency signal received"

        # ── 2. Break-even soft stop (TP-020) ─────────────────────────
        # Arm break-even once the position reaches the configured R multiple.
        # After that, if unrealized P&L drops to zero (or below), close the position
        # to protect the trade from a winner turning into a loser.
        be_r = self._parse_float_instruction(instructions, r'break.?even\s+(?:at\s+)?(\d+(?:\.\d+)?)r', default=None)
        if be_r is not None and entry_price > 0 and state.trade_execution:
            stop_price = (state.strategy.stop_loss if state.strategy else 0) or 0
            initial_risk = abs(entry_price - stop_price) * float(
                (state.trade_execution.filled_quantity or 0)
            )
            if initial_risk > 0:
                r_achieved = unrealized_pl / initial_risk
                # Arm once we reach the threshold
                if r_achieved >= be_r and not state.trade_execution.break_even_armed:
                    state.trade_execution.break_even_armed = True
                    self.log(state, f"🎯 Break-even armed at {r_achieved:.2f}R (threshold {be_r}R)")
                # Once armed, close if P&L drops to break-even or below
                if state.trade_execution.break_even_armed and unrealized_pl <= 0:
                    return True, f"Break-even stop triggered — position at or below entry after reaching {be_r}R"

        # ── 3. Trailing stop (TP-020) ────────────────────────────────
        # Parse: "trail 1.5%" or "trailing stop 2%"
        trail_pct = self._parse_float_instruction(instructions, r'trail(?:ing)?\s+(?:stop\s+)?(\d+(?:\.\d+)?)\s*%', default=None)
        if trail_pct is not None and state.trade_execution and current_price > 0:
            # Update high-water mark
            if unrealized_pl > state.trade_execution.high_water_pnl:
                state.trade_execution.high_water_pnl = unrealized_pl

            # Trail in dollar terms: drop from high-water mark > trail_pct of entry
            trail_drop_threshold = entry_price * (trail_pct / 100) * float(
                (state.trade_execution.filled_quantity or 1)
            )
            drawdown_from_peak = state.trade_execution.high_water_pnl - unrealized_pl
            if (
                state.trade_execution.high_water_pnl > 0
                and drawdown_from_peak >= trail_drop_threshold
            ):
                return (
                    True,
                    f"Trailing stop triggered: pullback of ${drawdown_from_peak:.2f} "
                    f"exceeds {trail_pct:.1f}% trail from peak P&L ${state.trade_execution.high_water_pnl:.2f}",
                )

        # ── 4. Session / EOD time stop (TP-020) ──────────────────────
        # Parse: "close by 3:55pm ET" or "exit before 15:55"
        eod_close = self._check_session_time_stop(instructions)
        if eod_close:
            return True, eod_close

        # ── 5. VIX spike (TP-024) ────────────────────────────────────
        vix_match = re.search(r'vix\s*[>]\s*(\d+)', instructions)
        if vix_match:
            vix_threshold = float(vix_match.group(1))
            snap = self._fetch_market_snapshot()
            triggered, reason = self._check_vix(snap, vix_threshold)
            if triggered:
                return True, reason

        # ── 6. SPY market crash (TP-024) ─────────────────────────────
        if "market crash" in instructions or "spy" in instructions:
            crash_pct = self._parse_float_instruction(
                instructions, r'spy\s*[<]\s*(-?\d+(?:\.\d+)?)\s*%', default=-3.0
            )
            snap = self._fetch_market_snapshot()
            triggered, reason = self._check_spy_crash(snap, crash_pct)
            if triggered:
                return True, reason

        return False, ""

    # ------------------------------------------------------------------
    # Exit condition helpers (TP-020 / TP-024)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_float_instruction(text: str, pattern: str, default) -> Optional[float]:
        """Extract a float from instructions text using a regex pattern."""
        m = re.search(pattern, text)
        if m:
            try:
                return float(m.group(1))
            except (ValueError, IndexError):
                pass
        return default

    @staticmethod
    def _check_session_time_stop(instructions: str) -> Optional[str]:
        """
        Return a close reason if the current ET time is past the configured exit time.

        Parses patterns like "close by 3:55pm", "exit before 15:55", "eod exit 3:50pm".
        """
        import re
        from datetime import datetime
        from zoneinfo import ZoneInfo

        et = ZoneInfo("America/New_York")
        now_et = datetime.now(tz=et)

        # Match "close/exit by/before HH:MMam/pm" or "HH:MM" 24h
        patterns = [
            r'(?:close|exit|eod)\s+(?:by|before|at)?\s*(\d{1,2}):(\d{2})\s*(am|pm)?',
            r'(?:close|exit)\s+(?:eod|end.of.day)',
        ]

        for pat in patterns:
            m = re.search(pat, instructions)
            if m:
                if m.lastindex and m.lastindex >= 2:
                    hour, minute = int(m.group(1)), int(m.group(2))
                    ampm = m.group(3) if m.lastindex >= 3 else None
                    if ampm == "pm" and hour < 12:
                        hour += 12
                    elif ampm == "am" and hour == 12:
                        hour = 0
                    from datetime import time as dt_time
                    exit_time = dt_time(hour, minute)
                    if now_et.time() >= exit_time:
                        return (
                            f"Session time stop: past configured exit time "
                            f"{hour:02d}:{minute:02d} ET (now {now_et.strftime('%H:%M')} ET)"
                        )
                else:
                    # Generic "eod" match — 3:55 PM ET default
                    from datetime import time as dt_time
                    if now_et.time() >= dt_time(15, 55):
                        return "EOD time stop: after 3:55 PM ET"

        return None

    def _fetch_market_snapshot(self):
        """Synchronously fetch VIX/SPY snapshot (TP-024)."""
        try:
            import asyncio
            from app.utils.market_context import get_market_snapshot
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                        return ex.submit(asyncio.run, get_market_snapshot()).result()
                return loop.run_until_complete(get_market_snapshot())
            except RuntimeError:
                return asyncio.run(get_market_snapshot())
        except Exception:
            from app.utils.market_context import MarketSnapshot
            return MarketSnapshot()

    @staticmethod
    def _check_vix(snap, threshold: float) -> tuple[bool, str]:
        from app.utils.market_context import check_vix_spike
        return check_vix_spike(snap, threshold)

    @staticmethod
    def _check_spy_crash(snap, threshold_pct: float) -> tuple[bool, str]:
        from app.utils.market_context import check_spy_crash
        return check_spy_crash(snap, threshold_pct)
    
    # ------------------------------------------------------------------
    # Session-aware execution (TP-021)
    # ------------------------------------------------------------------

    def _check_session_execution_policy(self, state) -> Optional[str]:
        """
        Block new entries during unfavourable sessions based on config.

        Returns a rejection string if execution should be skipped, else None.

        Config keys checked:
            no_entry_sessions : list[str] — sessions to block (default ["lunch", "after_hours"])
            no_entry_after    : "HH:MM" 24h ET — no new entries after this time

        Sessions match RegimeContext labels: pre_market | regular | lunch | power_hour | after_hours
        """
        from datetime import datetime, time as dt_time
        from zoneinfo import ZoneInfo

        et = ZoneInfo("America/New_York")
        now_et = datetime.now(tz=et)

        # ── No-entry-after time ───────────────────────────────────────
        no_entry_after = self.config.get("no_entry_after", "")
        if no_entry_after:
            try:
                h, m = map(int, no_entry_after.split(":"))
                if now_et.time() >= dt_time(h, m):
                    return f"Session policy: no new entries after {no_entry_after} ET (now {now_et.strftime('%H:%M')} ET)"
            except (ValueError, AttributeError):
                pass  # Invalid config — don't block

        # ── Blocked sessions ─────────────────────────────────────────
        blocked = self.config.get("no_entry_sessions", ["lunch", "after_hours", "pre_market"])
        if isinstance(blocked, str):
            blocked = [s.strip() for s in blocked.split(",")]

        current_session = self._current_et_session(now_et)

        if current_session and current_session in blocked:
            return (
                f"Session policy: no new entries during '{current_session}' session "
                f"(blocked sessions: {', '.join(blocked)})"
            )

        return None

    @staticmethod
    def _current_et_session(now_et) -> str:
        """Map current ET time to a session label matching RegimeContext.session."""
        from datetime import time as dt_time
        t = now_et.time()
        if dt_time(4, 0) <= t < dt_time(9, 30):
            return "pre_market"
        if dt_time(9, 30) <= t < dt_time(12, 0):
            return "regular"
        if dt_time(12, 0) <= t < dt_time(14, 0):
            return "lunch"
        if dt_time(14, 0) <= t < dt_time(16, 0):
            return "power_hour"
        if dt_time(16, 0) <= t < dt_time(20, 0):
            return "after_hours"
        return "after_hours"

    # ------------------------------------------------------------------
    # Pre-trade filter (TP-022)
    # ------------------------------------------------------------------

    def _run_pre_trade_filter(self, state, entry_price: float, quote_data: dict):
        """Run pre-trade spread/volume/volatility filters before placing order."""
        from app.utils.pre_trade_filter import PreTradeFilter, parse_filter_config_from_instructions
        instructions = self.config.get("instructions", "")
        filter_config = {**self.config, **parse_filter_config_from_instructions(instructions)}
        f = PreTradeFilter(filter_config)
        return f.check(
            symbol=state.symbol,
            entry_price=entry_price,
            market_data=quote_data or {},
        )

    # ------------------------------------------------------------------
    # Commission extraction (TP-023)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_commission(broker_data: dict) -> float:
        """
        Extract commission from the broker's order fill data.

        Tries multiple field names used by different brokers:
          - Alpaca: broker_data["commission"]
          - OANDA:  broker_data["orderFillTransaction"]["commission"]
          - Tradier: broker_data["order"]["commission"]
        Returns 0.0 if not available.
        """
        try:
            # Direct field
            if "commission" in broker_data:
                return float(broker_data["commission"] or 0)
            # OANDA fill transaction
            fill = broker_data.get("orderFillTransaction", {})
            if fill and "commission" in fill:
                return abs(float(fill["commission"] or 0))
            # Tradier / generic nested
            order = broker_data.get("order", {})
            if order and "commission" in order:
                return float(order["commission"] or 0)
        except (TypeError, ValueError):
            pass
        return 0.0

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
    
    def _send_trade_notification(
        self, 
        state: PipelineState, 
        strategy, 
        risk, 
        entry_price: float,
        take_profit: Optional[float],
        stop_loss: Optional[float]
    ):
        """
        Send Telegram notification for trade execution.
        
        Only sends if:
        1. User has Telegram enabled
        2. Pipeline has notifications enabled
        3. "trade_executed" is in notification events
        """
        try:
            # Import here to avoid circular dependency
            from app.services.telegram_notifier import telegram_notifier
            from sqlalchemy.orm import Session
            from app.models.user import User as UserModel
            from app.models.pipeline import Pipeline as PipelineModel
            from app.database import SessionLocal
            
            # We're in an agent, state has user_id and pipeline_id
            if not state.user_id or not state.pipeline_id:
                return
            
            # Create sync DB session (agents run in sync context)
            db = SessionLocal()
            try:
                # Get user
                user = db.query(UserModel).filter(UserModel.id == state.user_id).first()
                if not user or not user.telegram_enabled:
                    return
                
                if not user.telegram_bot_token or not user.telegram_chat_id:
                    return
                
                # Get pipeline
                pipeline = db.query(PipelineModel).filter(PipelineModel.id == state.pipeline_id).first()
                if not pipeline or not pipeline.notification_enabled:
                    return
                
                # Check if trade_executed is in notification events
                notification_events = pipeline.notification_events or []
                if "trade_executed" not in notification_events:
                    return
                
                # Send notification
                telegram_notifier.send_trade_alert(
                    bot_token=user.telegram_bot_token,
                    chat_id=user.telegram_chat_id,
                    symbol=state.symbol,
                    action=strategy.action,
                    entry_price=entry_price,
                    stop_loss=stop_loss or 0.0,
                    take_profit=take_profit or 0.0,
                    position_size=risk.position_size,
                    pipeline_name=pipeline.name
                )
                
                logger.info(
                    "telegram_notification_sent",
                    user_id=str(state.user_id),
                    pipeline_id=str(state.pipeline_id),
                    event="trade_executed"
                )
                
            finally:
                db.close()
                
        except Exception as e:
            # Don't fail pipeline execution if notification fails
            logger.error(
                "telegram_notification_failed",
                error=str(e),
                user_id=str(state.user_id) if state.user_id else None,
                pipeline_id=str(state.pipeline_id) if state.pipeline_id else None
            )
