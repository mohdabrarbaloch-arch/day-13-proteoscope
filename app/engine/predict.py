"""The top-level prediction pipeline.

`predict_structure` is the one function the API calls. It wires the stages
together and returns a single, self-contained result dict.
"""

from __future__ import annotations

from app.engine.geometry import generate_backbone, predict_contacts
from app.engine.secondary import predict_secondary
from app.engine.sequence import ParsedSequence, parse_sequence, properties

ENGINE_NAME = "Proteoscope"
ENGINE_VERSION = "1.0.0"


def predict_structure(raw_sequence: str, include_profile: bool = True) -> dict:
    """Run the full pipeline on a raw sequence.

    Returns a dict with keys: sequence, properties, secondary_structure,
    contacts, structure. Raises SequenceError on invalid input.
    """
    parsed: ParsedSequence = parse_sequence(raw_sequence)
    seq = parsed.cleaned

    props = properties(seq) if include_profile else None
    secondary = predict_secondary(seq)
    contacts = predict_contacts(seq)
    backbone = generate_backbone(seq, contacts)

    return {
        "sequence": {
            "cleaned": seq,
            "header": parsed.header,
            "length": parsed.length,
        },
        "properties": props,
        "secondary_structure": {
            "assignments": secondary["assignments"],
            "helix_fraction": secondary["helix_fraction"],
            "sheet_fraction": secondary["sheet_fraction"],
            "turn_fraction": secondary["turn_fraction"],
            "coil_fraction": secondary["coil_fraction"],
        },
        "contacts": {
            "count": len(contacts),
            "pairs": [[c.i, c.j, c.confidence] for c in contacts],
        },
        "structure": {
            "coordinates": backbone["coordinates"],
            "confidence": backbone["confidence"],
            "mean_confidence": backbone["mean_confidence"],
            "radius_of_gyration": backbone["radius_of_gyration"],
        },
    }