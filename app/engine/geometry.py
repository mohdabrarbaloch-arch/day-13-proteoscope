"""Contact prediction and 3D backbone generation.

Two jobs live here:

1. **Contact map.** Which residues are close in space? We estimate this from
   sequence separation, secondary structure, and a hydrophobic term, then apply
   a physical constraint: two residues cannot be in contact if the chain between
   them is too short to span the distance. That constraint is what stops the map
   from being a meaningless diagonal blob.

2. **3D trace.** Build a C-alpha backbone that *satisfies* the contact map. We
   start from ideal secondary-structure geometry (helices coil, sheets zig-zag,
   coils wander), then run a deterministic relaxation that pulls contacting
   residues together and pushes clashing ones apart.

The relaxation is position-based dynamics — the same family of solver used in
cloth and soft-body simulation. It is unconditionally stable, unlike a naive
force integration, which is what the first version of this file got wrong: the
forces compounded and the coordinates exploded to 1e27. PBD moves points
directly toward satisfying each constraint by a fraction, so it cannot diverge.
There is no randomness anywhere, so the same sequence always yields the same
coordinates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.engine.secondary import COIL, HELIX, SHEET, SecondaryStructure

# Ideal C-alpha geometry.
CA_CA_HELIX = 1.50  # angstrom, rise per residue along an alpha helix
CA_CA_EXTENDED = 3.40  # angstrom, rise per residue in a beta strand
CA_CA_COIL = 3.80  # angstrom, average for a random coil
HELIX_RADIUS = 2.30  # angstrom
HELIX_TWIST = 100.0  # degrees per residue (360 / 3.6)
SHEET_PLEAT = 1.00  # angstrom, alternating out-of-plane offset

# Contact-map thresholds.
CONTACT_CUTOFF = 8.0  # angstrom, the usual definition of a residue-residue contact
MIN_SEQUENCE_SEPARATION = 4  # below this, "contact" is just chain adjacency
MAX_CONTACTS_PER_RESIDUE = 12  # cap so a hydrophobic blob does not dominate

# Relaxation schedule.
RELAX_STEPS = 160
RELAX_STIFFNESS = 0.55
CONTACT_TARGET = 6.5  # angstrom, the distance a predicted contact is pulled toward
CLASH_DISTANCE = 3.2  # angstrom, below this two C-alphas repel
CONTACT_PULL = 0.55  # fraction of the contact correction applied per step
CHAIN_PULL = 0.85  # chain connectivity is the stiffest constraint
COMPACTION_PULL = 0.06  # weak pull toward the centroid; keeps long chains from drifting
# Target radius of gyration, from the standard polymer scaling Rg ~ 2.2 * N^0.38.
RG_PREFACTOR = 2.2
RG_EXPONENT = 0.38


@dataclass(frozen=True)
class ContactMap:
    """A sparse contact map plus the statistics that describe it."""

    pairs: list[tuple[int, int, float]]
    density: float
    max_separation: int
    per_residue: list[int]

    @property
    def count(self) -> int:
        return len(self.pairs)


@dataclass(frozen=True)
class Structure:
    """A 3D C-alpha trace with per-residue confidence."""

    coordinates: list[tuple[float, float, float]]
    confidence: list[float]
    radius_of_gyration: float
    end_to_end_distance: float
    mean_confidence: float


def _hydrophobic_bonus(a: str, b: str) -> float:
    """Extra contact propensity for two greasy residues."""
    from app.engine.sequence import KYTE_DOOLITTLE

    return max(0.0, (KYTE_DOOLITTLE[a] + KYTE_DOOLITTLE[b]) / 2.0) * 0.12


def _secondary_bonus(state_a: str, state_b: str) -> float:
    """Residues in the same regular element are more likely to touch."""
    if state_a == state_b == HELIX:
        return 0.18
    if state_a == state_b == SHEET:
        return 0.22
    if state_a == state_b == COIL:
        return -0.05
    return 0.0


def _max_span(separation: int) -> float:
    """Longest a chain of `separation` residues can physically reach.

    A fully extended chain gains about 3.4 A per residue, so this is the hard
    ceiling on how far apart two residues can be. Anything beyond it is not a
    contact, no matter what the propensity tables say.
    """
    return CA_CA_EXTENDED * separation


def predict_contacts(
    sequence: str,
    secondary: SecondaryStructure,
    *,
    cutoff: float = CONTACT_CUTOFF,
    min_separation: int = MIN_SEQUENCE_SEPARATION,
) -> ContactMap:
    """Predict which residue pairs are in spatial contact.

    For every pair at least `min_separation` apart we compute a propensity
    score, convert it to an estimated distance, and keep the pair if that
    distance is under `cutoff` *and* physically reachable. Each residue is then
    capped at `MAX_CONTACTS_PER_RESIDUE` of its strongest partners.
    """
    n = len(sequence)
    if n < min_separation + 1:
        return ContactMap(pairs=[], density=0.0, max_separation=0, per_residue=[0] * n)

    states = secondary.assignment
    candidates: list[tuple[int, int, float]] = []

    for i in range(n):
        for j in range(i + min_separation, n):
            separation = j - i
            if _max_span(separation) < cutoff:
                # The chain simply cannot fold back on itself this tightly.
                continue

            score = 0.5
            score += _hydrophobic_bonus(sequence[i], sequence[j])
            score += _secondary_bonus(states[i], states[j])
            # Contacts are more likely between residues that are close in
            # sequence than between distant ones, all else equal.
            score -= 0.0009 * separation
            score = max(0.0, min(1.0, score))

            # Map propensity to an estimated distance. High score -> short.
            estimated = cutoff + (1.0 - score) * 6.0
            if estimated <= cutoff:
                candidates.append((i, j, round(score, 4)))

    # Cap per-residue degree, keeping the strongest contacts.
    per_residue = [0] * n
    kept: list[tuple[int, int, float]] = []
    for i, j, score in sorted(candidates, key=lambda t: -t[2]):
        if per_residue[i] >= MAX_CONTACTS_PER_RESIDUE or per_residue[j] >= MAX_CONTACTS_PER_RESIDUE:
            continue
        per_residue[i] += 1
        per_residue[j] += 1
        kept.append((i, j, score))

    kept.sort(key=lambda t: (t[0], t[1]))
    possible = n * (n - 1) / 2
    density = round(len(kept) / possible, 5) if possible else 0.0
    max_sep = max((j - i for i, j, _ in kept), default=0)

    return ContactMap(pairs=kept, density=density, max_separation=max_sep, per_residue=per_residue)


def _initial_trace(sequence: str, secondary: SecondaryStructure) -> list[list[float]]:
    """Lay out an idealised backbone, one residue at a time.

    Helices coil around an axis, sheets zig-zag in a plane, coils drift. This is
    a starting guess for the relaxation, not a claim about the real fold.
    """
    n = len(sequence)
    states = secondary.assignment
    coords: list[list[float]] = []
    x, y, z = 0.0, 0.0, 0.0
    heading = 0.0

    for i in range(n):
        state = states[i] if i < len(states) else COIL
        if state == HELIX:
            angle = math.radians(HELIX_TWIST * i)
            x = HELIX_RADIUS * math.cos(angle)
            y = HELIX_RADIUS * math.sin(angle)
            z = CA_CA_HELIX * i
        elif state == SHEET:
            x = CA_CA_EXTENDED * i
            y = SHEET_PLEAT * (1 if i % 2 == 0 else -1)
            z = 0.0
        else:
            # Random coil: a slow, deterministic wander.
            heading += 0.7
            x += CA_CA_COIL * math.cos(heading)
            y += CA_CA_COIL * math.sin(heading)
            z += 0.6 * math.sin(heading * 0.5)
        coords.append([x, y, z])

    return coords


def _distance(a: list[float], b: list[float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _chain_target(states: str, i: int) -> float:
    """Preferred C-alpha distance between residues i and i+1."""
    state = states[i] if i < len(states) else COIL
    if state == HELIX:
        return CA_CA_HELIX
    if state == SHEET:
        return CA_CA_EXTENDED
    return CA_CA_COIL


def _relax(
    coords: list[list[float]],
    contacts: ContactMap,
    states: str,
    *,
    steps: int = RELAX_STEPS,
    stiffness: float = RELAX_STIFFNESS,
) -> list[list[float]]:
    """Position-based dynamics: satisfy each constraint by a fraction per step.

    Three constraint families, applied in order of stiffness:

    * chain connectivity (stiffest) — consecutive residues at a plausible gap
    * predicted contacts — pull partners toward CONTACT_TARGET
    * clashes — push any pair closer than CLASH_DISTANCE apart

    Because each step moves points *toward* satisfaction by a fraction < 1, the
    system cannot diverge. That is the whole reason this replaced the earlier
    force-integration version.
    """
    n = len(coords)
    if n < 2:
        return coords

    contact_pairs = [(i, j) for i, j, _ in contacts.pairs]
    target_rg = RG_PREFACTOR * (n**RG_EXPONENT)

    for _ in range(steps):
        # --- chain connectivity --------------------------------------------
        for i in range(n - 1):
            d = _distance(coords[i], coords[i + 1])
            if d < 1e-6:
                coords[i + 1][0] += 0.5
                continue
            target = _chain_target(states, i)
            corr = ((d - target) / d) * 0.5 * stiffness * CHAIN_PULL
            for axis in range(3):
                delta = (coords[i][axis] - coords[i + 1][axis]) * corr
                coords[i][axis] -= delta
                coords[i + 1][axis] += delta

        # --- predicted contacts --------------------------------------------
        for i, j in contact_pairs:
            d = _distance(coords[i], coords[j])
            if d < 1e-6 or d <= CONTACT_TARGET:
                continue
            corr = ((d - CONTACT_TARGET) / d) * 0.5 * stiffness * CONTACT_PULL
            for axis in range(3):
                delta = (coords[i][axis] - coords[j][axis]) * corr
                coords[i][axis] -= delta
                coords[j][axis] += delta

        # --- clashes --------------------------------------------------------
        for i in range(n):
            for j in range(i + 1, n):
                d = _distance(coords[i], coords[j])
                if d >= CLASH_DISTANCE or d < 1e-6:
                    continue
                corr = ((CLASH_DISTANCE - d) / d) * 0.5 * stiffness
                for axis in range(3):
                    delta = (coords[i][axis] - coords[j][axis]) * corr
                    coords[i][axis] += delta
                    coords[j][axis] -= delta

        # --- compaction -----------------------------------------------------
        # A real globular protein is compact: Rg scales as roughly N^0.38. The
        # chain and contact constraints alone let a long coil drift outward, so
        # we add a weak pull toward the centroid whenever the structure is
        # looser than that scaling predicts. It is deliberately gentle — it
        # shapes the fold, it does not dictate it.
        _compact(coords, target_rg)

    _center(coords)
    return coords


def _compact(coords: list[list[float]], target_rg: float) -> None:
    """Pull every point a little toward the centroid if the chain is too loose."""
    n = len(coords)
    if n == 0:
        return
    cx = sum(c[0] for c in coords) / n
    cy = sum(c[1] for c in coords) / n
    cz = sum(c[2] for c in coords) / n

    total = sum((c[0] - cx) ** 2 + (c[1] - cy) ** 2 + (c[2] - cz) ** 2 for c in coords)
    rg = math.sqrt(total / n)
    if rg <= target_rg or rg < 1e-6:
        return

    # Scale the excess back by a small fraction each step.
    factor = 1.0 - COMPACTION_PULL * (1.0 - target_rg / rg)
    for c in coords:
        c[0] = cx + (c[0] - cx) * factor
        c[1] = cy + (c[1] - cy) * factor
        c[2] = cz + (c[2] - cz) * factor


def _center(coords: list[list[float]]) -> None:
    """Translate the structure so its centroid sits at the origin."""
    n = len(coords)
    if n == 0:
        return
    cx = sum(c[0] for c in coords) / n
    cy = sum(c[1] for c in coords) / n
    cz = sum(c[2] for c in coords) / n
    for c in coords:
        c[0] -= cx
        c[1] -= cy
        c[2] -= cz


def _radius_of_gyration(coords: list[list[float]]) -> float:
    n = len(coords)
    if n == 0:
        return 0.0
    cx = sum(c[0] for c in coords) / n
    cy = sum(c[1] for c in coords) / n
    cz = sum(c[2] for c in coords) / n
    total = sum((c[0] - cx) ** 2 + (c[1] - cy) ** 2 + (c[2] - cz) ** 2 for c in coords)
    return round(math.sqrt(total / n), 3)


def _end_to_end(coords: list[list[float]]) -> float:
    if len(coords) < 2:
        return 0.0
    return round(_distance(coords[0], coords[-1]), 3)


def _confidence(
    coords: list[list[float]],
    contacts: ContactMap,
    secondary: SecondaryStructure,
) -> list[float]:
    """Per-residue confidence in [0, 1].

    Three things raise confidence: sitting in a regular secondary element,
    having several satisfied contacts, and not being in a clash. This is a
    heuristic, and it is labelled as one — it is not a calibrated pLDDT.
    """
    n = len(coords)
    states = secondary.assignment

    # Pre-bucket contacts by residue so this stays linear, not quadratic.
    partners: list[list[int]] = [[] for _ in range(n)]
    for a, b, _ in contacts.pairs:
        partners[a].append(b)
        partners[b].append(a)

    confidence: list[float] = []
    for i in range(n):
        base = 0.35
        state = states[i] if i < len(states) else COIL
        if state == HELIX:
            base += 0.30
        elif state == SHEET:
            base += 0.28
        elif state == "T":
            base += 0.05

        mine = partners[i]
        if mine:
            satisfied = sum(1 for other in mine if _distance(coords[i], coords[other]) <= CONTACT_CUTOFF)
            base += 0.30 * (satisfied / len(mine))

        clashes = sum(1 for j in range(n) if j != i and _distance(coords[i], coords[j]) < CLASH_DISTANCE)
        base -= min(0.25, clashes * 0.05)

        confidence.append(round(max(0.0, min(1.0, base)), 4))

    return confidence


def build_structure(
    sequence: str,
    secondary: SecondaryStructure,
    contacts: ContactMap,
) -> Structure:
    """Run the full geometry pipeline and return a C-alpha trace."""
    coords = _initial_trace(sequence, secondary)
    coords = _relax(coords, contacts, secondary.assignment)
    confidence = _confidence(coords, contacts, secondary)

    rounded = [(round(c[0], 3), round(c[1], 3), round(c[2], 3)) for c in coords]
    mean_conf = round(sum(confidence) / len(confidence), 4) if confidence else 0.0

    return Structure(
        coordinates=rounded,
        confidence=confidence,
        radius_of_gyration=_radius_of_gyration(coords),
        end_to_end_distance=_end_to_end(coords),
        mean_confidence=mean_conf,
    )
