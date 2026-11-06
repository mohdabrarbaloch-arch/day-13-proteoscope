"""Shared pytest fixtures.

Each test gets a fresh in-memory SQLite database and a fresh rate limiter, so
tests cannot leak state into each other.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the app at an in-memory database before anything imports app.config.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-hs256")
os.environ.setdefault("ENVIRONMENT", "test")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

# A real, well-known sequence: chicken lysozyme C, 78 residues.
LYSOZYME = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR"

# A short helix-forming peptide.
HELIX_PEPTIDE = "MEELLKKLEEALKKLEEALKKLEEALKKLEEALKKLEEALKKLEEALKKLEEALKKLEEALKK"

# A short sheet-forming peptide.
SHEET_PEPTIDE = "MIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVT"


@pytest.fixture(autouse=True)
def _fresh_db():
    """Recreate the schema and clear the rate limiter for every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.state.limiter.reset()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    """A client with a registered user and its token already attached."""
    resp = client.post(
        "/api/auth/register",
        json={"email": "researcher@example.com", "password": "helix1234", "full_name": "Researcher"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
