"""
Webhook Delivery with Retries (TP-019)

Delivers JSON payloads to external URLs with exponential backoff retries
and a structured delivery receipt.  Replaces the commented-out TODO in
TradeManagerAgent._send_webhook.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class DeliveryReceipt:
    """Record of a single webhook delivery attempt."""
    url: str
    status: str          # "delivered" | "failed" | "timeout"
    http_status: Optional[int] = None
    attempts: int = 0
    delivered_at: Optional[datetime] = None
    error: Optional[str] = None
    response_body: Optional[str] = None


class WebhookDelivery:
    """
    Send a JSON payload to a webhook URL with retry/backoff.

    Retry schedule (configurable):
        attempt 1 — immediate
        attempt 2 — 2 s delay
        attempt 3 — 4 s delay
        attempt 4 — 8 s delay

    A 2xx response is considered success.
    Non-2xx responses and connection errors are retried up to max_retries.
    """

    def __init__(
        self,
        timeout_s: float = 10.0,
        max_retries: int = 3,
        backoff_base_s: float = 2.0,
    ):
        self.timeout_s      = timeout_s
        self.max_retries    = max_retries
        self.backoff_base_s = backoff_base_s

    # ------------------------------------------------------------------
    # Sync entry point (used from non-async code in trade_manager_agent)
    # ------------------------------------------------------------------

    def send(self, url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> DeliveryReceipt:
        """
        Deliver payload to url.  Runs the async logic inside a new event loop
        if called from a sync context, otherwise awaits directly.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an existing event loop (e.g. FastAPI handler) —
                # schedule as a task and block via run_until_complete won't work.
                # Fall back to a thread-pool driven synchronous approach.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(asyncio.run, self._send_async(url, payload, headers))
                    return future.result()
            else:
                return loop.run_until_complete(self._send_async(url, payload, headers))
        except RuntimeError:
            return asyncio.run(self._send_async(url, payload, headers))

    # ------------------------------------------------------------------
    # Async implementation
    # ------------------------------------------------------------------

    async def _send_async(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> DeliveryReceipt:
        merged_headers = {"Content-Type": "application/json"}
        if headers:
            merged_headers.update(headers)

        receipt = DeliveryReceipt(url=url, status="failed")
        last_error: Optional[str] = None

        for attempt in range(1, self.max_retries + 2):   # +2 so we get max_retries retries
            receipt.attempts = attempt
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    resp = await client.post(url, json=payload, headers=merged_headers)

                receipt.http_status = resp.status_code
                receipt.response_body = resp.text[:500]  # truncate for safety

                if resp.is_success:
                    receipt.status = "delivered"
                    receipt.delivered_at = datetime.utcnow()
                    logger.info(
                        "webhook_delivered",
                        url=url,
                        attempt=attempt,
                        status=resp.status_code,
                    )
                    return receipt

                last_error = f"HTTP {resp.status_code}"
                logger.warning(
                    "webhook_non_2xx",
                    url=url,
                    attempt=attempt,
                    status=resp.status_code,
                )

            except httpx.TimeoutException as exc:
                last_error = f"Timeout after {self.timeout_s}s"
                receipt.status = "timeout"
                logger.warning("webhook_timeout", url=url, attempt=attempt)

            except Exception as exc:
                last_error = str(exc)
                logger.warning("webhook_error", url=url, attempt=attempt, error=last_error)

            # Backoff before next retry (skip delay after last attempt)
            if attempt <= self.max_retries:
                delay = self.backoff_base_s ** (attempt - 1)
                await asyncio.sleep(delay)

        receipt.status = receipt.status if receipt.status == "timeout" else "failed"
        receipt.error = last_error
        logger.error(
            "webhook_failed_all_retries",
            url=url,
            attempts=receipt.attempts,
            error=last_error,
        )
        return receipt
