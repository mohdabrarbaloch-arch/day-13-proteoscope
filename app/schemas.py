"""Pydantic request/response schemas.

Validation lives here so the routers stay thin. The sequence pre-check is a
cheap first line of defence; the engine does the authoritative validation.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config import settings

# Letters that are valid in a protein sequence (20 standard + B/Z/X).
_VALID_RESIDUES = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYBZX]+$", re.IGNORECASE)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class PredictRequest(BaseModel):
    sequence: str = Field(min_length=1, max_length=settings.max_sequence_length + 200)
    label: str = Field(default="", max_length=160)
    save: bool = False
    include_profile: bool = True

    @field_validator("sequence")
    @classmethod
    def check_sequence(cls, v: str) -> str:
        # Cheap pre-check on the raw text; the engine does the authoritative
        # validation (FASTA headers, whitespace, length, residue alphabet).
        text = v.strip()
        if not text:
            raise ValueError("sequence must not be empty")
        # A FASTA record starts with '>'; the header line is not sequence.
        if text.startswith(">"):
            lines = text.splitlines()
            body = "".join(lines[1:])
        else:
            body = "".join(text.split())
        if len(body) < settings.min_sequence_length:
            raise ValueError(f"sequence must be at least {settings.min_sequence_length} residues")
        if len(body) > settings.max_sequence_length:
            raise ValueError(f"sequence must be at most {settings.max_sequence_length} residues")
        if not _VALID_RESIDUES.match(body):
            raise ValueError("sequence contains invalid amino-acid letters")
        return v


class PredictionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    length: int
    mean_confidence: float
    helix_fraction: float
    sheet_fraction: float
    contact_count: int
    created_at: datetime


class PredictionDetail(PredictionSummary):
    sequence: str
    result_json: str


class HealthResponse(BaseModel):
    status: str
    app: str
    engine: str
    version: str
    environment: str