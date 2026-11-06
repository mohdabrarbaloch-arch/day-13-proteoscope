"""Application settings, loaded from the environment.

Every value has a safe default for local development, and the production guard
in ``validate()`` refuses to start with an insecure configuration.
"""

from __future__ import annotations

import os
import secrets


class Settings:
    """Typed access to configuration. Values come from the environment."""

    def __init__(self) -> None:
        self.environment: str = os.getenv("ENVIRONMENT", "development").lower()
        self.debug: bool = os.getenv("DEBUG", "false").lower() in {"1", "true", "yes", "on"}
        self.app_name: str = "Proteoscope"
        self.jwt_algorithm: str = "HS256"
        self.access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./proteoscope.db")
        self.max_sequence_length: int = int(os.getenv("MAX_SEQUENCE_LENGTH", "2000"))
        self.min_sequence_length: int = int(os.getenv("MIN_SEQUENCE_LENGTH", "10"))
        self.cors_origins: list[str] = [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:8013,http://127.0.0.1:8013").split(",")
            if o.strip()
        ]
        self.rate_limit_auth: str = os.getenv("RATE_LIMIT_AUTH", "10/minute")
        self.rate_limit_predict: str = os.getenv("RATE_LIMIT_PREDICT", "30/minute")
        self.rate_limit_default: str = os.getenv("RATE_LIMIT_DEFAULT", "120/minute")
        self.is_serverless: bool = os.getenv("VERCEL", "0") == "1"

        # A random key is generated per process when none is set. This keeps
        # local development working with zero config, but tokens will not
        # survive a restart — which is fine for dev and unacceptable in prod.
        self.secret_key: str = os.getenv("SECRET_KEY", "") or secrets.token_urlsafe(48)

        self.validate()

    def validate(self) -> None:
        """Refuse to run with an obviously insecure production config."""
        if self.environment == "production":
            if self.debug:
                raise RuntimeError("DEBUG must be false in production")
            if len(self.secret_key) < 32 or self.secret_key.startswith("dev-"):
                raise RuntimeError("SECRET_KEY must be set to a strong value in production")


settings = Settings()