"""Secondary-structure prediction by the Chou-Fasman method.

Chou & Fasman (1974) assign each residue a propensity for alpha-helix (P_a),
beta-sheet (P_b) and beta-turn (P_t). A stretch of residues with high P_a forms
a helix; high P_b forms a sheet; otherwise the region is coil. This is a
faithful, deterministic implementation of the classic rules.
"""

from __future__ import annotations

# Chou-Fasman conformational parameters (P_a, P_b, P_t).
_CF: dict[str, tuple[float, float, float]] = {
    "A": (1.42, 0.83, 0.66), "R": (0.98, 0.93, 0.95), "N": (0.67, 0.89, 1.56),
    "D": (1.01, 0.54, 1.46), "C": (0.70, 1.19, 1.19), "E": (1.51, 0.37, 0.74),
    "Q": (1.11, 1.10, 0.98), "G": (0.57, 0.75, 1.56), "H": (1.00, 0.87, 0.95),
    "I": (1.08, 1.60, 0.47), "L": (1.21, 1.30, 0.59), "K": (1.14, 0.74, 1.01),
    "M": (1.45, 1.05, 0.60), "F": (1.13, 1.38, 0.60), "P": (0.57, 0.55, 1.52),
    "S": (0.77, 0.75, 1.43), "T": (0.83, 1.19, 0.96), "W": (1.08, 1.37, 0.96),
    "Y": (0.69, 1.47, 1.14), "V": (1.06, 1.70, 0.50),
}

# Ambiguous residues default to coil-neutral values.
_DEFAULT = (1.0, 1.0, 1.0)

# A helix/sheet nucleus is a run of 4+ residues where the average propensity
# exceeds this threshold.
_NUCLEUS = 1.03
# A helix/sheet is extended while the average stays above this.
_EXTEND = 1.00


def _pa(aa: str) -> float:
    return _CF.get(aa, _DEFAULT)[0]


def _pb(aa: str) -> float:
    return _CF.get(aa, _DEFAULT)[1]


def _pt(aa: str) -> float:
    return _CF.get(aa, _DEFAULT)[2]


def predict_secondary(sequence: str) -> dict:
    """Return per-residue assignments and overall fractions.

    The result dict has:
      - ``assignments``: list of 'H' | 'E' | 'T' | 'C' per residue
      - ``helix_fraction``, ``sheet_fraction``, ``turn_fraction``, ``coil_fraction``
    """
    n = len(sequence)
    if n == 0:
        return {
            "assignments": [],
            "helix_fraction": 0.0,
            "sheet_fraction": 0.0,
            "turn_fraction": 0.0,
            "coil_fraction": 1.0,
        }

    # Pass 1: find helix and sheet nuclei, then extend them.
    state = ["C"] * n

    # Helices.
    i = 0
    while i < n - 3:
        window = sequence[i : i + 4]
        if sum(_pa(a) for a in window) / 4.0 >= _NUCLEUS:
            j = i + 4
            while j < n and sum(_pa(a) for a in sequence[i : j + 1]) / (j - i + 1) >= _EXTEND:
                j += 1
            for k in range(i, j):
                state[k] = "H"
            i = j
        else:
            i += 1

    # Sheets (only where not already helix).
    i = 0
    while i < n - 3:
        if state[i] == "H":
            i += 1
            continue
        window = sequence[i : i + 4]
        if sum(_pb(a) for a in window) / 4.0 >= _NUCLEUS:
            j = i + 4
            while j < n and state[j] != "H" and sum(_pb(a) for a in sequence[i : j + 1]) / (j - i + 1) >= _EXTEND:
                j += 1
            for k in range(i, j):
                state[k] = "E"
            i = j
        else:
            i += 1

    # Pass 2: turns in the remaining coil regions.
    for i in range(n - 3):
        if state[i] != "C":
            continue
        window = sequence[i : i + 4]
        # A turn is favoured when P_t is high and P_a/P_b are low.
        pt_avg = sum(_pt(a) for a in window) / 4.0
        pa_avg = sum(_pa(a) for a in window) / 4.0
        pb_avg = sum(_pb(a) for a in window) / 4.0
        if pt_avg > 1.0 and pt_avg > pa_avg and pt_avg > pb_avg:
            for k in range(i, i + 4):
                if state[k] == "C":
                    state[k] = "T"

    counts = {"H": 0, "E": 0, "T": 0, "C": 0}
    for s in state:
        counts[s] += 1

    return {
        "assignments": state,
        "helix_fraction": round(counts["H"] / n, 4),
        "sheet_fraction": round(counts["E"] / n, 4),
        "turn_fraction": round(counts["T"] / n, 4),
        "coil_fraction": round(counts["C"] / n, 4),
    }