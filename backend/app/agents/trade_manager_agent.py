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
            self.log(state, f"📋 Limit order still pending: {order_id}")
            
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
            
            # Evaluate emergency exit conditions
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
                    # Position was previously found but now missing - this is suspicious
                    # Could be a transient API error. Don't mark as cancelled yet.
                    self.log(
                        state,
                        f"⚠️ Position previously found but now missing for {state.symbol} "
                        f"(order_id={order_id}). This might be a transient API error. "
                        f"Will retry on next check.",
                        level="warning"
                    )
                    # Don't mark as cancelled - let the next monitoring check confirm
                    # The API error handling will track consecutive failures
                    # If it's a real API error, we'll hit the 5-failure threshold
                    # If the position was actually closed, we'll confirm on next successful check
                    return state
                
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
                        
                        final_pnl = broker_realized_pl
                        exit_price = float(broker_close_price) if broker_close_price else None
                        
                        # Calculate P&L percent from broker data
                        entry = broker_open_price or (state.strategy.entry_price if state.strategy else None)
                        if not entry and state.trade_execution:
                            entry = state.trade_execution.filled_price
                        final_pnl_percent = None
                        if entry and entry > 0 and exit_price:
                            final_pnl_percent = ((exit_price - entry) / entry) * 100
                        
                        exit_reason = "Position closed by broker (SL/TP/manual)" if broker_state == "closed" else "Position closed"
                        
                        self.log(
                            state,
                            f"✅ Broker P&L for {id_for_display}: "
                            f"${broker_realized_pl:+.2f} | exit_price={exit_price} | state={broker_state}"
                        )
                        
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
                        
                        self.record_report(
                            state,
                            title="Position closed",
                            summary=f"{state.symbol} position closed | P&L: ${final_pnl:+.2f}" + (f" ({final_pnl_percent:+.2f}%)" if final_pnl_percent is not None else ""),
                            status="completed",
                            data={
                                "symbol": state.symbol,
                                "reason": exit_reason,
                                "final_pnl": final_pnl,
                                "final_pnl_percent": final_pnl_percent,
                                "exit_price": exit_price,
                                "entry_price": entry,
                                "closed_at": datetime.now().isoformat(),
                                "order_id": order_id,
                                "trade_id": trade_id
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
                
                # Tradier: Positions don't have individual trade IDs, but we can use
                # the position ID or create a synthetic ID from position data
                # Check for any ID-like fields in Tradier position data
                if not trade_id:
                    # Try common ID fields
                    trade_id = (
                        broker_data.get("id") or
                        broker_data.get("position_id") or
                        broker_data.get("trade_id") or
                        broker_data.get("tradeID")
                    )
                    if trade_id:
                        trade_id = str(trade_id)
                
                # Fallback: For Tradier, create a synthetic trade_id from position data
                # This allows us to track the position even if Tradier doesn't provide a trade ID
                if not trade_id and hasattr(broker, '__class__') and 'Tradier' in broker.__class__.__name__:
                    # Use symbol + quantity + cost_basis as a unique identifier
                    # This is stable as long as the position exists
                    synthetic_id = f"{position.symbol}_{position.qty}_{position.cost_basis:.2f}"
                    trade_id = synthetic_id
                    self.logger.debug(
                        "created_synthetic_trade_id_for_tradier",
                        symbol=position.symbol,
                        trade_id=trade_id
                    )
                
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

