"""Secondary-structure prediction by the Chou-Fasman method.

Chou & Fasman (1974, 1978) assign each residue a propensity to sit in a helix,
a sheet, or a turn. The algorithm nucleates runs of high-propensity residues and
extends them. It is old, it is not accurate by modern standards (roughly 60-65%
per-residue agreement on real proteins), and it is *fully inspectable* — which is
exactly why it is here. Every assignment can be traced back to a table value.

The propensity tables below are the published ones. Where a residue has no
published turn propensity it is given 1.00 (neutral) rather than a guess.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.engine.sequence import KYTE_DOOLITTLE

# P(a) helix, P(b) sheet, P(t) turn. Chou-Fasman, as tabulated in
# Creighton, "Proteins" (2nd ed.), Table 6.2.
HELIX_PROPENSITY: dict[str, float] = {
    "A": 1.42,
    "R": 0.98,
    "N": 0.67,
    "D": 1.01,
    "C": 0.70,
    "Q": 1.11,
    "E": 1.51,
    "G": 0.57,
    "H": 1.00,
    "I": 1.08,
    "L": 1.21,
    "K": 1.16,
    "M": 1.45,
    "F": 1.13,
    "P": 0.57,
    "S": 0.77,
    "T": 0.83,
    "W": 1.08,
    "Y": 0.69,
    "V": 1.06,
}

SHEET_PROPENSITY: dict[str, float] = {
    "A": 0.83,
    "R": 0.93,
    "N": 0.89,
    "D": 0.54,
    "C": 1.19,
    "Q": 1.10,
    "E": 0.37,
    "G": 0.75,
    "H": 0.87,
    "I": 1.60,
    "L": 1.30,
    "K": 0.74,
    "M": 1.05,
    "F": 1.38,
    "P": 0.55,
    "S": 0.75,
    "T": 1.19,
    "W": 1.37,
    "Y": 1.47,
    "V": 1.70,
}

TURN_PROPENSITY: dict[str, float] = {
    "A": 0.66,
    "R": 0.95,
    "N": 1.56,
    "D": 1.46,
    "C": 1.19,
    "Q": 0.98,
    "E": 0.74,
    "G": 1.56,
    "H": 0.95,
    "I": 0.47,
    "L": 0.59,
    "K": 1.01,
    "M": 0.60,
    "F": 0.60,
    "P": 1.52,
    "S": 1.43,
    "T": 0.96,
    "W": 0.96,
    "Y": 1.14,
    "V": 0.50,
}

# Residues that break a helix outright.
HELIX_BREAKERS: frozenset[str] = frozenset("PG")
# Residues that break a sheet.
SHEET_BREAKERS: frozenset[str] = frozenset("PDGKRS")

HELIX_THRESHOLD = 1.03
SHEET_THRESHOLD = 1.05
TURN_THRESHOLD = 1.00

HELIX_MIN_RUN = 4
SHEET_MIN_RUN = 3
TURN_WINDOW = 4

# One-letter codes for the three states plus coil.
HELIX = "H"
SHEET = "E"
TURN = "T"
COIL = "C"

_TWO_PI = 2.0 * math.pi


@dataclass(frozen=True)
class SecondaryStructure:
    """Per-residue secondary-structure assignment."""

    assignment: str
    helix_fraction: float
    sheet_fraction: float
    turn_fraction: float
    coil_fraction: float
    segments: list[dict]

    @property
    def length(self) -> int:
        return len(self.assignment)


def _spans_from_flags(flags: list[bool]) -> list[tuple[int, int]]:
    """Maximal [start, end) spans where `flags` is True."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for i, flag in enumerate(flags):
        if flag:
            if start is None:
                start = i
        elif start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(flags)))
    return spans


def _segments(assignment: str) -> list[dict]:
    """Collapse a per-residue string into contiguous labelled segments."""
    if not assignment:
        return []
    labels = {HELIX: "helix", SHEET: "sheet", TURN: "turn", COIL: "coil"}
    segments: list[dict] = []
    start = 0
    current = assignment[0]
    for i in range(1, len(assignment)):
        if assignment[i] != current:
            segments.append(
                {
                    "type": labels[current],
                    "start": start + 1,  # 1-based, inclusive
                    "end": i,  # 1-based, inclusive
                    "length": i - start,
                }
            )
            start = i
            current = assignment[i]
    segments.append(
        {
            "type": labels[current],
            "start": start + 1,
            "end": len(assignment),
            "length": len(assignment) - start,
        }
    )
    return segments


def predict_secondary_structure(sequence: str) -> SecondaryStructure:
    """Assign H / E / T / C to every residue.

    Order of operations matters and follows Chou-Fasman:

    1. Nucleate helices: a run of >= 4 residues with P(a) >= 1.03 and no
       proline or glycine inside.
    2. Nucleate sheets: a run of >= 3 residues with P(b) >= 1.05 and no
       sheet-breaking residue inside.
    3. Mark turns: any 4-residue window whose mean P(t) >= 1.00.
    4. Resolve overlaps: helix beats sheet beats turn, because that is the
       priority Chou-Fasman gives them.
    5. Everything left over is coil.
    """
    n = len(sequence)
    if n == 0:
        return SecondaryStructure("", 0.0, 0.0, 0.0, 0.0, [])

    helix_scores = [HELIX_PROPENSITY[c] for c in sequence]
    sheet_scores = [SHEET_PROPENSITY[c] for c in sequence]
    turn_scores = [TURN_PROPENSITY[c] for c in sequence]

    state = [COIL] * n

    # --- 1. Helices ---------------------------------------------------------
    helix_ok = [helix_scores[i] >= HELIX_THRESHOLD and sequence[i] not in HELIX_BREAKERS for i in range(n)]
    for start, end in _spans_from_flags(helix_ok):
        if end - start >= HELIX_MIN_RUN:
            for i in range(start, end):
                state[i] = HELIX

    # --- 2. Sheets ----------------------------------------------------------
    sheet_ok = [sheet_scores[i] >= SHEET_THRESHOLD and sequence[i] not in SHEET_BREAKERS for i in range(n)]
    for start, end in _spans_from_flags(sheet_ok):
        if end - start >= SHEET_MIN_RUN:
            for i in range(start, end):
                if state[i] == COIL:
                    state[i] = SHEET

    # --- 3. Turns -----------------------------------------------------------
    for i in range(n):
        if state[i] != COIL:
            continue
        if i + TURN_WINDOW > n:
            break
        window_mean = sum(turn_scores[i : i + TURN_WINDOW]) / TURN_WINDOW
        if window_mean >= TURN_THRESHOLD:
            for j in range(i, i + TURN_WINDOW):
                if state[j] == COIL:
                    state[j] = TURN

    assignment = "".join(state)
    counts = {s: assignment.count(s) for s in (HELIX, SHEET, TURN, COIL)}
    segments = _segments(assignment)

    return SecondaryStructure(
        assignment=assignment,
        helix_fraction=round(counts[HELIX] / n, 4),
        sheet_fraction=round(counts[SHEET] / n, 4),
        turn_fraction=round(counts[TURN] / n, 4),
        coil_fraction=round(counts[COIL] / n, 4),
        segments=segments,
    )


def hydrophobic_moment(sequence: str, window: int = 18) -> list[float]:
    """Hydrophobic moment per residue, assuming an ideal alpha helix.

    A real alpha helix has 3.6 residues per turn, so residues i and i+3/i+4 face
    the same side. A high value means one face is greasy and the other is not —
    the signature of a membrane-spanning or surface-binding helix.
    """
    n = len(sequence)
    if n == 0:
        return []
    period = 3.6
    half = window // 2
    moments: list[float] = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        real = 0.0
        imag = 0.0
        for j in range(lo, hi):
            angle = _TWO_PI * (j - i) / period
            h = KYTE_DOOLITTLE[sequence[j]]
            real += h * math.cos(angle)
            imag += h * math.sin(angle)
        moments.append(round(math.hypot(real, imag) / (hi - lo), 3))
    return moments
