# Proteoscope

**Deterministic, explainable protein structure analysis.** Paste a sequence, get
secondary structure, a contact map, and a 3D C-alpha trace — with every number
traceable to a published scale.

[![Python 3.11](https://img.shields.io/badge/python-3.11-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-79%20passing-4dd4ac)](#tests)
[![License: MIT](https://img.shields.io/badge/license-MIT-5aa9f0)](LICENSE)
[![No ML weights](https://img.shields.io/badge/ML%20weights-none-ffc857)](#what-this-is-not)

---

## What it does

Give it a protein sequence. It gives you back:

- **Physicochemical properties** — molecular weight, isoelectric point (by
  bisection), GRAVY, aliphatic index, aromaticity, extinction coefficient.
- **Secondary structure** — H/E/T/C per residue, via Chou-Fasman propensities,
  with the contiguous segments listed.
- **A contact map** — which residues are close in space, constrained by what the
  chain can physically reach.
- **A 3D C-alpha trace** — ideal geometry, then position-based dynamics to
  satisfy the contacts and remove clashes. Rotatable in the browser.
- **Per-residue confidence** — a heuristic in [0, 1], labelled as a heuristic.

## What this is not

**It is not AlphaFold.** There are no learned weights and no network calls. The
secondary-structure method is Chou-Fasman (1974), which agrees with experiment
on roughly 60–65% of residues. The 3D trace is a physically-constrained model,
not a prediction of the true fold. Use it for teaching, triage, and exploration
— not for anything that depends on a real structure.

That trade is the whole point. A tool where you can point at any residue and say
*why* it was called a helix is useful in a way an opaque model is not.

## Screenshots

| Analyze | 3D trace |
|---|---|
| ![Sequence input and summary statistics](screenshots/01-analyze.png) | ![Rotatable C-alpha trace](screenshots/02-structure.png) |

| Contact map | Properties & per-residue table |
|---|---|
| ![Residue-residue contact map](screenshots/03-contacts.png) | ![Physicochemical properties and residue table](screenshots/04-properties.png) |

| How it works | Mobile |
|---|---|
| ![The About view explaining the method](screenshots/05-about.png) | ![Mobile layout](screenshots/06-mobile.png) |

## Quick start

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-13-proteoscope.git
cd day-13-proteoscope

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # defaults work as-is for local dev
uvicorn app.main:app --reload --port 8013
```

Open <http://localhost:8013>. Interactive API docs are at
<http://localhost:8013/api/docs>.

### With Docker

```bash
docker compose up --build
```

That brings up the app on port 8013 and a PostgreSQL instance behind it.

## Usage

### In the browser

1. Paste a sequence (bare, or a FASTA record — headers are handled).
2. Optionally give it a label and tick **Save to my account**.
3. Hit **Analyze structure**.

The example chips load a real sequence (chicken lysozyme C) and two synthetic
peptides so you can see the difference between a helix-rich and a sheet-rich
result immediately.

### From the API

```bash
# Register (returns a token immediately — no second login round-trip)
TOKEN=$(curl -s -X POST http://localhost:8013/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"helix1234","full_name":"You"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

# Predict and save
curl -s -X POST http://localhost:8013/api/predictions \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"sequence":"MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR","save":true,"label":"Lysozyme C"}'

# Export as PDB
curl -s "http://localhost:8013/api/predictions/1/export?fmt=pdb" \
  -H "Authorization: Bearer $TOKEN" -o structure.pdb
```

Full endpoint reference: [`docs/api.md`](docs/api.md).

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q          # 79 tests
ruff check .       # clean
black --check .    # clean
```

The tests check against published values rather than re-asserting the
implementation — molecular weight per residue, pI sign behaviour, the physical
reachability of every predicted contact, and the fact that the relaxation does
not diverge. Two of them are regression tests for bugs found during
development: the force-integration divergence, and FASTA header letters being
counted as residues.

## Deployment

Proteoscope ships with two deployment paths, both already wired up:

**Docker** — the whole stack, database included:

```bash
docker compose up --build
# app on http://localhost:8013, Postgres on 5432
```

**Vercel** — serverless, for the API and the static UI:

```bash
npm i -g vercel
vercel --prod --yes --token "$VERCEL_TOKEN"
```

`vercel.json` and `api/index.py` are already in the repo, so the deploy is a
single command once a token is present.

> **Status:** this repo has not been deployed to a live URL yet — the build
> environment it was developed in had no `VERCEL_TOKEN`, and I would rather say
> that plainly than paste a link that does not resolve. Everything needed to
> deploy is committed and the production build passes locally. Add a token and
> the command above puts it online in about two minutes.

## Tech stack

| Layer | Choice |
|---|---|
| API | FastAPI 0.115, Pydantic v2 |
| ORM | SQLAlchemy 2.0 (SQLite dev / PostgreSQL prod) |
| Auth | PyJWT HS256 + bcrypt (12 rounds) |
| Frontend | Vanilla JS, no build step, canvas rendering |
| Tests | pytest + httpx |
| Lint | ruff + black |
| Deploy | Docker, or Vercel serverless |

## Project layout

```
app/
  engine/          pure computation, no I/O
    sequence.py    parsing, validation, physicochemical properties
    secondary.py   Chou-Fasman secondary-structure prediction
    geometry.py    contact map + 3D trace (position-based dynamics)
    predict.py     pipeline orchestration
    report.py      text / PDB / CSV export
  routers/         health, auth, predictions
  static/          the SPA (index.html, styles.css, app.js)
  config.py        env-driven settings + production safety checks
  database.py      engine, session factory, declarative base
  models.py        User, Prediction
  schemas.py       request/response validation
  security.py      bcrypt + JWT
  ratelimit.py     sliding-window limiter
  deps.py          current-user and db dependencies
  main.py          app factory, middleware, error handlers
api/index.py       Vercel serverless entrypoint
tests/             78 tests
docs/              setup, usage, API reference
```

## License

MIT — see [LICENSE](LICENSE).

---

*Part of a 30-day build challenge: one production-shaped project a day.*
