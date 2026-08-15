from __future__ import annotations

from datetime import datetime
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import get_db
from app.models import InitiatePaymentRequest, InitiatePaymentResponse, PaymentStatusResponse, PlanConfig, Transaction, Voucher, VoucherResponse
from app.services import mikrotik, pesapal
from app.services.voucher import calculate_expiry, generate_voucher_code

router = APIRouter(tags=["payments"])
logger = logging.getLogger(__name__)

PLANS = {
    "DAY PASS": PlanConfig(name="DAY PASS", price=2000, speed_label="10 Mbps", duration_hours=24, mikrotik_profile_name="day-pass", rate_limit="10M/10M"),
    "WEEK PASS": PlanConfig(name="WEEK PASS", price=8000, speed_label="15 Mbps", duration_hours=168, mikrotik_profile_name="week-pass", rate_limit="15M/15M"),
    "MONTH PASS": PlanConfig(name="MONTH PASS", price=25000, speed_label="20 Mbps", duration_hours=720, mikrotik_profile_name="month-pass", rate_limit="20M/20M"),
}


def normalize_phone(phone: str) -> str:
    digits = "".join(char for char in phone if char.isdigit())
    if digits.startswith("0"):
        digits = "256" + digits[1:]
    elif len(digits) == 9 and digits.startswith("7"):
        digits = "256" + digits
    if not digits.startswith("256") or len(digits) != 12:
        raise HTTPException(422, "Use a valid Ugandan phone number, e.g. 0771234567.")
    return f"+{digits}"


def voucher_response(voucher: Voucher) -> VoucherResponse:
    return VoucherResponse(code=voucher.code, username=voucher.mikrotik_username, password=voucher.code, plan_name=voucher.plan_name, expires_at=voucher.expires_at)


def map_status(pesapal_status: str | None) -> str:
    value = (pesapal_status or "").upper()
    if value == "COMPLETED": return "completed"
    if value in {"FAILED", "INVALID", "CANCELLED"}: return "failed"
    return "pending"


def issue_voucher_if_needed(db: Session, transaction: Transaction) -> Voucher | None:
    if transaction.status != "completed":
        logger.info(
            "Voucher creation skipped transaction_id=%s: local status=%s (requires completed)",
            transaction.id, transaction.status,
        )
        return None
    if transaction.voucher:
        logger.info(
            "Voucher creation skipped transaction_id=%s: voucher_id=%s already exists",
            transaction.id, transaction.voucher.id,
        )
        return transaction.voucher
    plan = PLANS[transaction.plan_name]
    code = generate_voucher_code()
    expiry = calculate_expiry(plan.duration_hours)
    logger.info(
        "Voucher creation starting transaction_id=%s plan=%s username=%s",
        transaction.id, plan.name, code,
    )
    try:
        mikrotik.create_hotspot_user(code, code, plan.mikrotik_profile_name, f"expires={expiry.isoformat()}")
    except RuntimeError as exc:
        # Do not mark fulfillment complete if the router was unreachable. A later status check retries safely.
        logger.exception("Voucher creation failed transaction_id=%s while provisioning MikroTik", transaction.id)
        raise HTTPException(503, f"Payment confirmed but voucher provisioning is temporarily unavailable: {exc}") from exc
    try:
        voucher = Voucher(code=code, transaction_id=transaction.id, plan_name=plan.name, mikrotik_username=code, expires_at=expiry, status="active")
        db.add(voucher); db.commit(); db.refresh(voucher)
    except Exception:
        db.rollback()
        logger.exception("Voucher creation failed transaction_id=%s while saving to the database", transaction.id)
        raise
    logger.info(
        "Voucher creation succeeded transaction_id=%s voucher_id=%s username=%s expires_at=%s",
        transaction.id, voucher.id, voucher.mikrotik_username, voucher.expires_at.isoformat(),
    )
    return voucher


@router.post("/payment/initiate", response_model=InitiatePaymentResponse, status_code=201)
async def initiate_payment(request: InitiatePaymentRequest, db: Session = Depends(get_db)):
    plan = PLANS.get(request.plan_name.upper())
    if not plan: raise HTTPException(422, "Unknown plan.")
    phone = normalize_phone(request.phone)
    reference = f"wifi-{uuid4().hex[:24]}"
    transaction = Transaction(merchant_reference=reference, phone=phone, plan_name=plan.name, amount=plan.price, status="pending")
    db.add(transaction); db.commit(); db.refresh(transaction)
    logger.info("Payment initiated transaction_id=%s merchant_reference=%s plan=%s amount=%s", transaction.id, reference, plan.name, plan.price)
    try:
        callback_url = f"{settings.frontend_url}/?transaction_id={transaction.id}"
        order = await pesapal.submit_order_request(reference, plan.price, "UGX", f"{plan.name} WiFi voucher", callback_url, phone)
        transaction.order_tracking_id = order["order_tracking_id"]; db.commit()
        logger.info("Pesapal order submitted transaction_id=%s order_tracking_id=%s", transaction.id, transaction.order_tracking_id)
    except Exception as exc:
        transaction.status = "failed"; db.commit()
        logger.exception("Pesapal order submission failed transaction_id=%s", transaction.id)
        raise HTTPException(502, str(exc)) from exc
    return InitiatePaymentResponse(transaction_id=transaction.id, redirect_url=order["redirect_url"], status="pending")


@router.get("/payment/status/{transaction_id}", response_model=PaymentStatusResponse)
async def payment_status(transaction_id: int, db: Session = Depends(get_db)):
    transaction = db.get(Transaction, transaction_id)
    if not transaction: raise HTTPException(404, "Transaction not found.")
    if transaction.status == "pending" and transaction.order_tracking_id:
        try:
            result = await pesapal.get_transaction_status(transaction.order_tracking_id)
            pesapal_status = result.get("payment_status_description") or result.get("status")
            transaction.status = map_status(pesapal_status); db.commit(); db.refresh(transaction)
            logger.info(
                "Payment status checked transaction_id=%s order_tracking_id=%s pesapal_status=%r mapped_status=%s",
                transaction.id, transaction.order_tracking_id, pesapal_status, transaction.status,
            )
        except Exception as exc:
            logger.exception("Pesapal status check failed transaction_id=%s", transaction.id)
            raise HTTPException(502, f"Could not confirm payment status: {exc}") from exc
    elif transaction.status == "pending":
        logger.warning("Payment status check skipped transaction_id=%s: no Pesapal order_tracking_id", transaction.id)
    else:
        logger.info("Payment status check skipped transaction_id=%s: local status=%s", transaction.id, transaction.status)
    voucher = issue_voucher_if_needed(db, transaction)
    return PaymentStatusResponse(status=transaction.status, voucher=voucher_response(voucher) if voucher else None)


@router.api_route("/pesapal-ipn", methods=["GET", "POST"])
async def pesapal_ipn(OrderTrackingId: str = Query(...), OrderMerchantReference: str = Query(...), OrderNotificationType: str = Query("IPNCHANGE"), db: Session = Depends(get_db)):
    # The IPN itself has no payment status. Confirm it with Pesapal before updating the local order.
    logger.info("Pesapal IPN received order_tracking_id=%s merchant_reference=%s notification_type=%s", OrderTrackingId, OrderMerchantReference, OrderNotificationType)
    transaction = db.query(Transaction).filter(Transaction.merchant_reference == OrderMerchantReference).first()
    if transaction and transaction.order_tracking_id == OrderTrackingId:
        result = await pesapal.get_transaction_status(OrderTrackingId)
        pesapal_status = result.get("payment_status_description") or result.get("status")
        transaction.status = map_status(pesapal_status); db.commit()
        logger.info(
            "Pesapal IPN verified transaction_id=%s pesapal_status=%r mapped_status=%s",
            transaction.id, pesapal_status, transaction.status,
        )
        issue_voucher_if_needed(db, transaction)
    elif not transaction:
        logger.warning("Pesapal IPN ignored: no transaction for merchant_reference=%s", OrderMerchantReference)
    else:
        logger.warning(
            "Pesapal IPN ignored transaction_id=%s: tracking ID mismatch received=%s expected=%s",
            transaction.id, OrderTrackingId, transaction.order_tracking_id,
        )
    return {"orderNotificationType": OrderNotificationType, "orderTrackingId": OrderTrackingId, "orderMerchantReference": OrderMerchantReference, "status": 200}


@router.get("/debug/transactions")
def debug_transactions(x_debug_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Temporary diagnostic view. Requires DEBUG_API_TOKEN to be configured."""
    if not settings.debug_api_token or x_debug_token != settings.debug_api_token:
        raise HTTPException(404, "Not found.")
    transactions = (
        db.query(Transaction)
        .options(selectinload(Transaction.voucher))
        .order_by(Transaction.created_at.desc())
        .all()
    )
    return {
        "transactions": [
            {
                "id": transaction.id,
                "merchant_reference": transaction.merchant_reference,
                "order_tracking_id": transaction.order_tracking_id,
                "phone": transaction.phone,
                "plan_name": transaction.plan_name,
                "amount": transaction.amount,
                "status": transaction.status,
                "created_at": transaction.created_at,
                "voucher": (
                    {
                        "id": transaction.voucher.id,
                        "code": transaction.voucher.code,
                        "username": transaction.voucher.mikrotik_username,
                        "password": transaction.voucher.code,
                        "status": transaction.voucher.status,
                        "expires_at": transaction.voucher.expires_at,
                        "created_at": transaction.voucher.created_at,
                    }
                    if transaction.voucher else None
                ),
            }
            for transaction in transactions
        ]
    }
