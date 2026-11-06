"""Prediction endpoints: run the engine, save, list, fetch, export."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.engine.predict import predict_structure
from app.engine.report import build_report, to_csv, to_pdb
from app.engine.sequence import SequenceError
from app.models import Prediction, User
from app.schemas import PredictionDetail, PredictionSummary, PredictRequest

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_prediction(
    payload: PredictRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    """Run a prediction. Optionally persist it.

    Works anonymously — the engine is a pure computation, so requiring an
    account to run it would be friction with no benefit. Saving needs an
    identity, so `save=true` without a token is a 401.

    Returns the full result inline. When `save` is true the prediction is also
    stored and the response carries its `id`.
    """
    if payload.save and user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to save a prediction.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        result = predict_structure(payload.sequence, include_profile=payload.include_profile)
    except SequenceError as exc:
        # A bad sequence is the caller's problem, not a server fault.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None

    response: dict = {"result": result, "saved": False, "id": None}

    if payload.save and user is not None:
        record = Prediction(
            owner_id=user.id,
            label=payload.label.strip() or (result["sequence"]["header"] or "Untitled"),
            sequence=result["sequence"]["cleaned"],
            length=result["sequence"]["length"],
            mean_confidence=result["structure"]["mean_confidence"],
            helix_fraction=result["secondary_structure"]["helix_fraction"],
            sheet_fraction=result["secondary_structure"]["sheet_fraction"],
            contact_count=result["contacts"]["count"],
            result_json=json.dumps(result),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        response["saved"] = True
        response["id"] = record.id

    return response


@router.get("", response_model=list[PredictionSummary])
def list_predictions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[PredictionSummary]:
    """List the caller's saved predictions, newest first."""
    rows = db.scalars(
        select(Prediction)
        .where(Prediction.owner_id == user.id)
        .order_by(Prediction.created_at.desc(), Prediction.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [PredictionSummary.model_validate(r) for r in rows]


@router.get("/{prediction_id}", response_model=PredictionDetail)
def get_prediction(
    prediction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PredictionDetail:
    """Fetch one saved prediction, including the full result."""
    record = db.get(Prediction, prediction_id)
    # 404 rather than 403 for someone else's record: a 403 would confirm the id
    # exists, which leaks information about other users' data.
    if record is None or record.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found.")

    return PredictionDetail(
        id=record.id,
        label=record.label,
        length=record.length,
        mean_confidence=record.mean_confidence,
        helix_fraction=record.helix_fraction,
        sheet_fraction=record.sheet_fraction,
        contact_count=record.contact_count,
        created_at=record.created_at,
        sequence=record.sequence,
        result=json.loads(record.result_json),
    )


@router.delete("/{prediction_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_prediction(
    prediction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Delete a saved prediction."""
    record = db.get(Prediction, prediction_id)
    if record is None or record.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found.")
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{prediction_id}/export", response_class=PlainTextResponse)
def export_prediction(
    prediction_id: int,
    fmt: str = Query(default="pdb", pattern="^(pdb|csv|txt)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlainTextResponse:
    """Export a saved prediction as PDB, CSV, or a text report."""
    record = db.get(Prediction, prediction_id)
    if record is None or record.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found.")

    result = json.loads(record.result_json)
    if fmt == "pdb":
        body, media, filename = to_pdb(result), "chemical/x-pdb", f"proteoscope-{record.id}.pdb"
    elif fmt == "csv":
        body, media, filename = to_csv(result), "text/csv", f"proteoscope-{record.id}.csv"
    else:
        body, media, filename = build_report(result), "text/plain", f"proteoscope-{record.id}.txt"

    return PlainTextResponse(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
