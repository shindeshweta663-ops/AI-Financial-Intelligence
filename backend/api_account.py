"""Account endpoints for the dashboard (Phase 16).

GET /api/payments       -> the user's latest recorded payment (login required)
GET /api/notifications  -> real notices derived from the user's subscription

Honest limits:
- The database keeps only the LATEST payment per user (users.payment_id,
  payment_status, start_date), so this list has at most one row. An early
  renewal replaces the earlier payment.
- The amount is not stored per payment; it comes from PLANS in api_payment.py
  and is only right while there is a single plan. Shown in rupees.
- Notifications are not stored anywhere; they are worked out on each request.
"""
import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api_payment import PLANS, is_premium
from auth import get_current_user

router = APIRouter(tags=["account"])

ENDING_SOON_DAYS = 7


class PaymentOut(BaseModel):
    id: str
    reference: str
    date: Optional[str]
    amount: float
    currency: str
    status: str
    plan: str


class PaymentsOut(BaseModel):
    items: List[PaymentOut]
    note: str


class NotificationOut(BaseModel):
    id: str
    title: str
    message: str
    created_at: str
    read: bool


class NotificationsOut(BaseModel):
    items: List[NotificationOut]


def payment_rows(user) -> List[dict]:
    """The one payment we can show, or [] if the user never paid."""
    if not user.payment_id or (user.payment_status or "").lower() not in ("paid", "pending", "failed"):
        return []
    plan_name = "annual"
    return [{
        "id": user.payment_id,
        "reference": user.payment_id,
        "date": user.start_date.isoformat() if user.start_date else None,
        "amount": PLANS[plan_name]["amount"] / 100.0,  # paise -> rupees
        "currency": "INR",
        "status": (user.payment_status or "pending").lower(),
        "plan": plan_name,
    }]


def notice_rows(user, now: dt.datetime) -> List[dict]:
    out = []
    expiry = user.expiry_date
    status = (user.subscription_status or "").lower()
    stamp = now.isoformat()
    if status == "active" and expiry and expiry <= now:
        out.append(("sub-expired", "Subscription expired",
                    f"Your subscription ended on {expiry:%d %b %Y}. Renew to keep premium access."))
    elif status == "active" and expiry and (expiry - now) <= dt.timedelta(days=ENDING_SOON_DAYS):
        out.append(("sub-ending", "Subscription ending soon",
                    f"Your subscription expires on {expiry:%d %b %Y}."))
    elif status != "active":
        out.append(("sub-inactive", "No active subscription",
                    "Subscribe to unlock premium features."))
    return [{"id": i, "title": t, "message": m, "created_at": stamp, "read": False} for i, t, m in out]


@router.get("/api/payments", response_model=PaymentsOut)
def list_payments(user=Depends(get_current_user)):
    return PaymentsOut(
        items=[PaymentOut(**r) for r in payment_rows(user)],
        note=("Only the latest payment is stored. The amount comes from the plan price "
              "(single annual plan), not from a per-payment record."),
    )


@router.get("/api/notifications", response_model=NotificationsOut)
def list_notifications(user=Depends(get_current_user)):
    return NotificationsOut(items=[NotificationOut(**r) for r in notice_rows(user, dt.datetime.now())])