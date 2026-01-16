#!/usr/bin/env python3
"""
Interactive Test Runner for Agent Testing

Provides:
- Interactive menu for test selection
- Beautiful test execution output
- HTML/JSON report generation
- Regression testing visibility
- Test result comparison
"""
import os
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def print_banner():
    """Print welcome banner"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*80}")
    print("🧪 AGENT TEST RUNNER - Comprehensive Testing & Reporting")
    print(f"{'='*80}{Colors.END}\n")


def print_menu():
    """Display interactive menu"""
    print(f"{Colors.BOLD}Select Test Suite:{Colors.END}\n")
    print(f"  {Colors.GREEN}1{Colors.END}. Run Bias Agent Tests (10 tests)")
    print(f"  {Colors.GREEN}2{Colors.END}. Run Strategy Agent Tests (12 tests)")
    print(f"  {Colors.GREEN}3{Colors.END}. Run Risk Manager Agent Tests (12 tests)")
    print(f"  {Colors.GREEN}4{Colors.END}. Run ALL Agent Tests (34 tests)")
    print(f"  {Colors.GREEN}5{Colors.END}. Run Quick Smoke Tests (3 tests)")
    print(f"  {Colors.YELLOW}6{Colors.END}. Compare with Previous Run (regression check)")
    print(f"  {Colors.YELLOW}7{Colors.END}. View Test Coverage Summary")
    print(f"  {Colors.RED}8{Colors.END}. Exit\n")


def run_tests(test_path, description, generate_report=True):
    """Run pytest tests with enhanced output"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}🚀 Running: {description}{Colors.END}\n")
    
    # Ask if user wants to generate reports
    if generate_report:
        try:
            response = input(f"{Colors.BOLD}Generate HTML/JSON reports? (Y/n): {Colors.END}").strip().lower()
            generate_report = response != 'n'
        except (KeyboardInterrupt, EOFError):
            print("\n")
            return False, None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = Path("test_reports")
    reports_dir.mkdir(exist_ok=True)
    
    # Prepare pytest command
    cmd = [
        "docker-compose", "exec", "-T", "backend", "pytest"
    ]
    
    # Add test paths (split if multiple)
    if isinstance(test_path, str):
        cmd.extend(test_path.split())
    else:
        cmd.extend(test_path)
    
    # Add pytest options
    cmd.extend([
        "-v",  # Verbose
        "--tb=short",  # Short traceback
        f"--junit-xml=test_reports/junit_{timestamp}.xml",
    ])
    
    if generate_report:
        cmd.extend([
            f"--html=test_reports/report_{timestamp}.html",
            "--self-contained-html",
            f"--json-report",
            f"--json-report-file=test_reports/results_{timestamp}.json"
        ])
    
    # Run tests
    print(f"{Colors.YELLOW}📋 Command: {' '.join(cmd[4:])}{Colors.END}\n")
    result = subprocess.run(cmd, cwd="/Users/sarbjits/workspace/personal/kuber-agents")
    
    if result.returncode == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ ALL TESTS PASSED!{Colors.END}")
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ SOME TESTS FAILED{Colors.END}")
    
    # Show report location
    if generate_report:
        report_path = reports_dir / f"report_{timestamp}.html"
        json_path = reports_dir / f"results_{timestamp}.json"
        print(f"\n{Colors.CYAN}📊 Reports Generated:{Colors.END}")
        print(f"   HTML: {report_path}")
        print(f"   JSON: {json_path}")
        print(f"   Open: open {report_path}  # (Mac/Linux)")
    
    return result.returncode == 0, timestamp


def compare_with_previous():
    """Compare current test results with previous run (regression check)"""
    reports_dir = Path("test_reports")
    json_files = sorted(reports_dir.glob("results_*.json"), reverse=True)
    
    if len(json_files) < 2:
        print(f"{Colors.YELLOW}⚠️  Need at least 2 test runs to compare{Colors.END}")
        return
    
    current_file = json_files[0]
    previous_file = json_files[1]
    
    print(f"\n{Colors.CYAN}{Colors.BOLD}🔍 REGRESSION CHECK{Colors.END}")
    print(f"Current:  {current_file.name}")
    print(f"Previous: {previous_file.name}\n")
    
    try:
        with open(current_file) as f:
            current = json.load(f)
        with open(previous_file) as f:
            previous = json.load(f)
        
        # Compare summaries
        curr_summary = current.get('summary', {})
        prev_summary = previous.get('summary', {})
        
        print(f"{Colors.BOLD}Summary Comparison:{Colors.END}")
        print(f"{'Metric':<20} {'Previous':<15} {'Current':<15} {'Change':<15}")
        print("-" * 65)
        
        for metric in ['total', 'passed', 'failed', 'skipped']:
            prev_val = prev_summary.get(metric, 0)
            curr_val = curr_summary.get(metric, 0)
            change = curr_val - prev_val
            
            if metric == 'failed':
                color = Colors.GREEN if change < 0 else (Colors.RED if change > 0 else Colors.END)
            elif metric == 'passed':
                color = Colors.GREEN if change > 0 else (Colors.RED if change < 0 else Colors.END)
            else:
                color = Colors.END
            
            change_str = f"{color}{change:+d}{Colors.END}" if change != 0 else "0"
            print(f"{metric:<20} {prev_val:<15} {curr_val:<15} {change_str}")
        
        # Check for regressions
        if curr_summary.get('failed', 0) > prev_summary.get('failed', 0):
            print(f"\n{Colors.RED}{Colors.BOLD}⚠️  REGRESSION DETECTED: More tests failing than before!{Colors.END}")
        elif curr_summary.get('passed', 0) > prev_summary.get('passed', 0):
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ IMPROVEMENT: More tests passing!{Colors.END}")
        else:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ NO REGRESSION: Test results stable{Colors.END}")
        
        # Show newly failing tests
        curr_tests = {t['nodeid']: t for t in current.get('tests', [])}
        prev_tests = {t['nodeid']: t for t in previous.get('tests', [])}
        
        newly_failing = []
        for nodeid, test in curr_tests.items():
            if test.get('outcome') == 'failed':
                prev_test = prev_tests.get(nodeid)
                if prev_test and prev_test.get('outcome') == 'passed':
                    newly_failing.append(nodeid)
        
        if newly_failing:
            print(f"\n{Colors.RED}{Colors.BOLD}🚨 Newly Failing Tests:{Colors.END}")
            for nodeid in newly_failing:
                print(f"   - {nodeid}")
        
    except Exception as e:
        print(f"{Colors.RED}❌ Error comparing results: {e}{Colors.END}")


def view_coverage_summary():
    """Display test coverage summary"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}📊 TEST COVERAGE SUMMARY{Colors.END}\n")
    
    coverage = {
        "Bias Agent": {
            "total": 10,
            "categories": {
                "Accuracy Tests": 4,
                "Report Tests": 3,
                "Edge Cases": 3
            },
            "coverage": [
                "✅ Custom RSI thresholds (40/60)",
                "✅ Multiple indicator usage (RSI, MACD, SMA)",
                "✅ Timeframe selection",
                "✅ Strong directional bias",
                "✅ Report structure validation",
                "✅ Multiple timeframes in reports",
                "✅ Key factors extraction",
                "✅ Minimal instructions handling",
                "✅ Missing data handling",
                "✅ Conflicting instructions"
            ]
        },
        "Strategy Agent": {
            "total": 12,
            "categories": {
                "Accuracy Tests": 5,
                "Report Tests": 3,
                "Edge Cases": 4
            },
            "coverage": [
                "✅ FVG strategy instructions",
                "✅ Bull flag pattern detection",
                "✅ Custom R/R ratio (2:1)",
                "✅ Timeframe-specific analysis",
                "✅ Report structure validation",
                "✅ Chart data generation",
                "✅ Reasoning format with sections",
                "✅ No trading opportunity (HOLD)",
                "✅ Conflicting bias handling",
                "✅ High confidence requirements",
                "✅ R/R validation",
                "✅ Edge cases"
            ]
        },
        "Risk Manager Agent": {
            "total": 12,
            "categories": {
                "Accuracy Tests": 5,
                "Report Tests": 3,
                "Edge Cases": 4
            },
            "coverage": [
                "✅ 1% risk per trade limit",
                "✅ 25% position size limit",
                "✅ Minimum R/R ratio (2:1)",
                "✅ Approve good R/R (3:1)",
                "✅ Report structure validation",
                "✅ Reasoning format",
                "✅ Warnings populated",
                "✅ Missing strategy handling",
                "✅ HOLD action handling",
                "✅ Zero stop loss edge case",
                "✅ Incomplete price levels",
                "✅ High risk scenarios"
            ]
        }
    }
    
    for agent, info in coverage.items():
        print(f"{Colors.BOLD}{agent} - {info['total']} tests{Colors.END}")
        print(f"  Categories: {', '.join(f'{k} ({v})' for k, v in info['categories'].items())}")
        print(f"  Coverage:")
        for item in info['coverage']:
            print(f"    {item}")
        print()
    
    total_tests = sum(info['total'] for info in coverage.values())
    print(f"{Colors.GREEN}{Colors.BOLD}Total Test Coverage: {total_tests} tests across 3 agents{Colors.END}\n")


def main():
    """Main interactive loop"""
    print_banner()
    
    while True:
        print_menu()
        
        try:
            choice = input(f"{Colors.BOLD}Enter your choice (1-9): {Colors.END}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Colors.YELLOW}Goodbye!{Colors.END}\n")
            sys.exit(0)
        
        if choice == '1':
            run_tests("tests/test_bias_agent.py", "Bias Agent Tests")
        elif choice == '2':
            run_tests("tests/test_strategy_agent.py", "Strategy Agent Tests")
        elif choice == '3':
            run_tests("tests/test_risk_manager_agent.py", "Risk Manager Agent Tests")
        elif choice == '4':
            run_tests("tests/test_bias_agent.py tests/test_strategy_agent.py tests/test_risk_manager_agent.py", "ALL Agent Tests (Full Suite)")
        elif choice == '5':
            # Quick smoke tests - one from each agent
            run_tests(
                "tests/test_bias_agent.py::TestBiasAgentAccuracy::test_custom_rsi_thresholds_40_60 "
                "tests/test_strategy_agent.py::TestStrategyAgentAccuracy::test_custom_risk_reward_ratio "
                "tests/test_risk_manager_agent.py::TestRiskManagerAccuracy::test_custom_risk_per_trade_1_percent",
                "Quick Smoke Tests (3 critical tests)"
            )
        elif choice == '6':
            compare_with_previous()
        elif choice == '7':
            view_coverage_summary()
        elif choice == '8':
            print(f"\n{Colors.GREEN}✅ Thank you for testing! Keep building great agents! 🚀{Colors.END}\n")
            break
        else:
            print(f"{Colors.RED}❌ Invalid choice. Please select 1-8.{Colors.END}")
        
        input(f"\n{Colors.YELLOW}Press Enter to continue...{Colors.END}")
        print("\n" * 2)


if __name__ == "__main__":
    main()

