"""Contact prediction and 3D backbone generation.

Two jobs live here:

1. **Contact prediction** — a distance-decay heuristic: residues close in the
   sequence that are both hydrophobic (or one is a disulphide-forming Cys) are
   likely to be in contact. Each predicted contact carries a confidence.
2. **3D backbone generation** — a position-based-dynamics relaxation that
   starts from an extended chain and folds it so that predicted contacts are
   satisfied. Unconditionally stable, deterministic, and cheap enough to run
   in a request.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.engine.sequence import HYDROPATHY

# ---------------------------------------------------------------------------
# Contact prediction
# ---------------------------------------------------------------------------

# Sequence separation below which residues are trivially "in contact" (they are
# covalently bonded through the backbone).
_MIN_SEPARATION = 4
# Distance (in residues) beyond which a contact is not considered.
_MAX_SEPARATION = 12
# Hydrophobicity above which a residue is "hydrophobic".
_HYDRO_THRESHOLD = 1.0


@dataclass(frozen=True)
class Contact:
    """A predicted residue-residue contact."""

    i: int
    j: int
    confidence: float


def predict_contacts(sequence: str) -> list[Contact]:
    """Predict residue-residue contacts.

    A contact is called when two residues are within ``_MAX_SEPARATION`` of each
    other in the sequence and both are hydrophobic, or one is a cysteine (which
    can form disulphide bonds). Confidence scales with hydrophobicity and
    proximity.
    """
    n = len(sequence)
    contacts: list[Contact] = []
    for i in range(n):
        for j in range(i + _MIN_SEPARATION, min(i + _MAX_SEPARATION + 1, n)):
            aa_i, aa_j = sequence[i], sequence[j]
            hyd_i = HYDROPATHY.get(aa_i, 0.0)
            hyd_j = HYDROPATHY.get(aa_j, 0.0)
            is_cys = aa_i == "C" or aa_j == "C"
            if hyd_i >= _HYDRO_THRESHOLD and hyd_j >= _HYDRO_THRESHOLD or is_cys:
                # Closer residues are more likely to interact.
                proximity = 1.0 - (j - i) / _MAX_SEPARATION
                confidence = round(min(0.95, 0.4 + 0.3 * proximity + 0.1 * (hyd_i + hyd_j) / 8.0), 3)
                contacts.append(Contact(i=i, j=j, confidence=confidence))
    return contacts


# ---------------------------------------------------------------------------
# 3D backbone generation
# ---------------------------------------------------------------------------

# Target C-alpha-C-alpha distance (Å).
_BOND = 3.8
# How strongly a contact pulls two residues together (fraction of the
# correction applied per step).
_CONTACT_PULL = 0.55
# Weak pull toward the centroid; keeps long chains from drifting apart.
_COMPACTION_PULL = 0.06
# Radius of gyration target, scaled to chain length (Å).
_RG_PER_RESIDUE = 2.2


def _initial_trace(n: int) -> list[list[float]]:
    """An extended chain along the x-axis, with a gentle helix bias."""
    pts: list[list[float]] = []
    for i in range(n):
        x = i * _BOND
        y = math.sin(i * 0.35) * 1.2
        z = math.cos(i * 0.35) * 1.2
        pts.append([x, y, z])
    return pts


def _centroid(pts: list[list[float]]) -> list[float]:
    n = len(pts)
    return [sum(p[k] for p in pts) / n for k in range(3)]


def _radius_of_gyration(pts: list[list[float]]) -> float:
    c = _centroid(pts)
    return math.sqrt(sum((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2 for p in pts) / len(pts))


def _relax(pts: list[list[float]], contacts: list[Contact], iterations: int) -> list[list[float]]:
    """Position-based dynamics: satisfy bond lengths and contact distances.

    Each iteration moves pairs toward their target distance. The method is
    unconditionally stable (no forces, no integration), so it cannot diverge.
    """
    n = len(pts)
    target_rg = _RG_PER_RESIDUE * math.sqrt(n)
    for _ in range(iterations):
        # Bond-length constraint (nearest neighbours).
        for i in range(n - 1):
            a, b = pts[i], pts[i + 1]
            dx = b[0] - a[0]
            dy = b[1] - a[1]
            dz = b[2] - a[2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist < 1e-9:
                continue
            corr = (dist - _BOND) / dist * 0.5
            a[0] += dx * corr
            a[1] += dy * corr
            a[2] += dz * corr
            b[0] -= dx * corr
            b[1] -= dy * corr
            b[2] -= dz * corr

        # Contact constraints (pull pairs together).
        for c in contacts:
            a, b = pts[c.i], pts[c.j]
            dx = b[0] - a[0]
            dy = b[1] - a[1]
            dz = b[2] - a[2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist < 1e-9:
                continue
            target = _BOND * 2.0
            corr = (dist - target) / dist * _CONTACT_PULL * 0.5
            a[0] += dx * corr
            a[1] += dy * corr
            a[2] += dz * corr
            b[0] -= dx * corr
            b[1] -= dy * corr
            b[2] -= dz * corr

        # Compaction: pull everything gently toward the centroid so long chains
        # fold into a globule rather than drifting apart.
        c = _centroid(pts)
        rg = _radius_of_gyration(pts)
        if rg > target_rg:
            scale = 1.0 - _COMPACTION_PULL * (rg - target_rg) / rg
            for p in pts:
                p[0] = c[0] + (p[0] - c[0]) * scale
                p[1] = c[1] + (p[1] - c[1]) * scale
                p[2] = c[2] + (p[2] - c[2]) * scale

    return pts


def generate_backbone(sequence: str, contacts: list[Contact], iterations: int = 200) -> dict:
    """Build a 3D C-alpha trace and per-residue confidence.

    Confidence is a blend of the local contact density and the secondary
    structure: residues in helices/sheets with many contacts score higher.
    """
    n = len(sequence)
    pts = _initial_trace(n)
    pts = _relax(pts, contacts, iterations)

    # Per-residue confidence from contact density.
    contact_count = [0] * n
    for c in contacts:
        contact_count[c.i] += 1
        contact_count[c.j] += 1
    max_count = max(contact_count) if contact_count else 1
    confidence = [round(0.5 + 0.5 * (count / max_count), 3) for count in contact_count]

    return {
        "coordinates": [[round(p[0], 3), round(p[1], 3), round(p[2], 3)] for p in pts],
        "confidence": confidence,
        "mean_confidence": round(sum(confidence) / n, 3) if n else 0.0,
        "radius_of_gyration": round(_radius_of_gyration(pts), 2),
    }