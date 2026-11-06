"""Human-readable report generation and export formats.

Turns a prediction dict into something a person can read (a text report) or
something another tool can read (PDB, CSV). The PDB writer emits a CA-only
trace, which is a legitimate — if minimal — PDB file: viewers will load it and
draw the backbone.
"""

from __future__ import annotations

from datetime import UTC, datetime

DISCLAIMER = (
    "Proteoscope is a deterministic, explainable structure *analysis* tool. It "
    "is not AlphaFold, it uses no learned weights, and its output is not an "
    "experimental structure. Use it for teaching, triage and exploration — not "
    "for anything that depends on a real fold."
)


def build_report(prediction: dict) -> str:
    """Render a plain-text report from a prediction dict."""
    seq = prediction["sequence"]
    props = prediction["properties"]
    ss = prediction["secondary_structure"]
    contacts = prediction["contacts"]
    structure = prediction["structure"]

    lines: list[str] = []
    lines.append("=" * 68)
    lines.append("PROTEOSCOPE STRUCTURE REPORT")
    lines.append("=" * 68)
    lines.append(f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    if seq.get("header"):
        lines.append(f"Header:    {seq['header']}")
    lines.append("")

    lines.append("-- SEQUENCE " + "-" * 56)
    lines.append(f"Length:            {seq['length']} residues")
    lines.append(f"Residues removed:  {seq['residues_removed']} (whitespace, digits, separators)")
    lines.append("")

    lines.append("-- PHYSICOCHEMICAL PROPERTIES " + "-" * 39)
    lines.append(f"Molecular weight:  {props['molecular_weight_da']:,.2f} Da")
    lines.append(f"Isoelectric point: {props['isoelectric_point']}")
    lines.append(f"Net charge (pH 7): {props['net_charge_ph7']:+.3f}")
    lines.append(f"GRAVY:             {props['gravy']:+.3f}  (positive = hydrophobic)")
    lines.append(f"Aromaticity:       {props['aromaticity']:.4f}")
    lines.append(f"Aliphatic index:   {props['aliphatic_index']}")
    lines.append(f"Ext. coeff. 280nm: {props['extinction_coefficient_m1cm1']:,} M-1 cm-1")
    lines.append("")

    lines.append("-- SECONDARY STRUCTURE " + "-" * 45)
    lines.append(f"Helix: {ss['helix_fraction'] * 100:5.1f}%")
    lines.append(f"Sheet: {ss['sheet_fraction'] * 100:5.1f}%")
    lines.append(f"Turn:  {ss['turn_fraction'] * 100:5.1f}%")
    lines.append(f"Coil:  {ss['coil_fraction'] * 100:5.1f}%")
    lines.append("")
    lines.append("Segments:")
    for seg in ss["segments"]:
        lines.append(f"  {seg['type']:<6} {seg['start']:>5} - {seg['end']:<5} ({seg['length']} residues)")
    lines.append("")

    lines.append("-- CONTACT MAP " + "-" * 54)
    lines.append(f"Predicted contacts: {contacts['count']}")
    lines.append(f"Contact density:    {contacts['density']}")
    lines.append(f"Longest separation: {contacts['max_sequence_separation']} residues")
    lines.append("")

    lines.append("-- 3D TRACE " + "-" * 57)
    lines.append(f"Radius of gyration: {structure['radius_of_gyration']} A")
    lines.append(f"End-to-end distance: {structure['end_to_end_distance']} A")
    lines.append(f"Mean confidence:    {structure['mean_confidence']:.3f} (heuristic, not pLDDT)")
    lines.append("")

    lines.append("-- NOTE " + "-" * 61)
    lines.append(DISCLAIMER)
    lines.append("=" * 68)
    return "\n".join(lines)


def to_pdb(prediction: dict) -> str:
    """Export the C-alpha trace as a minimal PDB file.

    Only CA atoms are written. That is enough for any viewer to draw the
    backbone, and it is honest about what we actually predicted — we did not
    predict side chains, so we do not write them.
    """
    seq = prediction["sequence"]
    coords = prediction["structure"]["coordinates"]
    confidence = prediction["structure"]["confidence"]
    ss = prediction["secondary_structure"]["assignment"]

    lines: list[str] = []
    lines.append(f"HEADER    PROTEOSCOPE CA-TRACE  {datetime.now(UTC).strftime('%d-%b-%Y')}")
    lines.append(f"TITLE     {seq.get('header') or 'Proteoscope prediction'}")

    for idx, point in enumerate(coords):
        residue = seq["cleaned"][idx] if idx < len(seq["cleaned"]) else "X"
        b_factor = confidence[idx] * 100.0 if idx < len(confidence) else 0.0
        ss_code = ss[idx] if idx < len(ss) else "C"
        # PDB columns are fixed-width; getting them wrong makes files unreadable.
        lines.append(
            f"ATOM  {idx + 1:>5}  CA  {residue:>3} A{idx + 1:>4}    "
            f"{point['x']:>8.3f}{point['y']:>8.3f}{point['z']:>8.3f}"
            f"{1.00:>6.2f}{b_factor:>6.2f}          {ss_code:>2}"
        )

    lines.append("TER")
    lines.append("END")
    return "\n".join(lines) + "\n"


def to_csv(prediction: dict) -> str:
    """Export the per-residue table as CSV."""
    rows = prediction["residue_table"]
    coords = prediction["structure"]["coordinates"]
    out = ["index,residue,residue_name,secondary_structure,confidence,x,y,z"]
    for idx, row in enumerate(rows):
        point = coords[idx] if idx < len(coords) else {"x": 0.0, "y": 0.0, "z": 0.0}
        out.append(
            f"{row['index']},{row['residue']},{row['residue_name']},"
            f"{row['ss']},{row['confidence']},{point['x']},{point['y']},{point['z']}"
        )
    return "\n".join(out) + "\n"
