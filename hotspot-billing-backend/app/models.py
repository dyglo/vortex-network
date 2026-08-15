from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_tracking_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    merchant_reference: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    plan_name: Mapped[str] = mapped_column(String(50))
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    voucher: Mapped["Voucher | None"] = relationship(back_populates="transaction", uselist=False)


class Voucher(Base):
    __tablename__ = "vouchers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), unique=True)
    plan_name: Mapped[str] = mapped_column(String(50))
    mikrotik_username: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(12), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    transaction: Mapped[Transaction] = relationship(back_populates="voucher")


class PlanConfig(BaseModel):
    name: str
    price: int
    speed_label: str
    duration_hours: int
    mikrotik_profile_name: str
    rate_limit: str


class InitiatePaymentRequest(BaseModel):
    plan_name: str
    phone: str = Field(min_length=9, max_length=20)


class InitiatePaymentResponse(BaseModel):
    transaction_id: int
    redirect_url: str
    status: Literal["pending"]


class VoucherResponse(BaseModel):
    code: str
    username: str
    password: str
    plan_name: str
    expires_at: datetime


class PaymentStatusResponse(BaseModel):
    status: Literal["pending", "completed", "failed"]
    voucher: VoucherResponse | None = None


class RetrieveVoucherRequest(BaseModel):
    phone: str = Field(min_length=9, max_length=20)
