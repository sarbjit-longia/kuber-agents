# Position-Aware Trade Manager Implementation

## Overview

Implemented a position-aware trade execution and monitoring system where the **Trade Manager Agent** can:
1. **Execute trades** via broker or webhook
2. **Monitor open positions** continuously until completion
3. **Handle emergency exits** based on custom instructions

This eliminates duplicate trades and enables continuous position monitoring.

---

## Architecture

### **Dual-Phase Execution**

```
┌─────────────────────────────────────────────────────────┐
│  Phase 1: EXECUTE (Initial Pipeline Run)                │
│  ├─ Bias Agent → Market bias analysis                   │
│  ├─ Strategy Agent → Entry signal                       │
│  ├─ Risk Manager → Position sizing                      │
│  └─ Trade Manager:                                       │
│      ├─ Check broker for duplicate position             │
│      ├─ If duplicate → SKIP, mark COMPLETED ✅          │
│      ├─ If webhook tool → Send signal, COMPLETED ✅     │
│      └─ If broker tool → Execute bracket order          │
│          ├─ Set take profit & stop loss                 │
│          └─ Status: MONITORING 🔄                       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Phase 2: MONITOR (Every 5 minutes)                     │
│  └─ Trade Manager only:                                 │
│      ├─ Fresh DB connection ← Prevent long-running     │
│      ├─ position = broker.get_position(symbol)          │
│      ├─ If position closed → COMPLETED ✅               │
│      ├─ If emergency condition → Close position         │
│      │   └─ COMPLETED ✅                                │
│      └─ Else → Schedule next check in 5 min            │
│      └─ DB.close() ← Clean up                          │
└─────────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. **Database Schema** (`backend/app/models/execution.py`)

**New Execution Status:**
```python
class ExecutionStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    MONITORING = "monitoring"  # ← NEW: Position monitoring mode
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    SKIPPED = "skipped"
```

**New Fields:**
```python
class Execution(Base):
    # ... existing fields ...
    
    # Position monitoring fields
    execution_phase = Column(String(20), default="execute", nullable=False)
    next_check_at = Column(DateTime, nullable=True)
    monitor_interval_minutes = Column(Integer, default=5, nullable=False)
```

### 2. **Pipeline State** (`backend/app/schemas/pipeline_state.py`)

```python
class PipelineState(BaseModel):
    # ... existing fields ...
    
    # Position monitoring
    execution_phase: str = "execute"  # "execute" or "monitoring"
    should_complete: bool = False  # Signal from agent to complete
    monitor_interval_minutes: int = 5  # Polling frequency
```

### 3. **Trade Manager Agent** (`backend/app/agents/trade_manager_agent.py`)

**Dual-Phase Processing:**

```python
def process(self, state: PipelineState) -> PipelineState:
    is_monitoring = state.execution_phase == "monitoring"
    
    if is_monitoring:
        return self._monitor_position(state)  # Phase 2
    else:
        return self._execute_trade(state)  # Phase 1
```

**Execute Phase:**
- Checks for duplicate positions via `broker.get_position(symbol)`
- Executes bracket orders with take profit & stop loss
- Sets `state.execution_phase = "monitoring"` if broker trade

**Monitor Phase:**
- Checks if position still exists
- Evaluates emergency exit conditions from instructions
- Sets `state.should_complete = True` when done

### 4. **Pipeline Executor** (`backend/app/orchestration/executor.py`)

**Self-Scheduling Logic:**

```python
# After pipeline execution completes
if state.execution_phase == "monitoring":
    execution.status = ExecutionStatus.MONITORING
    execution.next_check_at = datetime.utcnow() + timedelta(minutes=5)
    
    # Schedule monitoring task
    schedule_monitoring_check.apply_async(
        args=[str(execution.id)],
        countdown=5 * 60  # 5 minutes
    )
```

### 5. **Celery Monitoring Task** (`backend/app/orchestration/tasks.py`)

```python
@celery_app.task(name="schedule_monitoring_check", max_retries=5)
def schedule_monitoring_check(execution_id: str):
    """
    Periodic position monitoring.
    - Fresh DB connection each time (no long-running connections)
    - Checks position status via broker API
    - Evaluates emergency exit conditions
    - Self-schedules next check or completes
    """
    db = SessionLocal()  # ← Fresh connection!
    
    try:
        # Load execution, reconstruct state
        # Run Trade Manager in monitoring mode
        # If should_complete → Mark COMPLETED
        # Else → Schedule next check
    finally:
        db.close()  # ← Always clean up!
```

**Retry Strategy:** Exponential backoff (1, 2, 4, 8, 16 min) for broker API failures.

### 6. **UI Updates**

**Frontend Monitoring Component:**
- Added **MONITORING** status display
- Yellow pulsing animation for monitoring executions
- Eye icon (`visibility`) for monitoring status

```typescript
// monitoring.component.ts
getStatusIcon(status: string): string {
  return {
    'monitoring': 'visibility',
    // ... other statuses
  }[status] || 'help';
}
```

```scss
// monitoring.component.scss
.status-monitoring {
  background-color: #fff9c4 !important;
  color: #f57f17 !important;
  animation: pulse-monitoring 2s ease-in-out infinite;
}
```

---

## User-Facing Features

### **Instructions-Driven Emergency Exits**

Users can configure emergency exit conditions in Trade Manager instructions:

#### **Examples:**

1. **VIX-Based Exit:**
   ```
   Close position if VIX > 40
   ```

2. **News-Based Exit:**
   ```
   Exit on high impact news for this symbol
   ```

3. **Market Crash Protection:**
   ```
   Liquidate if SPY drops 3% intraday
   ```

4. **Combined Conditions:**
   ```
   Monitor position and close on:
   - High impact news
   - VIX > 35
   - Market crashes (SPY -3%)
   ```

### **Trade Execution Flow**

#### **Webhook (Fire-and-Forget):**
```
Create Pipeline → Add Webhook Tool → Execute
Duration: 30 seconds
Status: COMPLETED ✅
```

#### **Broker (With Monitoring):**
```
Create Pipeline → Add Broker Tool → Execute
Duration: Until position closes (hours/days)
Status: MONITORING 🔄 (checks every 5 min)
UI shows: "Monitoring AAPL: +2.3% P&L"
```

---

## Benefits

| Concern | Solution |
|---------|----------|
| **API Rate Limits** | ✅ 5-min polling = 12 calls/hour (vs 60/min) |
| **DB Connections** | ✅ Fresh connection per check, always closed |
| **Broker Downtime** | ✅ Celery retry with exponential backoff |
| **Duplicate Trades** | ✅ Broker position check before execution |
| **Manual Positions** | ✅ Detected & skipped automatically |
| **Audit Trail** | ✅ Full execution log in database |
| **Testing** | ✅ Paper trading accounts supported |
| **Emergency Exits** | ✅ Instruction-driven custom conditions |

---

## Implementation Details

### **Polling Frequency**
- Default: **5 minutes**
- Configurable via `state.monitor_interval_minutes`
- Results in **12 API calls/hour** per open position

### **Duplicate Position Prevention**
```python
def _has_duplicate_position(self, state, broker_tool) -> bool:
    position = broker_tool.get_position(account_id, state.symbol)
    return position is not None
```
- Prevents opening multiple positions for the same symbol
- Handles manual positions opened outside the platform

### **Broker As Source of Truth**
- Position status queried from broker API
- No local position tracking (reduces complexity)
- Handles manual exits gracefully

### **Emergency Exit Parsing**
```python
def _evaluate_exit_conditions(self, state, position) -> tuple[bool, str]:
    instructions = self.config.get("instructions", "").lower()
    
    # VIX spike
    if "vix" in instructions:
        vix_threshold = parse_number(instructions, "vix")
        if get_vix() > vix_threshold:
            return True, f"VIX spike: {get_vix()} > {vix_threshold}"
    
    # High impact news
    if "news" in instructions:
        if check_high_impact_news(state.symbol):
            return True, "High impact news detected"
    
    # Market crash
    if "spy" in instructions or "market crash" in instructions:
        spy_change = get_spy_daily_change()
        if spy_change < -3.0:
            return True, f"Market crash: SPY {spy_change:.1f}%"
    
    return False, ""
```

---

## Migration

**Alembic Migration:** `20251218_0533_add_position_monitoring_fields`

```sql
-- Add MONITORING status
ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'monitoring';

-- Add monitoring fields
ALTER TABLE executions 
  ADD COLUMN execution_phase VARCHAR(20) NOT NULL DEFAULT 'execute',
  ADD COLUMN next_check_at TIMESTAMP,
  ADD COLUMN monitor_interval_minutes INTEGER NOT NULL DEFAULT 5;
```

---

## Testing

### **Simulated Trade (No Broker):**
1. Create pipeline with Trade Manager (no tools attached)
2. Execute → Should fail with "No execution tool attached"

### **Webhook Test:**
1. Create pipeline with Webhook Notifier tool
2. Execute → Should send webhook and complete immediately
3. Status: `COMPLETED` (no monitoring)

### **Broker Test (Paper Trading):**
1. Create pipeline with Alpaca Broker tool (paper account)
2. Configure instructions: "Close on high impact news"
3. Execute → Should enter `MONITORING` status
4. Check database: `execution.status = 'monitoring'`, `next_check_at` set
5. Wait 5 minutes → Celery task should run
6. Manually close position in Alpaca → Next check should detect and complete

### **Duplicate Prevention Test:**
1. Create pipeline with Alpaca Broker tool
2. Execute twice quickly
3. First execution: Trades, enters monitoring
4. Second execution: Skipped (duplicate detected)

---

## Future Enhancements

1. **Position State Table** (Phase 2):
   - Track position history locally for audit trail
   - Enable analytics & performance tracking

2. **ML-Based Emergency Exits**:
   - Use LLM to dynamically evaluate market conditions
   - "Close if market sentiment turns bearish"

3. **Partial Exits**:
   - "Close 50% at 3% profit, let 50% run"
   - Scale out of positions

4. **Multi-Account Support**:
   - Monitor positions across multiple broker accounts
   - Aggregate P&L reporting

5. **Real-Time Monitoring**:
   - WebSocket integration for sub-minute updates
   - Push notifications for emergency exits

---

## Files Modified

1. **Backend:**
   - `backend/app/models/execution.py` - Added monitoring fields
   - `backend/app/schemas/pipeline_state.py` - Added monitoring state
   - `backend/app/agents/trade_manager_agent.py` - Dual-phase logic
   - `backend/app/orchestration/executor.py` - Self-scheduling
   - `backend/app/orchestration/tasks.py` - Monitoring task
   - `backend/alembic/versions/20251218_0533_add_position_monitoring_fields.py` - Migration

2. **Frontend:**
   - `frontend/src/app/features/monitoring/monitoring.component.ts` - Status handling
   - `frontend/src/app/features/monitoring/monitoring.component.scss` - Monitoring styling

---

## Summary

**This implementation solves the position management challenge with:**

✅ **Broker as source of truth** - No local position tracking complexity
✅ **5-minute polling** - Minimal API usage (12 calls/hour)
✅ **Fresh DB connections** - No long-running connection issues
✅ **Duplicate prevention** - Checks broker before each trade
✅ **Emergency exits** - Instruction-driven custom conditions
✅ **Self-scheduling** - Pipeline monitors itself until completion
✅ **User-friendly UI** - Clear monitoring status with pulsing animation

**Result:** A production-ready, scalable position monitoring system that respects API limits, prevents duplicate trades, and empowers users with flexible exit strategies.

