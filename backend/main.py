from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import get_db

from api import router as stocks_router


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

app.include_router(stocks_router)


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