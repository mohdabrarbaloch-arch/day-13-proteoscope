"""Sequence parsing, validation, and physicochemical properties.

Every constant here is a published value, not a fitted one:

* residue masses      -- average isotopic masses (IUPAC)
* Kyte-Doolittle      -- hydropathy scale, J. Mol. Biol. 157:105 (1982)
* pKa set             -- EMBOSS/ExPASy convention
* extinction coeff.   -- Gill & von Hippel, Anal. Biochem. 182:319 (1989)
* aliphatic index     -- Ikai, J. Biochem. 88:1895 (1980)

Nothing in this module is random or time-dependent, so the same sequence always
yields the same numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

STANDARD_AA: str = "ACDEFGHIKLMNPQRSTVWY"
AA_SET: frozenset[str] = frozenset(STANDARD_AA)

THREE_LETTER: dict[str, str] = {
    "A": "Ala",
    "R": "Arg",
    "N": "Asn",
    "D": "Asp",
    "C": "Cys",
    "E": "Glu",
    "Q": "Gln",
    "G": "Gly",
    "H": "His",
    "I": "Ile",
    "L": "Leu",
    "K": "Lys",
    "M": "Met",
    "F": "Phe",
    "P": "Pro",
    "S": "Ser",
    "T": "Thr",
    "W": "Trp",
    "Y": "Tyr",
    "V": "Val",
}

# Average residue masses in daltons (residue only, no water).
RESIDUE_MASS: dict[str, float] = {
    "A": 71.0788,
    "R": 156.1875,
    "N": 114.1038,
    "D": 115.0886,
    "C": 103.1388,
    "E": 129.1155,
    "Q": 128.1307,
    "G": 57.0519,
    "H": 137.1411,
    "I": 113.1594,
    "L": 113.1594,
    "K": 128.1741,
    "M": 131.1926,
    "F": 147.1766,
    "P": 97.1167,
    "S": 87.0782,
    "T": 101.1051,
    "W": 186.2132,
    "Y": 163.1760,
    "V": 99.1326,
}

WATER_MASS: float = 18.0153

# Kyte-Doolittle hydropathy. Positive = hydrophobic, negative = hydrophilic.
KYTE_DOOLITTLE: dict[str, float] = {
    "A": 1.8,
    "R": -4.5,
    "N": -3.5,
    "D": -3.5,
    "C": 2.5,
    "Q": -3.5,
    "E": -3.5,
    "G": -0.4,
    "H": -3.2,
    "I": 4.5,
    "L": 3.8,
    "K": -3.9,
    "M": 1.9,
    "F": 2.8,
    "P": -1.6,
    "S": -0.8,
    "T": -0.7,
    "W": -0.9,
    "Y": -1.3,
    "V": 4.2,
}

# Side-chain pKa values (EMBOSS convention) plus the terminal groups.
PKA_SIDECHAIN: dict[str, float] = {
    "C": 8.5,
    "D": 3.9,
    "E": 4.1,
    "H": 6.5,
    "K": 10.8,
    "R": 12.5,
    "Y": 10.1,
}
PKA_NTERM: float = 8.6
PKA_CTERM: float = 3.6

# Residues that carry a positive charge when protonated.
POSITIVE: frozenset[str] = frozenset("KRH")
NEGATIVE: frozenset[str] = frozenset("DECY")

AROMATIC: frozenset[str] = frozenset("FWY")


class SequenceError(ValueError):
    """Raised when a sequence cannot be parsed or is not usable."""


@dataclass(frozen=True)
class ParsedSequence:
    """A validated protein sequence plus the raw input it came from."""

    sequence: str
    raw_length: int
    header: str | None
    removed: int

    @property
    def length(self) -> int:
        return len(self.sequence)


def parse_sequence(raw: str) -> ParsedSequence:
    """Clean and validate a protein sequence.

    Accepts a bare sequence or a FASTA record (``>header`` line first). Strips
    whitespace, digits and common separators, uppercases the rest, and rejects
    anything that is not one of the 20 standard residues.

    Raises:
        SequenceError: if the input is empty, too short, or contains residues
            outside the standard alphabet.
    """
    if raw is None:
        raise SequenceError("No sequence provided.")

    header: str | None = None
    body_lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">") or stripped.startswith(";"):
            if header is None:
                header = stripped[1:].strip() or None
            continue
        body_lines.append(stripped)

    joined = "".join(body_lines)
    # Drop whitespace, digits and the separators people paste in from papers.
    cleaned_chars: list[str] = []
    for ch in joined:
        if ch.isspace() or ch.isdigit() or ch in "-.*_|,":
            continue
        cleaned_chars.append(ch.upper())

    sequence = "".join(cleaned_chars)
    removed = len(joined) - len(sequence)

    if not sequence:
        raise SequenceError("No sequence provided.")

    invalid = sorted({c for c in sequence if c not in AA_SET})
    if invalid:
        shown = ", ".join(invalid[:10])
        raise SequenceError(
            f"Sequence contains {len(invalid)} non-standard residue type(s): {shown}. "
            "Only the 20 standard amino acids (ACDEFGHIKLMNPQRSTVWY) are supported."
        )

    if len(sequence) < 10:
        raise SequenceError(
            f"Sequence is only {len(sequence)} residues long. "
            "At least 10 are needed for a meaningful prediction."
        )

    return ParsedSequence(
        sequence=sequence,
        raw_length=len(joined),
        header=header,
        removed=removed,
    )


def composition(sequence: str) -> dict[str, int]:
    """Count each standard residue. Absent residues are reported as 0."""
    counts = dict.fromkeys(STANDARD_AA, 0)
    for ch in sequence:
        counts[ch] += 1
    return counts


def molecular_weight(sequence: str) -> float:
    """Average molecular weight in daltons, including the water lost on bonding."""
    if not sequence:
        return 0.0
    return sum(RESIDUE_MASS[c] for c in sequence) + WATER_MASS


def net_charge(sequence: str, ph: float) -> float:
    """Net charge at a given pH, using the Henderson-Hasselbalch approximation.

    Termini are counted once each; every ionisable side chain is counted per
    occurrence.
    """
    if not sequence:
        return 0.0

    charge = 0.0
    # N-terminus (positive when protonated).
    charge += 1.0 / (1.0 + 10.0 ** (ph - PKA_NTERM))
    # C-terminus (negative when deprotonated).
    charge -= 1.0 / (1.0 + 10.0 ** (PKA_CTERM - ph))

    for residue, pka in PKA_SIDECHAIN.items():
        count = sequence.count(residue)
        if not count:
            continue
        if residue in POSITIVE:
            charge += count / (1.0 + 10.0 ** (ph - pka))
        else:
            charge -= count / (1.0 + 10.0 ** (pka - ph))
    return charge


def isoelectric_point(sequence: str, tolerance: float = 1e-4) -> float:
    """The pH at which net charge is zero, found by bisection.

    Bisection rather than a closed form because the charge function is monotonic
    in pH but not analytically invertible once several groups overlap.
    """
    if not sequence:
        return 0.0
    low, high = 0.0, 14.0
    for _ in range(100):
        mid = (low + high) / 2.0
        if net_charge(sequence, mid) > 0:
            low = mid
        else:
            high = mid
        if high - low < tolerance:
            break
    return round((low + high) / 2.0, 2)


def gravy(sequence: str) -> float:
    """Grand average of hydropathy (Kyte-Doolittle)."""
    if not sequence:
        return 0.0
    return round(sum(KYTE_DOOLITTLE[c] for c in sequence) / len(sequence), 3)


def aromaticity(sequence: str) -> float:
    """Fraction of aromatic residues (F, W, Y)."""
    if not sequence:
        return 0.0
    return round(sum(1 for c in sequence if c in AROMATIC) / len(sequence), 4)


def aliphatic_index(sequence: str) -> float:
    """Ikai's aliphatic index: 100 * (A% + 2.9*V% + 3.9*(I% + L%)).

    A rough proxy for thermostability — higher means a more tightly packed
    aliphatic core.
    """
    if not sequence:
        return 0.0
    n = len(sequence)
    a = sequence.count("A") / n * 100.0
    v = sequence.count("V") / n * 100.0
    i = sequence.count("I") / n * 100.0
    leu = sequence.count("L") / n * 100.0
    return round(a + 2.9 * v + 3.9 * (i + leu), 2)


def extinction_coefficient(sequence: str) -> int:
    """Molar extinction coefficient at 280 nm (Gill & von Hippel).

    Assumes all cysteines are reduced, which is the conservative choice: it
    under-reports rather than over-reports.
    """
    n_w = sequence.count("W")
    n_y = sequence.count("Y")
    return n_w * 5500 + n_y * 1490


def absorbance_280(sequence: str) -> float:
    """A280 of a 1 g/L solution, i.e. epsilon / molecular weight."""
    mw = molecular_weight(sequence)
    if mw <= 0:
        return 0.0
    return round(extinction_coefficient(sequence) / mw, 3)


def hydropathy_profile(sequence: str, window: int = 9) -> list[float]:
    """Sliding-window Kyte-Doolittle average, one value per residue.

    Windows are truncated at the termini rather than padded, so the first and
    last values are averages over fewer residues — the alternative (padding with
    zeros) invents data that is not there.
    """
    n = len(sequence)
    if n == 0:
        return []
    window = max(1, min(window, n))
    half = window // 2
    profile: list[float] = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        segment = sequence[lo:hi]
        profile.append(round(sum(KYTE_DOOLITTLE[c] for c in segment) / len(segment), 3))
    return profile


def properties(sequence: str) -> dict:
    """The full physicochemical summary for a sequence."""
    return {
        "length": len(sequence),
        "molecular_weight_da": round(molecular_weight(sequence), 2),
        "isoelectric_point": isoelectric_point(sequence),
        "net_charge_ph7": round(net_charge(sequence, 7.0), 3),
        "gravy": gravy(sequence),
        "aromaticity": aromaticity(sequence),
        "aliphatic_index": aliphatic_index(sequence),
        "extinction_coefficient_m1cm1": extinction_coefficient(sequence),
        "absorbance_280_1g_per_l": absorbance_280(sequence),
    }
