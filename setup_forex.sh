#!/bin/bash
# Setup script for Forex Trading
# This creates a forex scanner and pipeline in your database

echo "========================================="
echo "🚀 FOREX TRADING SETUP"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Step 1: Run SQL setup
echo -e "${BLUE}Step 1: Creating Forex Scanner and Pipeline...${NC}"
docker-compose exec -T postgres psql -U dev -d trading_platform -f - < setup_forex_scanner.sql

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Forex scanner and pipeline created!${NC}"
else
    echo "❌ Failed to create scanner/pipeline"
    exit 1
fi

echo ""
echo "========================================="
echo "✅ SETUP COMPLETE!"
echo "========================================="
echo ""
echo "Your forex trading pipeline is ready:"
echo ""
echo "📊 Scanner: Forex Major Pairs"
echo "   - Tickers: EUR_USD, GBP_USD, USD_JPY, USD_CHF, AUD_USD, NZD_USD"
echo ""
echo "🤖 Pipeline: Forex RSI Reversal Strategy"
echo "   - Timeframes: 5m (strategy), 15m, 1h (bias)"
echo "   - Agents: Time Trigger → Market Data → Bias → Strategy → Risk Manager"
echo "   - Model: GPT-3.5-turbo"
echo ""
echo "Next Steps:"
echo "1. Go to http://localhost:4200"
echo "2. Navigate to 'Pipelines'"
echo "3. Find 'Forex RSI Reversal Strategy'"
echo "4. Click 'Run' to test manually"
echo ""
echo "The pipeline will automatically execute every 5 minutes!"
echo ""
