"""
Twilio SMS Notifier for Trade Approval

Sends SMS messages with trade approval links via Twilio.
"""
import structlog
from typing import Optional, Dict, Any

from app.config import settings

logger = structlog.get_logger()


class TwilioSmsNotifier:
    """Send trade approval SMS notifications via Twilio."""

    @staticmethod
    def send_approval_request(
        to_phone: str,
        symbol: str,
        action: str,
        confidence: Optional[float],
        position_size: Optional[float],
        entry_price: Optional[float],
        approval_url: str,
        timeout_minutes: int,
    ) -> Dict[str, Any]:
        """
        Send an SMS with trade approval details and link.

        Args:
            to_phone: Recipient phone number (E.164 format)
            symbol: Trading symbol (e.g. "AAPL")
            action: Trade action (BUY/SELL)
            confidence: Strategy confidence (0-1)
            position_size: Number of units
            entry_price: Entry price
            approval_url: URL to approve/reject the trade
            timeout_minutes: Minutes before auto-reject

        Returns:
            Dict with message SID and status
        """
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            logger.warning("twilio_not_configured", msg="Skipping SMS — Twilio credentials not set")
            return {"status": "skipped", "reason": "twilio_not_configured"}

        conf_str = f" ({confidence * 100:.0f}% conf)" if confidence else ""
        size_str = f", {position_size:.0f} units" if position_size else ""
        price_str = f" @ ${entry_price:.2f}" if entry_price else ""

        body = (
            f"Trade approval: {action} {symbol}{price_str}{conf_str}{size_str}. "
            f"Approve/reject within {timeout_minutes}m: {approval_url}"
        )

        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=body,
                from_=settings.TWILIO_FROM_NUMBER,
                to=to_phone,
            )
            logger.info(
                "sms_sent",
                to=to_phone,
                message_sid=message.sid,
                symbol=symbol,
            )
            return {"status": "sent", "message_sid": message.sid}
        except Exception as e:
            logger.error("sms_send_failed", to=to_phone, error=str(e))
            return {"status": "error", "error": str(e)}
