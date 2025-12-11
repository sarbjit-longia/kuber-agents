#!/usr/bin/env python3
"""Update Data Plane dashboard queries to show instant values"""
import json

with open('monitoring/grafana/dashboards/trading-platform-overview.json', 'r') as f:
    dashboard = json.load(f)

updates = {
    "Quotes Fetched (5min window)": "sum(quotes_fetched_total) or vector(0)",
    "Quote Fetch Rate (per second)": "sum(quotes_fetched_total) or vector(0)", 
    "Quote Failures (1h)": "sum(quotes_fetch_failures_total) or vector(0)",
    "Candles Fetched (5m)": "sum(candles_fetched_total) or vector(0)"
}

for panel in dashboard['panels']:
    title = panel.get('title', '')
    if title in updates:
        if 'targets' in panel:
            for target in panel['targets']:
                if 'expr' in target:
                    old_expr = target['expr']
                    target['expr'] = updates[title]
                    print(f"✓ Updated '{title}'")
                    print(f"  Old: {old_expr}")
                    print(f"  New: {target['expr']}")

with open('monitoring/grafana/dashboards/trading-platform-overview.json', 'w') as f:
    json.dump(dashboard, f, indent=2)

print("\n✅ Dashboard updated to show instant values (total counts)")
print("   This will show data immediately while metrics accumulate")

