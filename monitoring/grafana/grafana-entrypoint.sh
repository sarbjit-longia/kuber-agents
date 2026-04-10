#!/bin/sh
# Only provision Telegram alerting if bot token is configured
if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
  cp -r /etc/grafana/provisioning/alerting-available/* /etc/grafana/provisioning/alerting/ 2>/dev/null || true
fi

exec /run.sh
