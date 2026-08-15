import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import Base, engine
from app.routers import payment, voucher
from app.scheduler import start_scheduler, stop_scheduler
from app.services import mikrotik

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Hotspot Billing API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_url], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(payment.router, prefix="/api")
app.include_router(voucher.router, prefix="/api")
app.include_router(payment.router, prefix="/webhook", include_in_schema=False)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    start_scheduler()
    try:
        api = mikrotik.get_connection(); api.close(); logger.info("MikroTik connection verified")
    except RuntimeError as exc:
        logger.warning("MikroTik unavailable at startup; voucher issuance will retry after it is reachable: %s", exc)


@app.on_event("shutdown")
def shutdown() -> None:
    stop_scheduler()


@app.get("/health")
def health():
    return {"status": "ok"}
