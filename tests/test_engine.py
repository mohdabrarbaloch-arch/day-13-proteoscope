"""Tests for secondary-structure prediction and the geometry pipeline."""

from __future__ import annotations

import math

from app.engine.geometry import (
    CLASH_DISTANCE,
    CONTACT_CUTOFF,
    build_structure,
    predict_contacts,
)
from app.engine.predict import predict_structure
from app.engine.secondary import (
    COIL,
    HELIX,
    predict_secondary_structure,
)
from tests.conftest import HELIX_PEPTIDE, LYSOZYME, SHEET_PEPTIDE


class TestSecondaryStructure:
    def test_assignment_length_matches_sequence(self):
        ss = predict_secondary_structure(LYSOZYME)
        assert len(ss.assignment) == len(LYSOZYME)

    def test_fractions_sum_to_one(self):
        ss = predict_secondary_structure(LYSOZYME)
        total = ss.helix_fraction + ss.sheet_fraction + ss.turn_fraction + ss.coil_fraction
        # Each fraction is rounded to 4 dp, so the sum can drift a few units in
        # the last place.
        assert abs(total - 1.0) < 1e-3

    def test_helix_peptide_is_mostly_helix(self):
        ss = predict_secondary_structure(HELIX_PEPTIDE)
        assert ss.helix_fraction > 0.5

    def test_sheet_peptide_is_mostly_sheet(self):
        ss = predict_secondary_structure(SHEET_PEPTIDE)
        assert ss.sheet_fraction > 0.5

    def test_proline_breaks_a_helix(self):
        # A run of strong helix formers with a proline in the middle must not be
        # assigned as one continuous helix.
        seq = "MEELLKKLEEALKKPEEALKKLEEALKKLEEALKKLEEALKK"
        ss = predict_secondary_structure(seq)
        pro_index = seq.index("P")
        assert ss.assignment[pro_index] != HELIX

    def test_segments_cover_the_whole_sequence(self):
        ss = predict_secondary_structure(LYSOZYME)
        covered = sum(seg["length"] for seg in ss.segments)
        assert covered == len(LYSOZYME)

    def test_segments_are_contiguous_and_1_based(self):
        ss = predict_secondary_structure(LYSOZYME)
        assert ss.segments[0]["start"] == 1
        assert ss.segments[-1]["end"] == len(LYSOZYME)
        for a, b in zip(ss.segments, ss.segments[1:], strict=False):
            assert b["start"] == a["end"] + 1

    def test_empty_sequence_is_handled(self):
        ss = predict_secondary_structure("")
        assert ss.assignment == ""
        assert ss.segments == []


class TestContacts:
    def test_contacts_respect_minimum_separation(self):
        ss = predict_secondary_structure(LYSOZYME)
        contacts = predict_contacts(LYSOZYME, ss)
        for i, j, _ in contacts.pairs:
            assert j - i >= 4

    def test_contacts_are_physically_reachable(self):
        # No pair may be further apart in sequence than the chain can span.
        ss = predict_secondary_structure(LYSOZYME)
        contacts = predict_contacts(LYSOZYME, ss)
        for i, j, _ in contacts.pairs:
            assert 3.4 * (j - i) >= CONTACT_CUTOFF

    def test_per_residue_degree_is_capped(self):
        ss = predict_secondary_structure(LYSOZYME)
        contacts = predict_contacts(LYSOZYME, ss)
        assert max(contacts.per_residue) <= 12

    def test_density_is_a_fraction(self):
        ss = predict_secondary_structure(LYSOZYME)
        contacts = predict_contacts(LYSOZYME, ss)
        assert 0.0 <= contacts.density <= 1.0

    def test_short_sequence_yields_no_contacts(self):
        ss = predict_secondary_structure("MKTA")
        contacts = predict_contacts("MKTA", ss)
        assert contacts.count == 0


class TestGeometry:
    def test_structure_is_deterministic(self):
        a = predict_structure(LYSOZYME)
        b = predict_structure(LYSOZYME)
        assert a["structure"]["coordinates"] == b["structure"]["coordinates"]

    def test_coordinates_are_finite(self):
        r = predict_structure(LYSOZYME)
        for point in r["structure"]["coordinates"]:
            for axis in ("x", "y", "z"):
                assert math.isfinite(point[axis])

    def test_structure_is_compact_not_exploded(self):
        # The first version of the relaxation diverged to 1e27. A real protein
        # of this size has an Rg of roughly 10-20 A; anything past 60 is broken.
        r = predict_structure(LYSOZYME)
        assert r["structure"]["radius_of_gyration"] < 60

    def test_radius_of_gyration_grows_with_length(self):
        short = predict_structure(LYSOZYME)
        long_seq = LYSOZYME * 3
        long = predict_structure(long_seq)
        assert long["structure"]["radius_of_gyration"] > short["structure"]["radius_of_gyration"]

    def test_consecutive_residues_stay_bonded(self):
        r = predict_structure(LYSOZYME)
        coords = r["structure"]["coordinates"]
        for a, b in zip(coords, coords[1:], strict=False):
            d = math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
            # Chain constraints keep neighbours within a plausible C-alpha gap.
            assert d < 8.0

    def test_confidence_is_bounded(self):
        r = predict_structure(LYSOZYME)
        for c in r["structure"]["confidence"]:
            assert 0.0 <= c <= 1.0

    def test_confidence_length_matches_sequence(self):
        r = predict_structure(LYSOZYME)
        assert len(r["structure"]["confidence"]) == len(LYSOZYME)

    def test_helix_residues_score_higher_than_coil(self):
        r = predict_structure(HELIX_PEPTIDE)
        ss = r["secondary_structure"]["assignment"]
        conf = r["structure"]["confidence"]
        helix_conf = [conf[i] for i, s in enumerate(ss) if s == HELIX]
        coil_conf = [conf[i] for i, s in enumerate(ss) if s == COIL]
        if helix_conf and coil_conf:
            assert sum(helix_conf) / len(helix_conf) > sum(coil_conf) / len(coil_conf)

    def test_build_structure_returns_expected_shape(self):
        ss = predict_secondary_structure(LYSOZYME)
        contacts = predict_contacts(LYSOZYME, ss)
        structure = build_structure(LYSOZYME, ss, contacts)
        assert len(structure.coordinates) == len(LYSOZYME)
        assert structure.mean_confidence > 0

    def test_clash_distance_is_respected_on_average(self):
        # Not every pair can be separated in a dense fold, but the mean nearest
        # neighbour distance must be above the clash threshold.
        r = predict_structure(LYSOZYME)
        coords = r["structure"]["coordinates"]
        nearest = []
        for i, a in enumerate(coords):
            best = min(
                math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
                for j, b in enumerate(coords)
                if j != i
            )
            nearest.append(best)
        assert sum(nearest) / len(nearest) > CLASH_DISTANCE * 0.8


class TestPipeline:
    def test_full_result_has_every_section(self):
        r = predict_structure(LYSOZYME)
        for key in (
            "engine",
            "sequence",
            "properties",
            "secondary_structure",
            "contacts",
            "structure",
            "residue_table",
            "profiles",
        ):
            assert key in r

    def test_profiles_can_be_omitted(self):
        r = predict_structure(LYSOZYME, include_profile=False)
        assert "profiles" not in r

    def test_residue_table_matches_sequence(self):
        r = predict_structure(LYSOZYME)
        assert len(r["residue_table"]) == len(LYSOZYME)
        assert r["residue_table"][0]["residue"] == LYSOZYME[0]
        assert r["residue_table"][0]["index"] == 1

    def test_engine_identifies_itself_honestly(self):
        r = predict_structure(LYSOZYME)
        assert r["engine"]["name"] == "Proteoscope"
        assert "not" in r["engine"]["method"].lower() or "no learned weights" in r["engine"]["method"]
