"""Pydantic request/response schemas.

Validation lives here so the routers stay thin. The sequence field is validated
for length and alphabet at the edge, before it ever reaches the engine.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.config import settings
from app.engine.sequence import AA_SET


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=120)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if v.strip() != v:
            raise ValueError("Password must not start or end with whitespace.")
        if v.isdigit() or v.isalpha():
            raise ValueError("Password must mix letters and numbers.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PredictRequest(BaseModel):
    """A prediction request. `sequence` accepts a bare sequence or FASTA."""

    sequence: str = Field(min_length=1, max_length=20000)
    label: str = Field(default="", max_length=160)
    save: bool = False
    include_profile: bool = True

    @field_validator("sequence")
    @classmethod
    def check_sequence(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Sequence must not be empty.")
        # Cheap pre-check on the raw text; the engine does the authoritative
        # parse and raises SequenceError with a precise message.
        #
        # Header lines must be skipped first. A FASTA header like
        # ">sp|P00698|LYSC_CHICK Lysozyme C" is full of letters that are not
        # residues (O, Z, B...), and counting them rejects perfectly valid
        # input. The engine strips headers; this pre-check has to as well.
        body = "\n".join(line for line in v.splitlines() if not line.lstrip().startswith((">", ";")))
        letters = [c.upper() for c in body if c.isalpha()]
        if len(letters) < settings.min_sequence_length:
            raise ValueError(f"Sequence must contain at least {settings.min_sequence_length} residues.")
        if len(letters) > settings.max_sequence_length:
            raise ValueError(
                f"Sequence is {len(letters)} residues; the limit is " f"{settings.max_sequence_length}."
            )
        bad = sorted({c for c in letters if c not in AA_SET})
        if bad:
            raise ValueError("Sequence contains non-standard residues: " + ", ".join(bad[:10]) + ".")
        return v


class PredictionSummary(BaseModel):
    id: int
    label: str
    length: int
    mean_confidence: float
    helix_fraction: float
    sheet_fraction: float
    contact_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PredictionDetail(PredictionSummary):
    sequence: str
    result: dict


class HealthResponse(BaseModel):
    status: str
    app: str
    engine: str
    version: str
    environment: str
