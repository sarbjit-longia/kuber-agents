# Scanner Feature - Testing Guide

**Quick guide for testing the Scanner feature (Phase 1)**

---

## 🧪 Backend Testing (API)

### 1. Test Scanner Creation

```bash
# Get auth token first
TOKEN="your-jwt-token"

# Create a scanner
curl -X POST http://localhost:8000/api/v1/scanners \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Tech Giants",
    "description": "Top technology stocks",
    "scanner_type": "manual",
    "config": {
      "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    },
    "is_active": true
  }'
```

**Expected**: 201 Created with scanner object

### 2. Test List Scanners

```bash
curl -X GET http://localhost:8000/api/v1/scanners \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: Array of scanners with `ticker_count` and `pipeline_count`

### 3. Test Get Scanner Tickers

```bash
curl -X GET http://localhost:8000/api/v1/scanners/{scanner_id}/tickers \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: Ticker list with metadata

### 4. Test Update Scanner

```bash
curl -X PATCH http://localhost:8000/api/v1/scanners/{scanner_id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA"]
    }
  }'
```

**Expected**: 200 OK with updated scanner

### 5. Test Delete Scanner (without usage)

```bash
curl -X DELETE http://localhost:8000/api/v1/scanners/{scanner_id} \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: 204 No Content

### 6. Test Delete Scanner (with usage)

```bash
# First, assign scanner to a pipeline, then try to delete
curl -X DELETE http://localhost:8000/api/v1/scanners/{scanner_id} \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**: 400 Bad Request with error message

### 7. Test Get Available Signal Types

```bash
curl -X GET http://localhost:8000/api/v1/signals/types
```

**Expected**: Array of signal types (mock, golden_cross)

---

## 🎨 Frontend Testing (UI)

### 1. Scanner Management Page

#### Navigate to `/scanners`
- ✅ Page loads without errors
- ✅ Shows empty state if no scanners
- ✅ "New Scanner" button visible

#### Create Scanner
1. Click **"New Scanner"**
2. Enter name: "My Watchlist"
3. Add tickers: 
   - Type `AAPL` and press Enter
   - Type `MSFT` and press Enter
   - Paste: `GOOGL, AMZN, TSLA`
4. Click **"Create Scanner"**

**Expected**:
- ✅ Tickers normalized to uppercase
- ✅ Duplicates removed automatically
- ✅ Ticker count shows correct number
- ✅ Dialog closes on create
- ✅ Scanner appears in list
- ✅ Success snackbar shown

#### Edit Scanner
1. Click **menu (⋮)** on scanner card
2. Click **"Edit"**
3. Add more tickers
4. Click **"Save Changes"**

**Expected**:
- ✅ Dialog pre-fills with existing data
- ✅ New tickers added
- ✅ Card updates immediately

#### Toggle Active/Inactive
1. Click **menu (⋮)** on scanner card
2. Click **"Deactivate"**

**Expected**:
- ✅ Status chip changes to "Inactive"
- ✅ Chip color changes to gray
- ✅ Snackbar confirms action

#### Filter Scanners
1. Click **"Active"** filter button

**Expected**:
- ✅ Shows only active scanners
- ✅ Click "All" shows all again

#### Delete Scanner
1. Click **menu (⋮)** on scanner card
2. Click **"Delete"**
3. Confirm deletion

**Expected**:
- ✅ Confirmation dialog appears
- ✅ Scanner removed from list
- ✅ If used by pipeline, shows error message

---

### 2. Pipeline Settings Dialog

#### Open Settings in Pipeline Builder
1. Go to **Pipeline Builder**
2. Click **Settings** icon (⚙️)

**Expected**:
- ✅ Dialog opens
- ✅ Shows current trigger mode (Periodic by default)

#### Switch to Signal Mode
1. Select **"Signal-Based"** radio button

**Expected**:
- ✅ Scanner selector appears
- ✅ Signal filters section appears
- ✅ Scanner dropdown is required (red border if empty)

#### Select Scanner
1. Click **"Select Scanner"** dropdown
2. Choose a scanner

**Expected**:
- ✅ Scanner preview appears below dropdown
- ✅ Shows scanner name and tickers (up to 15)
- ✅ Shows "+X more" if more than 15 tickers

#### Add Signal Filter
1. Click **"Add Filter"**
2. Select signal type: "Golden Cross"
3. Enter min confidence: 80

**Expected**:
- ✅ Filter row appears
- ✅ Signal type dropdown shows available types with icons
- ✅ Confidence field accepts 0-100

#### Remove Signal Filter
1. Click **delete icon** on filter row

**Expected**:
- ✅ Filter removed
- ✅ Shows "Accepting all signal types" message

#### Save Settings
1. Click **"Save Settings"**

**Expected**:
- ✅ Dialog closes
- ✅ Pipeline updated with scanner_id and signal_subscriptions

---

## 🔄 End-to-End Testing

### Scenario: Create Signal-Based Pipeline

#### Step 1: Create Scanner
1. Go to `/scanners`
2. Create scanner "Test Scanner" with tickers: `AAPL, MSFT`
3. Note the scanner ID

#### Step 2: Configure Pipeline
1. Go to `/pipeline-builder`
2. Create or edit a pipeline
3. Open **Settings**
4. Select **"Signal-Based"** trigger mode
5. Select "Test Scanner"
6. Add signal filter:
   - Signal Type: "Golden Cross"
   - Min Confidence: 85
7. Save settings
8. **Save and Activate** pipeline

#### Step 3: Verify Database
```sql
-- Check pipeline has scanner_id
SELECT id, name, trigger_mode, scanner_id, signal_subscriptions FROM pipelines WHERE name = 'your-pipeline';

-- Check scanner exists
SELECT id, name, config FROM scanners WHERE name = 'Test Scanner';
```

**Expected**:
- ✅ `trigger_mode` = 'signal'
- ✅ `scanner_id` = UUID of "Test Scanner"
- ✅ `signal_subscriptions` = `[{"signal_type": "golden_cross", "min_confidence": 85}]`

#### Step 4: Check Trigger Dispatcher Cache
```bash
# Check logs
docker logs trading-trigger-dispatcher | grep "pipeline_cache_refreshed"
```

**Expected**:
- ✅ Cache includes your pipeline
- ✅ Cache shows correct ticker count

#### Step 5: Test Signal Matching
```bash
# Manually publish a signal to Kafka (for testing)
# Or wait for signal-generator to emit a Golden Cross signal
docker logs trading-signal-generator | grep "golden_cross_detected"
```

**Expected**:
- ✅ Trigger Dispatcher logs "signal_matched_to_pipeline"
- ✅ Pipeline execution starts (check `/monitoring`)

#### Step 6: Verify Execution
1. Go to `/monitoring`
2. Check latest execution

**Expected**:
- ✅ Execution shows for your pipeline
- ✅ Triggered by signal (not time trigger)
- ✅ Execution details show correct ticker

---

## 🐛 Troubleshooting

### Scanner Not Appearing in Dropdown
- Check if scanner `is_active = true`
- Check if user owns the scanner
- Refresh browser

### Signal Not Triggering Pipeline
- Check scanner has correct tickers
- Check signal type matches subscription
- Check confidence threshold
- Check pipeline is active
- Check Trigger Dispatcher logs

### Tickers Not Normalized
- Should auto-uppercase on save
- Should remove duplicates
- Check browser console for errors

### Delete Scanner Fails
- Check if scanner is used by any pipeline
- Go to `/api/v1/scanners/{id}/usage` to see which pipelines

---

## 📊 Metrics to Monitor

### Backend
```bash
# Scanner API calls
curl -s http://localhost:8001/metrics | grep scanner_

# Pipeline cache size
curl -s http://localhost:8004/metrics | grep pipeline_cache_size

# Signal matching
curl -s http://localhost:8004/metrics | grep pipelines_matched
```

### Grafana Dashboard
- Go to http://localhost:3000
- Check **"Pipelines Matched Total"** panel
- Check **"Pipeline Cache Size"** panel

---

## ✅ Acceptance Criteria

### Must Work
- [x] Create scanner with tickers ✅
- [x] Edit scanner tickers ✅
- [x] Delete unused scanner ✅
- [x] Assign scanner to pipeline ✅
- [x] Pipeline settings save scanner_id ✅
- [x] Trigger Dispatcher uses scanner for matching ✅
- [ ] Signal triggers correct pipeline ⏳ (needs E2E test)

### Should Work
- [ ] Delete scanner fails if used ✅ (enforced by API)
- [ ] Scanner dropdown shows only active scanners ✅
- [ ] Ticker normalization (uppercase, dedupe) ✅
- [ ] Signal filtering by type ✅ (logic implemented)
- [ ] Signal filtering by confidence ✅ (logic implemented)

### Nice to Have
- [ ] Scanner preview in settings dialog ✅
- [ ] Ticker count badge ✅
- [ ] Pipeline count on scanner card ✅
- [ ] Empty state messages ✅

---

## 🚀 Ready for Production?

### Pre-Flight Checklist
- [ ] All API tests pass
- [ ] All UI tests pass
- [ ] Database migration applied
- [ ] Backend rebuilt
- [ ] Trigger Dispatcher rebuilt
- [ ] No console errors in browser
- [ ] No errors in backend logs
- [ ] Grafana shows scanner metrics

### Known Issues
- None currently

---

**Happy Testing! 🎉**

