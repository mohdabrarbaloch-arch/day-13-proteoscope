"""Tests for sequence parsing and physicochemical properties.

These check against published values, not against whatever the code happens to
return — a test that just re-asserts the implementation is worthless.
"""

from __future__ import annotations

import pytest

from app.engine.sequence import (
    SequenceError,
    aliphatic_index,
    aromaticity,
    composition,
    extinction_coefficient,
    gravy,
    hydropathy_profile,
    isoelectric_point,
    molecular_weight,
    net_charge,
    parse_sequence,
)
from tests.conftest import LYSOZYME


class TestParsing:
    def test_accepts_bare_sequence(self):
        parsed = parse_sequence(LYSOZYME)
        assert parsed.sequence == LYSOZYME
        assert parsed.length == 78
        assert parsed.header is None

    def test_accepts_fasta_and_keeps_header(self):
        parsed = parse_sequence(">sp|P00698|LYSC_CHICK Lysozyme C\n" + LYSOZYME)
        assert parsed.header == "sp|P00698|LYSC_CHICK Lysozyme C"
        assert parsed.sequence == LYSOZYME

    def test_strips_whitespace_digits_and_separators(self):
        messy = "MK-TA YI 123 AKQR\nQISFVK"
        parsed = parse_sequence(messy)
        assert parsed.sequence == "MKTAYIAKQRQISFVK"
        assert parsed.removed > 0

    def test_lowercase_is_uppercased(self):
        parsed = parse_sequence(
            "mktayiakqrqisfvkshfsrqleerlglievqapilsrvgdgtqdnlsgaekavqvkvkalpdaqfevvhslakwkr"
        )
        assert parsed.sequence == LYSOZYME

    def test_rejects_empty(self):
        with pytest.raises(SequenceError, match="No sequence"):
            parse_sequence("   \n  ")

    def test_rejects_non_standard_residues(self):
        with pytest.raises(SequenceError, match="non-standard"):
            parse_sequence("MKTAYIAKQRQISFVKXBZ")

    def test_rejects_too_short(self):
        with pytest.raises(SequenceError, match="At least 10"):
            parse_sequence("MKTAYIAK")


class TestProperties:
    def test_molecular_weight_is_plausible_per_residue(self):
        # The average residue mass is ~110 Da. Anything outside 100-120 per
        # residue means the mass table or the summation is wrong.
        mw = molecular_weight(LYSOZYME)
        per_residue = mw / len(LYSOZYME)
        assert 100 < per_residue < 120

    def test_isoelectric_point_is_basic_for_lysozyme(self):
        # Lysozyme is a famously basic protein. This 78-residue fragment is
        # arginine- and lysine-rich, so its pI sits well above neutral.
        pi = isoelectric_point(LYSOZYME)
        assert 8.5 < pi < 11.5

    def test_net_charge_is_zero_at_the_isoelectric_point(self):
        pi = isoelectric_point(LYSOZYME)
        assert abs(net_charge(LYSOZYME, pi)) < 0.05

    def test_net_charge_is_positive_in_acid(self):
        # Below the pI, a basic protein carries net positive charge.
        assert net_charge(LYSOZYME, 3.0) > 0

    def test_net_charge_is_negative_in_base(self):
        assert net_charge(LYSOZYME, 12.0) < 0

    def test_gravy_sign_follows_composition(self):
        hydrophobic = "LLLLLLLLLLLLLLLLLLLL"
        hydrophilic = "KKKKKKKKKKKKKKKKKKKK"
        assert gravy(hydrophobic) > 0
        assert gravy(hydrophilic) < 0

    def test_aromaticity_counts_only_fwy(self):
        assert aromaticity("FWYFWY") == 1.0
        assert aromaticity("AAAAAA") == 0.0
        assert aromaticity("FWYAAA") == pytest.approx(0.5)

    def test_extinction_coefficient_uses_trp_and_tyr(self):
        # One Trp (5500) + one Tyr (1490) = 6990.
        assert extinction_coefficient("WY") == 6990
        assert extinction_coefficient("AAAA") == 0

    def test_aliphatic_index_ranks_thermophilic_peptides_higher(self):
        # A/L/V-rich should beat a G/S/P-rich peptide.
        assert aliphatic_index("ALVALVALVALV") > aliphatic_index("GSPSGSPSGSPS")

    def test_composition_sums_to_length(self):
        counts = composition(LYSOZYME)
        assert sum(counts.values()) == len(LYSOZYME)
        assert set(counts) == set("ACDEFGHIKLMNPQRSTVWY")

    def test_hydropathy_profile_length_matches_sequence(self):
        profile = hydropathy_profile(LYSOZYME, window=9)
        assert len(profile) == len(LYSOZYME)

    def test_hydropathy_profile_is_smoother_than_raw(self):
        # A windowed average must have a smaller spread than the raw values.
        from app.engine.sequence import KYTE_DOOLITTLE

        raw = [KYTE_DOOLITTLE[c] for c in LYSOZYME]
        profile = hydropathy_profile(LYSOZYME, window=9)
        assert (max(profile) - min(profile)) < (max(raw) - min(raw))
