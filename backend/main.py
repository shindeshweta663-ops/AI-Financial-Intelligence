from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

# ---------- Response models (Pydantic) ----------
class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime


class RootResponse(BaseModel):
    message: str
    docs_url: str


# ---------- App instance ----------
app = FastAPI(
    title="AI Financial Intelligence API",
    description=(
        "Backend API for the AI-Powered Financial Intelligence & "
        "Investment Analytics Platform. Provides market data, technical "
        "analysis, news sentiment, risk analysis and ML predictions. "
        "Outputs are analytical tools, not financial advice."
    ),
    version="0.1.0",
)


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
        service="AI Financial Intelligence API",
        version="0.1.0",
        timestamp=datetime.now(timezone.utc),
    )