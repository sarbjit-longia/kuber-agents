#!/bin/bash
#
# Convenient wrapper to run the interactive test runner
#

cd "$(dirname "$0")"

# Make sure we're in the backend directory
if [ ! -f "test_runner.py" ]; then
    echo "❌ Error: test_runner.py not found"
    exit 1
fi

# Run the interactive test runner
python3 test_runner.py

