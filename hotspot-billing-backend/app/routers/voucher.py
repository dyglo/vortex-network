from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RetrieveVoucherRequest, Transaction, Voucher
from app.routers.payment import normalize_phone, voucher_response

router = APIRouter(tags=["vouchers"])


@router.post("/voucher/retrieve", response_model=dict)
def retrieve_voucher(request: RetrieveVoucherRequest, db: Session = Depends(get_db)):
    phone = normalize_phone(request.phone)
    voucher = (db.query(Voucher).join(Transaction).filter(Transaction.phone == phone, Voucher.status == "active", Voucher.expires_at > datetime.utcnow()).order_by(Voucher.expires_at.desc()).first())
    if not voucher: raise HTTPException(404, "No active voucher found for this phone number.")
    return voucher_response(voucher).model_dump(mode="json")
