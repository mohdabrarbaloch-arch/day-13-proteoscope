# Usage

## The interface

Three views, switchable from the top bar.

### Analyze

The main view. Paste a sequence — bare, or a FASTA record. Headers are handled:
`>sp|P00698|LYSC_CHICK Lysozyme C` is parsed for the header and the residues
below it are used.

Four example chips load ready-made inputs:

- **Lysozyme (78 aa)** — a real sequence, chicken lysozyme C.
- **Helix-rich** — a synthetic peptide of strong helix formers.
- **Sheet-rich** — a synthetic peptide of strong sheet formers.
- **Mixed (244 aa)** — a longer synthetic chain, useful for seeing how the
  contact map and the 3D trace behave at scale.

Tick **Save to my account** to persist the result. You need to be signed in for
that; the app will tell you if you aren't.

### Saved

Your saved predictions, newest first. Each row shows the label, length, mean
confidence, contact count, and timestamp. From here you can:

- **Open** — reload the full result into the Analyze view.
- **PDB** — download the C-alpha trace.
- **Delete** — remove it (with a confirmation).

### About

What the tool is, what it is not, and how the pipeline works.

## Reading the output

### Summary statistics

Eight tiles across the top: residue count, molecular weight, isoelectric point,
GRAVY, helix %, sheet %, contact count, and mean confidence.

### Secondary structure

A proportional bar (helix / sheet / turn / coil) plus the contiguous segments
listed as `H12–34`, `E40–52`, and so on. Coil segments are omitted from the list
— they are the gaps between the interesting parts.

### 3D C-alpha trace

Drag to rotate, scroll to zoom. Two colour modes:

- **Colour by structure** — helix pink, sheet amber, turn blue, coil grey.
- **Colour by confidence** — red (low) through amber to green (high).

The `N` and `C` labels mark the termini. Every fifth residue is drawn as a dot so
the trace reads as a chain rather than a scribble.

### Contact map

A symmetric matrix. A dot at (i, j) means residues i and j are predicted to be
close in space. The diagonal is empty by construction — a residue is not in
contact with itself, and pairs closer than 4 residues apart are excluded because
"contact" there would just mean chain adjacency.

The density figure is the fraction of all possible pairs that are contacts. For
a real globular protein this is typically a few percent.

### Hydropathy and hydrophobic moment

Two per-residue profiles:

- **Hydropathy** — Kyte-Doolittle, windowed. Positive is hydrophobic. Peaks
  suggest buried or membrane-facing stretches.
- **Hydrophobic moment** — computed assuming an ideal alpha helix (3.6 residues
  per turn). A high value means one face of the helix is greasy and the other is
  not, which is the signature of a membrane-spanning or surface-binding helix.

### Per-residue table

Every residue with its index, one- and three-letter codes, secondary-structure
assignment, confidence, and coordinates.

## Exporting

Three formats, all from the Saved view or the Export panel:

| Format | What you get |
|---|---|
| **PDB** | A C-alpha-only trace. Loads in PyMOL, Chimera, Mol*, anything that reads PDB. |
| **CSV** | The per-residue table with coordinates. |
| **Text** | A formatted report with every computed value. |

Exports require the prediction to be saved — the export endpoint reads from the
database, so there has to be a row to read.

## Interpreting confidence honestly

The confidence score is a **heuristic in [0, 1]**, not a calibrated pLDDT. It
rises when a residue sits in a regular secondary element, when its predicted
contacts are actually satisfied in the relaxed structure, and falls when it is
in a clash.

A high score means "this residue's local environment is self-consistent with the
model". It does **not** mean "this residue is in the right place in the real
protein". Treat it as a signal about model quality, not about truth.

## Common questions

**Why does my sheet-rich peptide show no sheet?**
Chou-Fasman needs a run of at least 3 residues above the sheet threshold with no
sheet-breaking residue (P, D, G, K, R, S) inside. Short peptides often can't
satisfy that. Try the Sheet-rich example to see what a clean case looks like.

**Why is the 3D trace so compact?**
Because it is constrained to be. A real globular protein is compact — its radius
of gyration scales as roughly N^0.38 — and the relaxation includes a weak pull
toward that scaling. Without it, a long chain drifts outward into a loose
tangle, which is not what a folded protein looks like.

**Can I use this for a real structure?**
No. Use it to build intuition, to triage which sequences are worth a closer
look, or to teach. For a real structure, use AlphaFold, RoseTTAFold, or — best
of all — an experimental structure from the PDB.
