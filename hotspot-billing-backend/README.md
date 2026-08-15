# Hotspot Billing API

The frontend lives at the repository root; this independent FastAPI project runs the payment, voucher, router, and scheduler work.

1. Create a virtual environment and install `pip install -r requirements.txt`.
2. Fill `PESAPAL_CONSUMER_KEY`, `PESAPAL_CONSUMER_SECRET`, and the MikroTik connection fields in `.env`.
3. Set `PUBLIC_API_URL` to a public HTTPS address (ngrok works for sandbox), then run `python -m app.register_ipn`. Save the printed ID as `PESAPAL_IPN_ID`.
4. Run `python run.py`.

Pesapal API 3.0 sandbox and production endpoints are already in `.env`. IPNs are always verified against Pesapal before a voucher is issued.

## Temporary payment diagnostics

Set a non-empty `DEBUG_API_TOKEN` in `.env`, restart the API, then call:

```powershell
Invoke-RestMethod http://localhost:8000/api/debug/transactions -Headers @{ "X-Debug-Token" = "<your token>" }
```

The response contains every transaction, its local status, the Pesapal tracking ID, and linked voucher credentials when one exists. This endpoint intentionally returns secrets, so it is disabled unless the token is configured and should be removed after the sandbox investigation.
