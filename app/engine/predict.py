"""The top-level prediction pipeline.

`predict_structure` is the one function the rest of the app calls. It runs the
stages in order and returns a single JSON-serialisable dict, so the API layer
never has to know how the pieces fit together.
"""

from __future__ import annotations

from app.engine.geometry import build_structure, predict_contacts
from app.engine.secondary import hydrophobic_moment, predict_secondary_structure
from app.engine.sequence import (
    THREE_LETTER,
    hydropathy_profile,
    parse_sequence,
    properties,
)

ENGINE_NAME = "Proteoscope"
ENGINE_VERSION = "1.0.0"

# What this engine is, stated plainly so nobody mistakes it for AlphaFold.
METHOD_NOTE = (
    "Deterministic, explainable structure analysis. Secondary structure uses "
    "Chou-Fasman propensities; contacts and the 3D trace come from a physical "
    "constraint model plus gradient relaxation. There are no learned weights "
    "and no network calls. Treat the output as a teaching and triage aid, not "
    "as an experimental structure."
)


def predict_structure(raw_sequence: str, *, include_profile: bool = True) -> dict:
    """Run the full pipeline on a raw sequence string.

    Args:
        raw_sequence: a bare sequence or a FASTA record.
        include_profile: whether to include the per-residue hydropathy and
            hydrophobic-moment arrays. They are useful for the UI but bulky, so
            callers that only want the summary can turn them off.

    Returns:
        A JSON-serialisable dict with the parsed sequence, properties,
        secondary structure, contact map, 3D trace, and confidence.

    Raises:
        SequenceError: if the sequence cannot be parsed.
    """
    parsed = parse_sequence(raw_sequence)
    sequence = parsed.sequence

    props = properties(sequence)
    secondary = predict_secondary_structure(sequence)
    contacts = predict_contacts(sequence, secondary)
    structure = build_structure(sequence, secondary, contacts)

    result: dict = {
        "engine": {"name": ENGINE_NAME, "version": ENGINE_VERSION, "method": METHOD_NOTE},
        "sequence": {
            "header": parsed.header,
            "length": parsed.length,
            "cleaned": sequence,
            "residues_removed": parsed.removed,
        },
        "properties": props,
        "secondary_structure": {
            "assignment": secondary.assignment,
            "helix_fraction": secondary.helix_fraction,
            "sheet_fraction": secondary.sheet_fraction,
            "turn_fraction": secondary.turn_fraction,
            "coil_fraction": secondary.coil_fraction,
            "segments": secondary.segments,
        },
        "contacts": {
            "count": contacts.count,
            "density": contacts.density,
            "max_sequence_separation": contacts.max_separation,
            "pairs": [{"i": i + 1, "j": j + 1, "score": score} for i, j, score in contacts.pairs],
        },
        "structure": {
            "coordinates": [
                {"residue": idx + 1, "x": x, "y": y, "z": z}
                for idx, (x, y, z) in enumerate(structure.coordinates)
            ],
            "confidence": structure.confidence,
            "mean_confidence": structure.mean_confidence,
            "radius_of_gyration": structure.radius_of_gyration,
            "end_to_end_distance": structure.end_to_end_distance,
        },
        "residue_table": _residue_table(sequence, secondary.assignment, structure.confidence),
    }

    if include_profile:
        result["profiles"] = {
            "hydropathy": hydropathy_profile(sequence),
            "hydrophobic_moment": hydrophobic_moment(sequence),
        }

    return result


def _residue_table(sequence: str, assignment: str, confidence: list[float]) -> list[dict]:
    """A compact per-residue view for the UI table."""
    rows: list[dict] = []
    for i, residue in enumerate(sequence):
        rows.append(
            {
                "index": i + 1,
                "residue": residue,
                "residue_name": THREE_LETTER.get(residue, residue),
                "ss": assignment[i] if i < len(assignment) else "C",
                "confidence": confidence[i] if i < len(confidence) else 0.0,
            }
        )
    return rows
