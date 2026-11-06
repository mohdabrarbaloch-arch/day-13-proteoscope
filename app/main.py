"""FastAPI application: middleware, routers, error handling, static SPA."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.ratelimit import Limit, RateLimiter
from app.routers import auth, health, predictions

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Proteoscope API",
    description="Deterministic, explainable protein structure analysis.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rate limiting (in-process sliding window) ---
_limiter = RateLimiter()
_limits = {
    "/api/auth": Limit.parse(settings.rate_limit_auth),
    "/api/predictions": Limit.parse(settings.rate_limit_predict),
}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply a per-IP sliding-window limit to API routes."""
    path = request.url.path
    if path.startswith("/api"):
        limit = next((v for k, v in _limits.items() if path.startswith(k)), Limit.parse(settings.rate_limit_default))
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = _limiter.check(client_ip, limit)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": str(int(retry_after))},
            )
    return await call_next(request)


# --- Routers ---
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(predictions.router)


# --- Static SPA ---
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# --- Error handling ---
@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler so a crash returns JSON, not an HTML stack trace."""
    if settings.debug:
        return JSONResponse(status_code=500, content={"detail": f"Internal error: {exc}"})
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """A minimal set of security headers (helmet-style, no extra dependency)."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response