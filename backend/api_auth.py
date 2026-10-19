"""Login endpoints: /api/auth/register, /login, /me, /logout, /change-password.

Passwords are stored only as bcrypt hashes. A successful login sets a signed
token in an HttpOnly cookie (see auth.py). Nothing here returns a password
or a hash.
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import (
    COOKIE_NAME,
    burn_password_check,
    create_token,
    get_current_user,
    hash_password,
    password_problem,
    verify_password,
)
from config import settings
from database import get_db
from models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EMAIL_LENGTH = 150   # users.email is VARCHAR(150)
MAX_NAME_LENGTH = 100    # users.name is VARCHAR(100)
BAD_LOGIN = "Invalid email or password."


# ---------- request / response shapes ----------
class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str
    remember: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class SubscriptionOut(BaseModel):
    plan: str
    status: Optional[str]
    expires_at: Optional[str]
    payment_status: Optional[str]


class UserOut(BaseModel):
    user_id: int
    name: Optional[str]
    email: Optional[str]
    subscription: SubscriptionOut


# ---------- helpers ----------
def _clean_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    return email


def _user_out(user: User) -> UserOut:
    active = (user.subscription_status or "").lower() == "active"
    return UserOut(
        user_id=user.user_id,
        name=user.name,
        email=user.email,
        subscription=SubscriptionOut(
            plan="premium" if active else "free",   # derived: no plan column exists yet
            status=user.subscription_status,
            expires_at=user.expiry_date.isoformat() if user.expiry_date else None,
            payment_status=user.payment_status,
        ),
    )


def _set_cookie(response: Response, user_id: int, remember: bool) -> None:
    token, lifetime = create_token(user_id, remember)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=lifetime,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _find_user(db: Session, email: str) -> Optional[User]:
    return db.scalars(select(User).where(func.lower(User.email) == email)).first()


# ---------- endpoints ----------
@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    name = body.name.strip()
    if len(name) < 2 or len(name) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail="Name must be 2 to 100 characters.")
    email = _clean_email(body.email)
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if _find_user(db, email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(body.password),
        subscription_status="inactive",
        payment_status="pending",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:   # two sign-ups with the same email at the same moment
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    db.refresh(user)
    _set_cookie(response, user.user_id, remember=False)
    return _user_out(user)


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = _find_user(db, email)
    if user is None or not user.password_hash:
        burn_password_check(body.password)   # same time cost, so timing does not reveal accounts
        raise HTTPException(status_code=401, detail=BAD_LOGIN)
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail=BAD_LOGIN)
    _set_cookie(response, user.user_id, body.remember)
    return _user_out(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return {"message": "Logged out."}


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    problem = password_problem(body.new_password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="New password must be different.")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"message": "Password changed."}