# Proteoscope — production image.
# Multi-stage so the final layer carries no build tooling.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build deps for psycopg2 and friends, removed in the same layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc

# --- runtime ---
FROM base AS runtime

# Run as a non-root user. A container that can write to its own code is a
# container that can be made to rewrite it.
RUN useradd --create-home --shell /bin/bash appuser

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser api ./api
COPY --chown=appuser:appuser pyproject.toml ./

USER appuser

ENV ENVIRONMENT=production \
    PORT=8013

EXPOSE 8013

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/api/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]