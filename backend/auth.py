"""Password hashing, login tokens and the 'who is logged in' dependency.

Passwords are stored only as bcrypt hashes. A login is a signed token (JWT) kept in
an HttpOnly cookie, so page JavaScript cannot read it. The signing secret
(JWT_SECRET) lives only in .env.
"""
import datetime as dt
from typing import Optional, Tuple

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User

COOKIE_NAME = "fn_session"
ALGORITHM = "HS256"
SESSION_SECONDS = 24 * 60 * 60            # normal login: 1 day
REMEMBER_SECONDS = 30 * 24 * 60 * 60      # "Remember Me": 30 days
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72                   # bcrypt cannot use more than 72 bytes


def _secret() -> str:
    if len(settings.jwt_secret) < 32:
        raise RuntimeError(
            "JWT_SECRET is missing or shorter than 32 characters. Add a long random value to .env."
        )
    return settings.jwt_secret


def password_problem(password: str) -> Optional[str]:
    """Return a message if the password is not acceptable, otherwise None."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return f"Password must be at most {MAX_PASSWORD_BYTES} bytes."
    return None


def hash_password(password: str) -> str:
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """True only for a correct password. Never raises for bad input."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError, AttributeError):
        return False


_dummy_hash: Optional[str] = None


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check, so a login for an unknown email is not faster."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode("ascii")
    verify_password(password[:MAX_PASSWORD_BYTES], _dummy_hash)


def create_token(user_id: int, remember: bool = False) -> Tuple[str, int]:
    """Return (signed token, lifetime in seconds)."""
    lifetime = REMEMBER_SECONDS if remember else SESSION_SECONDS
    now = dt.datetime.now(dt.timezone.utc)
    claims = {"sub": str(user_id), "iat": now, "exp": now + dt.timedelta(seconds=lifetime)}
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM), lifetime


def decode_token(token: str) -> Optional[int]:
    """The user id inside a valid, unexpired token, otherwise None."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency for protected endpoints: the logged-in user, or a 401."""
    token = request.cookies.get(COOKIE_NAME)
    user_id = decode_token(token) if token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in")
    return user