"""Application configuration.

One-time IPN setup
------------------
Pesapal requires a publicly reachable IPN URL before it accepts payment orders.
Once the API is live (or exposed with ngrok), run ``python -m app.register_ipn``.
Copy the printed ``ipn_id`` into ``PESAPAL_IPN_ID`` in ``.env`` and restart the API.
Do this separately for sandbox and production: IPN IDs are environment-specific.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Settings:
    pesapal_consumer_key = os.getenv("PESAPAL_CONSUMER_KEY", "")
    pesapal_consumer_secret = os.getenv("PESAPAL_CONSUMER_SECRET", "")
    pesapal_ipn_id = os.getenv("PESAPAL_IPN_ID", "")
    pesapal_env = os.getenv("PESAPAL_ENV", "sandbox").lower()
    pesapal_sandbox_base_url = os.getenv("PESAPAL_SANDBOX_BASE_URL", "https://cybqa.pesapal.com/pesapalv3")
    pesapal_production_base_url = os.getenv("PESAPAL_PRODUCTION_BASE_URL", "https://pay.pesapal.com/v3")
    public_api_url = os.getenv("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    database_url = os.getenv("DATABASE_URL", "sqlite:///./hotspot_billing.db")
    mikrotik_host = os.getenv("MIKROTIK_HOST", "")
    mikrotik_port = int(os.getenv("MIKROTIK_PORT", "8728"))
    mikrotik_user = os.getenv("MIKROTIK_USER", "admin")
    mikrotik_password = os.getenv("MIKROTIK_PASSWORD", "")
    # Intentionally opt-in: this endpoint exposes payment data and hotspot
    # credentials, so it must never be available anonymously in production.
    debug_api_token = os.getenv("DEBUG_API_TOKEN", "")

    @property
    def pesapal_base_url(self) -> str:
        return self.pesapal_production_base_url if self.pesapal_env == "production" else self.pesapal_sandbox_base_url

    @property
    def ipn_url(self) -> str:
        return f"{self.public_api_url}/webhook/pesapal-ipn"


settings = Settings()
