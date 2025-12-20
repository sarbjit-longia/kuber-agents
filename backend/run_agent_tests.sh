#!/bin/bash
# Quick test runner for agent tests

set -e

echo "🧪 Agent Test Runner"
echo "==================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to run tests
run_tests() {
    echo -e "${BLUE}Running: $1${NC}"
    echo ""
    docker-compose exec backend pytest $2 -v
}

# Check if specific test is requested
if [ "$1" == "bias" ]; then
    run_tests "Bias Agent Tests" "tests/test_bias_agent.py"
elif [ "$1" == "strategy" ]; then
    run_tests "Strategy Agent Tests" "tests/test_strategy_agent.py"
elif [ "$1" == "risk" ]; then
    run_tests "Risk Manager Tests" "tests/test_risk_manager_agent.py"
elif [ "$1" == "accuracy" ]; then
    run_tests "Accuracy Tests Only" "-m accuracy"
elif [ "$1" == "report" ]; then
    run_tests "Report Tests Only" "-m report"
elif [ "$1" == "unit" ]; then
    run_tests "Unit Tests Only" "-m unit"
elif [ "$1" == "quick" ]; then
    run_tests "Quick Tests (no slow)" "-m 'not slow'"
elif [ "$1" == "coverage" ]; then
    echo -e "${BLUE}Running All Tests with Coverage${NC}"
    echo ""
    docker-compose exec backend pytest tests/test_bias_agent.py tests/test_strategy_agent.py tests/test_risk_manager_agent.py --cov=app.agents --cov-report=term-missing -v
elif [ "$1" == "collect" ]; then
    echo -e "${BLUE}Collecting Tests (dry run)${NC}"
    echo ""
    docker-compose exec backend pytest tests/test_bias_agent.py tests/test_strategy_agent.py tests/test_risk_manager_agent.py --collect-only
elif [ "$1" == "help" ] || [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
    echo "Usage: ./run_agent_tests.sh [option]"
    echo ""
    echo "Options:"
    echo "  bias       - Run Bias Agent tests only"
    echo "  strategy   - Run Strategy Agent tests only"
    echo "  risk       - Run Risk Manager tests only"
    echo "  accuracy   - Run accuracy tests only (instruction following)"
    echo "  report     - Run report generation tests only"
    echo "  unit       - Run unit tests only (fast)"
    echo "  quick      - Run all except slow tests"
    echo "  coverage   - Run with coverage report"
    echo "  collect    - List all tests without running"
    echo "  help       - Show this help message"
    echo ""
    echo "No option = Run all agent tests"
else
    run_tests "All Agent Tests" "tests/test_bias_agent.py tests/test_strategy_agent.py tests/test_risk_manager_agent.py"
fi

echo ""
echo -e "${GREEN}✅ Test run complete!${NC}"

