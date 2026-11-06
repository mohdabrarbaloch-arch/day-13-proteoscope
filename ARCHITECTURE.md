# Proteoscope — Architecture

## What this is

Proteoscope takes a protein sequence and returns a structure analysis: secondary
structure, a residue-residue contact map, and a 3D C-alpha trace. It is
deliberately **not** a machine-learning model. Every number comes from a
published scale (Chou-Fasman propensities, Kyte-Doolittle hydrophobicity,
standard residue masses) or a stated heuristic, so any result can be reproduced
by hand. That determinism is the product's core value: a tool where you can
point at any residue and say *why* it was called a helix.

## System diagram

```
                    ┌─────────────────────────────────────────────┐
                    │                 Browser (SPA)               │
                    │  index.html · styles.css · app.js           │
                    │  canvas 3D viewer · contact map · tables    │
                    └──────────────────────┬──────────────────────┘
                                           │  JSON over HTTP
                                           ▼
                    ┌─────────────────────────────────────────────┐
                    │              FastAPI application            │
                    │  ┌───────────┐ ┌───────────┐ ┌───────────┐  │
                    │  │  auth     │ │predictions│ │  health   │  │
                    │  │  router   │ │  router   │ │  router   │  │
                    │  └─────┬─────┘ └─────┬─────┘ └───────────┘  │
                    │        │             │                       │
                    │  ┌─────▼─────────────▼─────┐                 │
                    │  │  rate limiter (in-proc) │                 │
                    │  └─────┬───────────────────┘                 │
                    │  ┌─────▼───────────────────┐                 │
                    │  │  structure engine       │                 │
                    │  │  sequence → secondary   │                 │
                    │  │  → contacts → 3D trace  │                 │
                    │  └─────┬───────────────────┘                 │
                    │  ┌─────▼───────────────────┐                 │
                    │  │  SQLAlchemy 2.0 ORM     │                 │
                    │  └─────┬───────────────────┘                 │
                    └────────┼─────────────────────────────────────┘
                             ▼
              ┌──────────────────────────────┐
              │  SQLite (dev) / PostgreSQL   │
              │  (prod, via docker-compose)  │
              └──────────────────────────────┘
```

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI 0.115 + Pydantic v2 | Typed request/response, auto OpenAPI docs |
| ORM | SQLAlchemy 2.0 | Same code for SQLite and Postgres |
| Auth | PyJWT HS256 + bcrypt (12 rounds) | Stateless tokens, strong hashing |
| Frontend | Vanilla JS, canvas | No build step, no framework lock-in |
| Rate limit | In-process sliding window | Zero deps, explicit, testable |
| Deploy | Docker / Vercel serverless | Two paths, both wired up |

## Data flow

1. **Request** — the SPA POSTs a sequence to `/api/predictions`. Pydantic does a
   cheap pre-check (length, residue alphabet, FASTA header handling).
2. **Engine** — `predict_structure` runs the pipeline:
   - `parse_sequence` validates and cleans the input.
   - `properties` computes molecular weight, pI, charge, GRAVY, composition.
   - `predict_secondary` runs the Chou-Fasman rules.
   - `predict_contacts` finds hydrophobic/Cys pairs within a sequence window.
   - `generate_backbone` builds a 3D trace with position-based dynamics.
3. **Persist (optional)** — if `save=true`, the result is stored as JSON text
   against the user's account.
4. **Response** — the full result returns inline; the SPA renders the 3D trace,
   contact map, and tables from canvas.

## Scaling notes

- **The engine is CPU-bound and O(n²) in the contact step.** The 2000-residue
  cap keeps a single request under ~2M pair evaluations. For higher throughput,
  run the engine as a separate worker pool and move the API to async.
- **The rate limiter is in-process.** It is correct for a single instance. For
  multiple instances, swap `RateLimiter` for a Redis-backed implementation — the
  `check()` interface is the only contract callers depend on.
- **SQLite is for development.** Production uses Postgres via docker-compose.
  On Vercel, a SQLite URL is transparently redirected to `/tmp` (the only
  writable path on serverless).
- **Stateless API.** JWTs carry the session; nothing is stored server-side, so
  horizontal scaling is trivial once the rate limiter and DB are externalised.

## Security

- Passwords hashed with bcrypt (12 rounds); never logged or returned.
- JWT with issuer check, expiry, and a strong secret (enforced in production).
- Rate limiting per client IP on all `/api` routes.
- CORS restricted to configured origins; security headers set on every response.
- Secrets only in the environment; `.env.example` documents every variable.
- The production config refuses to start with a weak secret or debug on.