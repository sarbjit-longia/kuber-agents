"""
Apple Push Notification Service (APNs) Integration

Sends push notifications to iOS devices via APNs HTTP/2 API.
Uses JWT-based authentication with the APNs auth key (.p8 file).
"""
import time
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

import httpx
import jwt
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user_device import UserDevice

logger = structlog.get_logger()

# APNs endpoints
APNS_PRODUCTION_URL = "https://api.push.apple.com"
APNS_SANDBOX_URL = "https://api.sandbox.push.apple.com"


class APNsService:
    """
    Send push notifications via APNs HTTP/2.

    Uses JWT (token-based) authentication. The auth key is read from the path
    configured in settings.apns_auth_key_path and cached for reuse until
    it expires (APNs tokens are valid for up to 60 minutes).
    """

    def __init__(self):
        self._jwt_token: Optional[str] = None
        self._jwt_issued_at: float = 0
        self._auth_key: Optional[str] = None
        # Token refresh interval: 50 minutes (APNs allows up to 60)
        self._token_ttl = 50 * 60

    @property
    def _base_url(self) -> str:
        """Return production or sandbox APNs URL based on environment."""
        if settings.ENV == "production":
            return APNS_PRODUCTION_URL
        return APNS_SANDBOX_URL

    def _load_auth_key(self) -> str:
        """Load the APNs auth key (.p8 file) from disk."""
        if self._auth_key is not None:
            return self._auth_key

        key_path = Path(settings.APNS_AUTH_KEY_PATH)
        if not key_path.exists():
            raise FileNotFoundError(
                f"APNs auth key not found at {key_path}. "
                "Download it from Apple Developer portal."
            )

        self._auth_key = key_path.read_text()
        return self._auth_key

    def _get_jwt_token(self) -> str:
        """
        Generate or return a cached APNs JWT token.

        APNs tokens are valid for up to 60 minutes. We refresh at 50 minutes.
        """
        now = time.time()
        if self._jwt_token and (now - self._jwt_issued_at) < self._token_ttl:
            return self._jwt_token

        auth_key = self._load_auth_key()
        headers = {
            "alg": "ES256",
            "kid": settings.APNS_KEY_ID,
        }
        payload = {
            "iss": settings.APNS_TEAM_ID,
            "iat": int(now),
        }

        self._jwt_token = jwt.encode(payload, auth_key, algorithm="ES256", headers=headers)
        self._jwt_issued_at = now

        logger.debug("apns_jwt_generated", key_id=settings.APNS_KEY_ID)
        return self._jwt_token

    async def _get_user_device_tokens(
        self, db: AsyncSession, user_id: str, platform: Optional[str] = None
    ) -> List[str]:
        """Fetch active device tokens for a user."""
        query = select(UserDevice.device_token).where(
            UserDevice.user_id == user_id,
            UserDevice.is_active == True,
        )
        if platform:
            query = query.where(UserDevice.platform == platform)

        result = await db.execute(query)
        return [row[0] for row in result.fetchall()]

    async def _send_notification(
        self,
        device_token: str,
        title: str,
        body: str,
        category: str,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send a single push notification via APNs HTTP/2.

        Args:
            device_token: APNs device token
            title: Notification title
            body: Notification body text
            category: APNs notification category (for actionable notifications)
            extra_data: Additional data payload

        Returns:
            Dict with status and optional error information
        """
        if not settings.APNS_KEY_ID or not settings.APNS_TEAM_ID:
            logger.warning("apns_not_configured", reason="Missing APNS_KEY_ID or APNS_TEAM_ID")
            return {"status": "skipped", "reason": "APNs not configured"}

        try:
            token = self._get_jwt_token()
        except FileNotFoundError as e:
            logger.warning("apns_auth_key_missing", error=str(e))
            return {"status": "skipped", "reason": str(e)}

        url = f"{self._base_url}/3/device/{device_token}"
        headers = {
            "authorization": f"bearer {token}",
            "apns-topic": settings.APNS_BUNDLE_ID,
            "apns-push-type": "alert",
            "apns-priority": "10",
        }

        payload = {
            "aps": {
                "alert": {
                    "title": title,
                    "body": body,
                },
                "sound": "default",
                "category": category,
                "thread-id": category,
            }
        }
        if extra_data:
            payload.update(extra_data)

        try:
            async with httpx.AsyncClient(http2=True) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=10.0,
                )

            if response.status_code == 200:
                logger.info(
                    "apns_sent",
                    device_token=device_token[:8] + "...",
                    category=category,
                )
                return {"status": "sent", "device_token": device_token[:8] + "..."}

            error_body = response.json() if response.content else {}
            reason = error_body.get("reason", "unknown")
            logger.error(
                "apns_failed",
                status=response.status_code,
                reason=reason,
                device_token=device_token[:8] + "...",
            )
            return {
                "status": "error",
                "reason": reason,
                "status_code": response.status_code,
            }

        except httpx.TimeoutException:
            logger.error("apns_timeout", device_token=device_token[:8] + "...")
            return {"status": "error", "reason": "timeout"}
        except Exception as e:
            logger.error("apns_exception", error=str(e))
            return {"status": "error", "reason": str(e)}

    async def _send_to_user(
        self,
        db: AsyncSession,
        user_id: str,
        title: str,
        body: str,
        category: str,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Send a notification to all active devices for a user."""
        device_tokens = await self._get_user_device_tokens(db, user_id, platform="ios")
        if not device_tokens:
            logger.debug("apns_no_devices", user_id=user_id)
            return [{"status": "skipped", "reason": "No active iOS devices"}]

        results = []
        for token in device_tokens:
            result = await self._send_notification(token, title, body, category, extra_data)
            results.append(result)

        return results

    async def notify_trade_approval(
        self,
        db: AsyncSession,
        user_id: str,
        execution_id: str,
        pipeline_name: str,
        symbol: str,
    ) -> List[Dict[str, Any]]:
        """
        Send a push notification requesting trade approval.

        Args:
            db: Async database session
            user_id: User UUID
            execution_id: Execution UUID
            pipeline_name: Name of the pipeline
            symbol: Trading symbol (e.g. AAPL)

        Returns:
            List of delivery results per device
        """
        title = f"Trade Approval: {symbol}"
        body = f"{pipeline_name} wants to execute a trade on {symbol}. Tap to review."
        extra_data = {
            "execution_id": execution_id,
            "pipeline_name": pipeline_name,
            "symbol": symbol,
            "action": "trade_approval",
        }

        return await self._send_to_user(
            db, user_id, title, body, "TRADE_APPROVAL", extra_data
        )

    async def notify_position_closed(
        self,
        db: AsyncSession,
        user_id: str,
        execution_id: str,
        pipeline_name: str,
        symbol: str,
        pnl: float,
    ) -> List[Dict[str, Any]]:
        """
        Send a push notification when a position is closed.

        Args:
            db: Async database session
            user_id: User UUID
            execution_id: Execution UUID
            pipeline_name: Name of the pipeline
            symbol: Trading symbol
            pnl: Profit/loss amount

        Returns:
            List of delivery results per device
        """
        pnl_sign = "+" if pnl >= 0 else ""
        title = f"Position Closed: {symbol}"
        body = f"{pipeline_name} closed {symbol} with {pnl_sign}${pnl:.2f} P&L."
        extra_data = {
            "execution_id": execution_id,
            "pipeline_name": pipeline_name,
            "symbol": symbol,
            "pnl": pnl,
            "action": "position_closed",
        }

        return await self._send_to_user(
            db, user_id, title, body, "POSITION_CLOSED", extra_data
        )

    async def notify_pipeline_failed(
        self,
        db: AsyncSession,
        user_id: str,
        execution_id: str,
        pipeline_name: str,
        error: str,
    ) -> List[Dict[str, Any]]:
        """
        Send a push notification when a pipeline fails.

        Args:
            db: Async database session
            user_id: User UUID
            execution_id: Execution UUID
            pipeline_name: Name of the pipeline
            error: Error description

        Returns:
            List of delivery results per device
        """
        title = f"Pipeline Failed: {pipeline_name}"
        body = f"{error[:100]}..." if len(error) > 100 else error
        extra_data = {
            "execution_id": execution_id,
            "pipeline_name": pipeline_name,
            "error": error,
            "action": "pipeline_failed",
        }

        return await self._send_to_user(
            db, user_id, title, body, "PIPELINE_FAILED", extra_data
        )

    async def notify_risk_rejected(
        self,
        db: AsyncSession,
        user_id: str,
        execution_id: str,
        pipeline_name: str,
        reason: str,
    ) -> List[Dict[str, Any]]:
        """
        Send a push notification when a trade is rejected by risk management.

        Args:
            db: Async database session
            user_id: User UUID
            execution_id: Execution UUID
            pipeline_name: Name of the pipeline
            reason: Rejection reason

        Returns:
            List of delivery results per device
        """
        title = f"Trade Rejected: {pipeline_name}"
        body = f"Risk manager blocked trade: {reason[:100]}"
        extra_data = {
            "execution_id": execution_id,
            "pipeline_name": pipeline_name,
            "reason": reason,
            "action": "risk_rejected",
        }

        return await self._send_to_user(
            db, user_id, title, body, "RISK_REJECTED", extra_data
        )


# Singleton instance
apns_service = APNsService()
