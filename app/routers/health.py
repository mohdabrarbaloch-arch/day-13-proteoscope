"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.engine.predict import ENGINE_NAME, ENGINE_VERSION
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe. Cheap, unauthenticated, no database access."""
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        engine=ENGINE_NAME,
        version=ENGINE_VERSION,
        environment=settings.environment,
    )
