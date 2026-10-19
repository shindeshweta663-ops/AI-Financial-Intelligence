from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import get_db

from api import router as stocks_router
from api_auth import router as auth_router
from api_economic import router as economic_router
from api_risk import router as risk_router
from api_search import router as search_router
from api_volatility import router as volatility_router
from api_watchlist import router as watchlist_router
from api_market import router as market_router
from api_payment import router as payment_router
from api_screener import router as screener_router
from api_predictions import router as predictions_router
from api_account import router as account_router



# ---------- Response models (Pydantic) ----------
class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime


class DatabaseHealthResponse(BaseModel):
    status: str
    database: str
    timestamp: datetime


class RootResponse(BaseModel):
    message: str
    docs_url: str


# ---------- App instance ----------
app = FastAPI(
    title=settings.app_name,
    description=(
        "Backend API for the AI-Powered Financial Intelligence & "
        "Investment Analytics Platform. Provides market data, technical "
        "analysis, news sentiment, risk analysis and ML predictions. "
        "Outputs are analytical tools, not financial advice."
    ),
    version=settings.app_version,
)

app.include_router(auth_router)
# search must be included BEFORE stocks_router, so "/api/stocks/search" is not
# mistaken for "/api/stocks/{symbol}".
app.include_router(search_router)
app.include_router(screener_router)
app.include_router(stocks_router)
app.include_router(economic_router)
app.include_router(risk_router)
app.include_router(volatility_router)
app.include_router(watchlist_router)
app.include_router(market_router)
app.include_router(payment_router) 
app.include_router(predictions_router)
app.include_router(account_router)

# Serve the frontend pages from the same address as the API (at /app/), so the
# login cookie works without cross-site settings.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


# ---------- Endpoints ----------
@app.get("/", response_model=RootResponse, tags=["General"])
def root():
    """Welcome endpoint."""
    return RootResponse(
        message="AI Financial Intelligence API is running",
        docs_url="/docs",
    )


@app.get("/health", response_model=HealthResponse, tags=["General"])
def health_check():
    """Confirms the API server is up."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/health/db", response_model=DatabaseHealthResponse, tags=["General"])
def database_health_check(db: Session = Depends(get_db)):
    """Confirms the API can reach PostgreSQL using a request session."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        # 503 = service unavailable. We don't expose internal error details.
        raise HTTPException(status_code=503, detail="Database is not reachable")

    return DatabaseHealthResponse(
        status="ok",
        database="connected",
        timestamp=datetime.now(timezone.utc),
    )