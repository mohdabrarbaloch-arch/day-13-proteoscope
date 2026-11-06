"""ORM models: users and saved predictions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    """An account. Passwords are stored only as bcrypt hashes."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow
    )

    predictions: Mapped[list[Prediction]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Prediction(Base):
    """A saved structure prediction.

    The full result is stored as JSON text rather than exploded into columns.
    The shape of a prediction is the engine's business, and pinning it to a
    schema here would mean a migration every time the engine gains a field.
    """

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    sequence: Mapped[str] = mapped_column(Text, nullable=False)
    length: Mapped[int] = mapped_column(Integer, nullable=False)
    mean_confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    helix_fraction: Mapped[float] = mapped_column(nullable=False, default=0.0)
    sheet_fraction: Mapped[float] = mapped_column(nullable=False, default=0.0)
    contact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow
    )

    owner: Mapped[User] = relationship(back_populates="predictions")