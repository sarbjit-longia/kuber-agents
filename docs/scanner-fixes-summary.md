# Scanner Phase 1 - Fixes Applied

**Date**: December 10, 2025  
**Issues Fixed**: Validator + Missing Settings UI

---

## Issue 1: Pipeline Validation Error ✅ FIXED

### Problem
When executing a pipeline, the validator was showing:
```
Pipeline must have a Trigger Agent (e.g., Time Trigger) to initiate execution
```

This was because the validator was still expecting the **old design** where every pipeline needed a Time Trigger agent.

### Solution
Updated the validator to support the **new trigger mode design**:

**For Periodic Pipelines** (default):
- Still requires a Time Trigger agent ✅
- Uses time-based scheduling

**For Signal-Based Pipelines** (new):
- Does NOT require a Time Trigger agent ✅
- Requires a scanner to be assigned ✅
- Triggered by external signals from signal generators

### Files Changed

1. **`backend/app/orchestration/validator.py`**
   - Updated `validate()` method to accept `trigger_mode` and `scanner_id` parameters
   - Updated `_validate_structure()` to check trigger requirements based on mode:
     - `periodic`: Requires Time Trigger agent
     - `signal`: Requires scanner_id (no trigger agent needed)

2. **`backend/app/api/v1/pipelines.py`**
   - Updated validation call to pass `trigger_mode` and `scanner_id`
   - Reads values from update request or existing pipeline

3. **`backend/app/api/v1/executions.py`**
   - Updated validation call to pass `trigger_mode` and `scanner_id`
   - Uses pipeline's actual trigger configuration

---

## Issue 2: Missing Settings UI ✅ FIXED

### Problem
User couldn't find where to configure:
- Trigger Mode (Periodic vs Signal)
- Scanner selection
- Signal subscriptions (filters)

The settings dialog was created but **not integrated** into the pipeline builder.

### Solution
Added a **Settings button** (⚙️) to the pipeline builder toolbar.

### What the Settings Dialog Allows

**Trigger Mode Selector**:
- 📅 **Periodic (Time-Based)**: Pipeline runs on schedule (requires Time Trigger agent)
- 🔔 **Signal-Based**: Pipeline wakes up on external signals (requires scanner)

**Scanner Selector** (for signal mode):
- Dropdown of all active scanners
- Preview of tickers in selected scanner
- Link to create scanner if none exist

**Signal Subscriptions** (optional filters):
- Add/remove signal type filters
- Set minimum confidence thresholds
- Example: Only trigger on "Golden Cross" signals with >80% confidence

### Files Changed

1. **`frontend/src/app/features/pipeline-builder/pipeline-builder.component.ts`**
   - Added import for `PipelineSettingsDialogComponent`
   - Added `currentPipeline` property to store full pipeline object
   - Added `openPipelineSettings()` method to open the dialog
   - Updated `loadPipeline()` to populate `currentPipeline`

2. **`frontend/src/app/features/pipeline-builder/pipeline-builder.component.html`**
   - Added Settings button (⚙️) in toolbar-right section
   - Button disabled if pipeline not saved yet
   - Tooltip: "Pipeline Settings (Trigger Mode, Scanner)"

---

## How to Use (User Guide)

### For Periodic Pipelines (Time-Based)
1. Add a **Time Trigger** agent to your pipeline
2. Configure time trigger settings (interval, start/end time, days)
3. Add other agents (Market Data, Strategy, Risk, etc.)
4. **Save** the pipeline
5. **Activate** and it will run on schedule ✅

### For Signal-Based Pipelines (Event-Driven)
1. **First**: Create a scanner at `/scanners` with your tickers
2. In Pipeline Builder, create your pipeline (Market Data, Strategy, Risk, etc.)
   - **No need for Time Trigger agent** ✅
3. **Save** the pipeline
4. Click **Settings button** (⚙️)
5. Select **"Signal-Based"** trigger mode
6. Choose your **scanner** from dropdown
7. (Optional) Add **signal filters** to narrow down which signals trigger the pipeline
8. Click **"Save Settings"**
9. **Activate** the pipeline
10. It will now wake up when signal generators emit signals for your scanner's tickers ✅

---

## Validation Rules (Updated)

### Periodic Pipelines
- ✅ Must have at least one Time Trigger agent
- ✅ Must have at least one other agent (e.g., Market Data, Strategy)
- ✅ All agents must be configured properly
- ✅ Required tools must be attached

### Signal-Based Pipelines
- ✅ Must have a scanner assigned (via Settings)
- ✅ Must have at least one agent (e.g., Market Data, Strategy)
- ✅ Does NOT require Time Trigger agent
- ✅ All agents must be configured properly
- ✅ Required tools must be attached

---

## Testing Checklist

### Backend Validation
- [x] Periodic pipeline with Time Trigger passes validation ✅
- [x] Signal pipeline without Time Trigger passes validation ✅
- [x] Signal pipeline without scanner fails validation ✅
- [x] Backend restarted successfully ✅

### Frontend Settings UI
- [ ] Settings button visible in pipeline builder toolbar
- [ ] Settings button disabled if pipeline not saved
- [ ] Settings dialog opens on click
- [ ] Trigger mode selector works
- [ ] Scanner dropdown loads scanners
- [ ] Scanner preview shows tickers
- [ ] Signal subscription add/remove works
- [ ] Settings save updates pipeline

---

## Next Steps

1. **Restart your frontend** if needed (Angular hot reload should work)
2. **Test the Settings button** - Click ⚙️ in pipeline builder toolbar
3. **Create a signal-based pipeline**:
   - Go to `/scanners` and create a scanner
   - Go to pipeline builder, remove Time Trigger agent
   - Add Market Data, Strategy, Risk agents
   - Save pipeline
   - Click Settings ⚙️
   - Select Signal mode + your scanner
   - Save settings
   - Activate pipeline ✅

---

## Troubleshooting

### "Settings button not showing"
- Make sure you saved the pipeline first
- Check browser console for errors
- Refresh the page

### "Pipeline validation still failing"
- Check if backend was restarted: `docker logs trading-backend --tail 20`
- Verify trigger mode and scanner are set correctly
- For signal mode: Make sure scanner is assigned in Settings

### "Settings dialog not opening"
- Check browser console for errors
- Make sure Angular module imports are correct
- Check if `PipelineSettingsDialogComponent` is declared in the module

---

## Summary

✅ **Validator Updated**: Now supports both periodic and signal-based pipelines  
✅ **Settings UI Integrated**: Settings button (⚙️) added to pipeline builder  
✅ **Backend Restarted**: Changes applied  
✅ **Ready for Testing**: Frontend should work after refresh

**You can now configure pipelines to be triggered by signals instead of just time!** 🎉

