from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_token: str | None = None
_token_expires_at: datetime | None = None

_PESAPAL_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_MAX_TIMEOUT_ATTEMPTS = 3


async def _pesapal_request(
    client: httpx.AsyncClient, method: str, url: str, **kwargs: Any
) -> httpx.Response:
    """Make a Pesapal request, retrying transient network timeouts."""
    for attempt in range(_MAX_TIMEOUT_ATTEMPTS):
        try:
            return await client.request(method, url, **kwargs)
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt == _MAX_TIMEOUT_ATTEMPTS - 1:
                raise
            backoff_seconds = attempt + 1
            logger.warning(
                "Pesapal %s request timed out; retrying in %s second(s) "
                "(attempt %s/%s)",
                method,
                backoff_seconds,
                attempt + 1,
                _MAX_TIMEOUT_ATTEMPTS,
            )
            await asyncio.sleep(backoff_seconds)


async def get_access_token() -> str:
    global _token, _token_expires_at
    now = datetime.now(timezone.utc)
    if _token and _token_expires_at and now < _token_expires_at:
        return _token
    if not settings.pesapal_consumer_key or not settings.pesapal_consumer_secret:
        raise RuntimeError("Set PESAPAL_CONSUMER_KEY and PESAPAL_CONSUMER_SECRET in backend/.env.")
    async with httpx.AsyncClient(timeout=_PESAPAL_TIMEOUT) as client:
        response = await _pesapal_request(
            client,
            "POST",
            f"{settings.pesapal_base_url}/api/Auth/RequestToken",
            json={
                "consumer_key": settings.pesapal_consumer_key,
                "consumer_secret": settings.pesapal_consumer_secret,
            },
        )
        response.raise_for_status()
        payload = response.json()
    if not payload.get("token"):
        raise RuntimeError(f"Pesapal token request failed: {payload}")
    _token = payload["token"]
    # Pesapal tokens last at most five minutes; renew early rather than trusting clock skew.
    _token_expires_at = now + timedelta(minutes=4, seconds=30)
    return _token


async def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {await get_access_token()}", "Accept": "application/json", "Content-Type": "application/json"}


async def register_ipn(callback_url: str) -> str:
    async with httpx.AsyncClient(timeout=_PESAPAL_TIMEOUT) as client:
        response = await _pesapal_request(
            client,
            "POST",
            f"{settings.pesapal_base_url}/api/URLSetup/RegisterIPN",
            headers=await _headers(),
            json={"url": callback_url, "ipn_notification_type": "GET"},
        )
        response.raise_for_status()
        payload = response.json()
    if not payload.get("ipn_id"):
        raise RuntimeError(f"Pesapal IPN registration failed: {payload}")
    return payload["ipn_id"]


async def submit_order_request(merchant_reference: str, amount: int, currency: str, description: str, callback_url: str, phone: str) -> dict:
    if not settings.pesapal_ipn_id:
        raise RuntimeError("PESAPAL_IPN_ID is empty. Register the public IPN URL first (see config.py).")
    payload = {
        "id": merchant_reference, "currency": currency, "amount": amount, "description": description,
        "callback_url": callback_url, "notification_id": settings.pesapal_ipn_id, "redirect_mode": "TOP_WINDOW",
        "billing_address": {"phone_number": phone, "country_code": "UG"},
    }
    async with httpx.AsyncClient(timeout=_PESAPAL_TIMEOUT) as client:
        response = await _pesapal_request(
            client,
            "POST",
            f"{settings.pesapal_base_url}/api/Transactions/SubmitOrderRequest",
            headers=await _headers(),
            json=payload,
        )
        response.raise_for_status()
        result = response.json()
    if not result.get("order_tracking_id") or not result.get("redirect_url"):
        raise RuntimeError(f"Pesapal order submission failed: {result}")
    return result


async def get_transaction_status(order_tracking_id: str) -> dict:
    async with httpx.AsyncClient(timeout=_PESAPAL_TIMEOUT) as client:
        response = await _pesapal_request(
            client,
            "GET",
            f"{settings.pesapal_base_url}/api/Transactions/GetTransactionStatus",
            headers=await _headers(),
            params={"orderTrackingId": order_tracking_id},
        )
        response.raise_for_status()
        result = response.json()
    # Keep the response fields which determine fulfilment visible in logs. Do
    # not log the full response: it can contain payer data.
    logger.info(
        "Pesapal GetTransactionStatus returned order_tracking_id=%s "
        "payment_status_description=%r status=%r payment_status_code=%r",
        order_tracking_id,
        result.get("payment_status_description"),
        result.get("status"),
        result.get("payment_status_code"),
    )
    return result


def verify_ipn_signature() -> bool:
    # API 3.0 IPNs have no HMAC signature. Never trust their payload as payment proof:
    # the router independently calls get_transaction_status before fulfilling an order.
    return True
