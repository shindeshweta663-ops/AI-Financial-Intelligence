import os
import datetime as dt

import razorpay
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User

load_dotenv()

router = APIRouter(prefix="/api/payment", tags=["payment"])

PLANS = {"annual": {"amount": 99900, "days": 365}}   # amount in paise (Rs 999)


def _client() -> razorpay.Client:
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise HTTPException(503, "Payment service is not configured")
    return razorpay.Client(auth=(key_id, key_secret))


class CreateOrderIn(BaseModel):
    plan: str = "annual"
    method: str = "upi"


class VerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


def is_premium(user: User) -> bool:
    return (
        user.subscription_status == "active"
        and (user.expiry_date is None or user.expiry_date > dt.datetime.now())
    )


def require_premium(user: User = Depends(get_current_user)) -> User:
    """Use as a dependency on premium-only endpoints."""
    if not is_premium(user):
        raise HTTPException(403, "An active subscription is required")
    return user


@router.post("/create-order")
def create_order(body: CreateOrderIn, user: User = Depends(get_current_user)):
    plan = PLANS.get(body.plan)
    if plan is None:
        raise HTTPException(400, "Unknown plan")
    client = _client()
    try:
        order = client.order.create({
            "amount": plan["amount"],            # server decides the price
            "currency": "INR",
            "receipt": f"u{user.user_id}_{int(dt.datetime.now().timestamp())}",
            "notes": {"user_id": str(user.user_id), "plan": body.plan},
        })
    except Exception:
        raise HTTPException(502, "Could not create the payment order")
    return {
        "order_id": order["id"],
        "key_id": os.getenv("RAZORPAY_KEY_ID"),
        "amount": order["amount"],
        "currency": order["currency"],
    }


@router.post("/verify")
def verify(body: VerifyIn, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    # Repeated callback for a payment we already activated -> same answer
    if user.payment_id == body.razorpay_payment_id and is_premium(user):
        return {"status": "success"}

    client = _client()

    # 1) signature must match (proves Razorpay produced these ids)
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": body.razorpay_order_id,
            "razorpay_payment_id": body.razorpay_payment_id,
            "razorpay_signature": body.razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        return {"status": "failed"}

    # 2) ask Razorpay directly: right owner, right amount, payment captured
    try:
        order = client.order.fetch(body.razorpay_order_id)
        payment = client.payment.fetch(body.razorpay_payment_id)
    except Exception:
        return {"status": "pending"}

    plan = PLANS.get((order.get("notes") or {}).get("plan", ""))
    if (
        plan is None
        or (order.get("notes") or {}).get("user_id") != str(user.user_id)
        or order.get("amount") != plan["amount"]
        or payment.get("order_id") != body.razorpay_order_id
    ):
        return {"status": "failed"}
    if payment.get("status") == "authorized":
        return {"status": "pending"}
    if payment.get("status") != "captured":
        return {"status": "failed"}

    # 3) activate (extend if the user is renewing early)
    now = dt.datetime.now()
    base = user.expiry_date if (user.expiry_date and user.expiry_date > now) else now
    if not (user.expiry_date and user.expiry_date > now):
        user.start_date = now
    user.expiry_date = base + dt.timedelta(days=plan["days"])
    user.subscription_status = "active"
    user.payment_status = "paid"
    user.payment_id = body.razorpay_payment_id
    db.commit()
    return {"status": "success"}


@router.get("/status")
def status(order_id: str = Query(...), user: User = Depends(get_current_user)):
    try:
        order = _client().order.fetch(order_id)
    except Exception:
        return {"status": "failed"}
    if (order.get("notes") or {}).get("user_id") != str(user.user_id):
        return {"status": "failed"}
    if order.get("status") == "paid":
        return {"status": "success" if is_premium(user) else "pending"}
    return {"status": "pending"}