from datetime import datetime
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.db import SessionLocal
from app.models import Voucher
from app.services import mikrotik

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")


def expire_vouchers() -> None:
    db = SessionLocal()
    try:
        vouchers = db.query(Voucher).filter(Voucher.status == "active", Voucher.expires_at < datetime.utcnow()).all()
        for voucher in vouchers:
            try:
                mikrotik.disable_hotspot_user(voucher.mikrotik_username)
                mikrotik.remove_active_session(voucher.mikrotik_username)
                voucher.status = "expired"
            except RuntimeError:
                logger.exception("Could not expire hotspot user %s; will retry", voucher.mikrotik_username)
        db.commit()
    finally:
        db.close()


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.add_job(expire_vouchers, "interval", minutes=5, id="expire-vouchers", replace_existing=True)
        scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running: scheduler.shutdown(wait=False)
