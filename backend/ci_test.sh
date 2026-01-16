#!/bin/bash
#
# CI/CD Test Script
# Returns exit code 0 if all tests pass, 1 if any fail
#
# Usage:
#   ./ci_test.sh                    # Run all tests
#   ./ci_test.sh bias               # Run bias agent tests only
#   ./ci_test.sh strategy           # Run strategy agent tests only
#   ./ci_test.sh risk               # Run risk manager tests only
#

set -e  # Exit on error

cd "$(dirname "$0")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Timestamp for reports
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORTS_DIR="test_reports"
mkdir -p "$REPORTS_DIR"

# Determine test path
TEST_PATH="tests/"
DESCRIPTION="All Agent Tests"

case "$1" in
    bias)
        TEST_PATH="tests/test_bias_agent.py"
        DESCRIPTION="Bias Agent Tests"
        ;;
    strategy)
        TEST_PATH="tests/test_strategy_agent.py"
        DESCRIPTION="Strategy Agent Tests"
        ;;
    risk)
        TEST_PATH="tests/test_risk_manager_agent.py"
        DESCRIPTION="Risk Manager Agent Tests"
        ;;
    smoke)
        TEST_PATH="tests/test_bias_agent.py::TestBiasAgentAccuracy::test_custom_rsi_thresholds_40_60 tests/test_strategy_agent.py::TestStrategyAgentAccuracy::test_custom_risk_reward_ratio tests/test_risk_manager_agent.py::TestRiskManagerAccuracy::test_custom_risk_per_trade_1_percent"
        DESCRIPTION="Smoke Tests"
        ;;
    "")
        # Default: all tests
        ;;
    *)
        echo -e "${RED}❌ Unknown test suite: $1${NC}"
        echo "Usage: $0 [bias|strategy|risk|smoke]"
        exit 1
        ;;
esac

echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}🧪 Running: $DESCRIPTION${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo

# Run tests with pytest
docker-compose exec -T backend pytest $TEST_PATH \
    --tb=short \
    --junit-xml="$REPORTS_DIR/junit_${TIMESTAMP}.xml" \
    --html="$REPORTS_DIR/report_${TIMESTAMP}.html" \
    --self-contained-html \
    --json-report \
    --json-report-file="$REPORTS_DIR/results_${TIMESTAMP}.json"

EXIT_CODE=$?

echo
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED!${NC}"
    echo
    echo -e "${GREEN}📊 Reports Generated:${NC}"
    echo -e "   HTML: $REPORTS_DIR/report_${TIMESTAMP}.html"
    echo -e "   JSON: $REPORTS_DIR/results_${TIMESTAMP}.json"
    echo -e "   JUnit: $REPORTS_DIR/junit_${TIMESTAMP}.xml"
else
    echo -e "${RED}❌ TESTS FAILED!${NC}"
    echo
    echo -e "${RED}📊 Failure Reports:${NC}"
    echo -e "   HTML: $REPORTS_DIR/report_${TIMESTAMP}.html"
    echo -e "   JSON: $REPORTS_DIR/results_${TIMESTAMP}.json"
fi

echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo

exit $EXIT_CODE

