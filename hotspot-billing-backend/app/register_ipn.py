import asyncio

from app.config import settings
from app.services.pesapal import register_ipn


async def main() -> None:
    ipn_id = await register_ipn(settings.ipn_url)
    print(f"Registered {settings.ipn_url}. Set PESAPAL_IPN_ID={ipn_id} in backend/.env")


if __name__ == "__main__":
    asyncio.run(main())
