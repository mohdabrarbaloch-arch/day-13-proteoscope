"""Sequence parsing, validation, and physicochemical properties.

Every constant here is a published value: standard residue masses, Kyte-Doolittle
hydrophobicity, and the pKa table used for the isoelectric point. Nothing is
fitted or learned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings

# ---------------------------------------------------------------------------
# Residue data
# ---------------------------------------------------------------------------

# Monoisotopic residue masses (Da) — the mass of the amino acid minus water.
RESIDUE_MASS: dict[str, float] = {
    "A": 71.03711, "R": 156.10111, "N": 114.04293, "D": 115.02694, "C": 103.00919,
    "E": 129.04259, "Q": 128.05858, "G": 57.02146, "H": 137.05891, "I": 113.08406,
    "L": 113.08406, "K": 128.09496, "M": 131.04049, "F": 147.06841, "P": 97.05276,
    "S": 87.03203, "T": 101.04768, "W": 186.07931, "Y": 163.06333, "V": 99.06841,
}

# Kyte-Doolittle hydropathy index (Kyte & Doolittle 1982).
HYDROPATHY: dict[str, float] = {
    "I": 4.5, "V": 4.2, "L": 3.8, "F": 2.8, "C": 2.5, "M": 1.9, "A": 1.8,
    "G": -0.4, "T": -0.7, "S": -0.8, "W": -0.9, "Y": -1.3, "P": -1.6, "H": -3.2,
    "D": -3.5, "E": -3.5, "Q": -3.5, "N": -3.5, "K": -3.9, "R": -4.5,
}

# pKa values used for the isoelectric point (Bjellqvist-style, simplified).
# (side-chain pKa, N-terminus pKa, C-terminus pKa)
_PKA_SIDECHAIN = {"D": 3.9, "E": 4.3, "C": 8.3, "Y": 10.1, "H": 6.0, "K": 10.5, "R": 12.4}
_PKA_NTERM = 8.0
_PKA_CTERM = 3.1

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_FASTA_HEADER = re.compile(r"^>(.*)$", re.MULTILINE)
_VALID = set(RESIDUE_MASS) | {"B", "Z", "X"}


class SequenceError(ValueError):
    """Raised when a sequence cannot be analysed."""


@dataclass(frozen=True)
class ParsedSequence:
    """A validated, cleaned sequence plus its FASTA header (if any)."""

    cleaned: str
    header: str
    length: int


def parse_sequence(raw: str) -> ParsedSequence:
    """Validate and normalise a raw sequence (plain text or FASTA).

    Raises SequenceError on any problem. Whitespace and digits are stripped;
    a FASTA header line is captured but not treated as sequence.
    """
    if not raw or not raw.strip():
        raise SequenceError("Sequence is empty.")

    text = raw.strip()
    header = ""
    if text.startswith(">"):
        lines = text.splitlines()
        header = lines[0][1:].strip()
        body = "".join(lines[1:])
    else:
        body = "".join(text.split())

    # Remove any digits that slipped in (some FASTA files number lines).
    body = re.sub(r"[0-9]", "", body)
    body = body.upper()

    if len(body) < settings.min_sequence_length:
        raise SequenceError(
            f"Sequence is too short: {len(body)} residues. "
            f"Minimum is {settings.min_sequence_length}."
        )
    if len(body) > settings.max_sequence_length:
        raise SequenceError(
            f"Sequence is too long: {len(body)} residues. "
            f"Maximum is {settings.max_sequence_length}."
        )

    invalid = sorted({c for c in body if c not in _VALID})
    if invalid:
        raise SequenceError(f"Sequence contains invalid amino-acid letters: {''.join(invalid)}")

    return ParsedSequence(cleaned=body, header=header, length=len(body))


# ---------------------------------------------------------------------------
# Physicochemical properties
# ---------------------------------------------------------------------------

def molecular_weight(sequence: str) -> float:
    """Molecular weight in Da, using monoisotopic residue masses.

    The weight of a protein is the sum of its residue masses plus the mass of
    one water molecule (the peptide bond condensation).
    """
    total = sum(RESIDUE_MASS.get(aa, 0.0) for aa in sequence)
    return total + 18.01528


def isoelectric_point(sequence: str) -> float:
    """Isoelectric point by a simplified Henderson-Hasselbalch charge model.

    The pI is the pH at which the net charge is zero. We bisect over pH 0-14.
    """
    n = len(sequence)
    if n == 0:
        return 7.0

    def net_charge(ph: float) -> float:
        charge = 0.0
        # N-terminus (positive below its pKa).
        charge += 1.0 / (1.0 + 10 ** (_PKA_NTERM - ph))
        # C-terminus (negative above its pKa).
        charge -= 1.0 / (1.0 + 10 ** (ph - _PKA_CTERM))
        for aa in sequence:
            pka = _PKA_SIDECHAIN.get(aa)
            if pka is None:
                continue
            if aa in {"D", "E", "C", "Y"}:
                charge -= 1.0 / (1.0 + 10 ** (ph - pka))
            else:  # H, K, R — basic
                charge += 1.0 / (1.0 + 10 ** (pka - ph))
        return charge

    lo, hi = 0.0, 14.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if net_charge(mid) > 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 2)


def charge_at_ph7(sequence: str) -> float:
    """Net charge at pH 7.0."""
    n = len(sequence)
    if n == 0:
        return 0.0
    charge = 0.0
    charge += 1.0 / (1.0 + 10 ** (_PKA_NTERM - 7.0))
    charge -= 1.0 / (1.0 + 10 ** (7.0 - _PKA_CTERM))
    for aa in sequence:
        pka = _PKA_SIDECHAIN.get(aa)
        if pka is None:
            continue
        if aa in {"D", "E", "C", "Y"}:
            charge -= 1.0 / (1.0 + 10 ** (7.0 - pka))
        else:
            charge += 1.0 / (1.0 + 10 ** (pka - 7.0))
    return round(charge, 2)


def gravy(sequence: str) -> float:
    """Grand average of hydropathy (Kyte-Doolittle)."""
    if not sequence:
        return 0.0
    return round(sum(HYDROPATHY.get(aa, 0.0) for aa in sequence) / len(sequence), 2)


def composition(sequence: str) -> dict[str, float]:
    """Amino-acid composition as percentages of the sequence."""
    n = len(sequence)
    if n == 0:
        return {}
    counts: dict[str, int] = {}
    for aa in sequence:
        counts[aa] = counts.get(aa, 0) + 1
    return {aa: round(count / n * 100.0, 2) for aa, count in sorted(counts.items())}


def properties(sequence: str) -> dict:
    """All physicochemical properties in one dict, ready for the API."""
    return {
        "length": len(sequence),
        "molecular_weight_da": round(molecular_weight(sequence), 2),
        "isoelectric_point": isoelectric_point(sequence),
        "charge_at_ph7": charge_at_ph7(sequence),
        "gravy": gravy(sequence),
        "composition": composition(sequence),
    }