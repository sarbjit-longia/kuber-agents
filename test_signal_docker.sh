#!/bin/bash
# Test signal injection using Docker container
# Usage: ./test_signal_docker.sh [--ticker TICKER] [--signal-type TYPE] [--confidence CONF]

TICKER="${1:-AAPL}"
SIGNAL_TYPE="${2:-test_signal}"
CONFIDENCE="${3:-85}"

echo "Injecting test signal:"
echo "  Ticker: $TICKER"
echo "  Signal Type: $SIGNAL_TYPE"
echo "  Confidence: $CONFIDENCE"
echo ""

docker exec trading-signal-generator python -c "
import json
import uuid
from datetime import datetime, timezone
from kafka import KafkaProducer

# Create producer
producer = KafkaProducer(
    bootstrap_servers='kafka:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# Generate signal
signal_id = str(uuid.uuid4())
timestamp = datetime.now(timezone.utc).isoformat()

signal_data = {
    'signal_id': signal_id,
    'signal_type': '$SIGNAL_TYPE',
    'source': 'test_injector',
    'timestamp': timestamp,
    'tickers': [
        {
            'ticker': '$TICKER',
            'signal': 'BULLISH',
            'confidence': $CONFIDENCE
        }
    ],
    'metadata': {
        'test': True,
        'injected_via': 'docker_script'
    }
}

# Send signal
producer.send('trading-signals', signal_data)
producer.flush()

print(f'✅ Signal sent: {signal_id}')
print(f'   Type: $SIGNAL_TYPE')
print(f'   Ticker: $TICKER')
print(f'   Confidence: $CONFIDENCE%')
"

echo ""
echo "✅ Test signal injected! Check trigger-dispatcher logs:"
echo "   docker logs trading-trigger-dispatcher | tail -20"

