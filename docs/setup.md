# Setup

## Requirements

- Python 3.11 or newer
- pip
- (optional) Docker + Docker Compose, for the containerised path
- (optional) PostgreSQL 14+, if you don't want the SQLite default

## Local development

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-13-proteoscope.git
cd day-13-proteoscope

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt
cp .env.example .env
```

The defaults in `.env.example` work as-is for local development. The app will
create a SQLite file (`proteoscope.db`) on first run and create its tables
automatically.

Start the server:

```bash
uvicorn app.main:app --reload --port 8013
```

- App: <http://localhost:8013>
- API docs: <http://localhost:8013/api/docs>
- Health: <http://localhost:8013/api/health>

## Docker

```bash
docker compose up --build
```

This starts two services:

- `app` — the FastAPI application on port 8013
- `db` — PostgreSQL 16, with a named volume so data survives restarts

The app waits for the database healthcheck before starting. To use Postgres
outside Docker, set `DATABASE_URL` to a `postgresql+psycopg2://` URL.

## Environment variables

Every variable is documented in `.env.example`. The ones that matter:

| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | dev placeholder | **Must** be set to a strong value in production. The app refuses to start otherwise. |
| `ENVIRONMENT` | `development` | Set to `production` to enable the safety checks. |
| `DATABASE_URL` | `sqlite:///./proteoscope.db` | Any SQLAlchemy URL. |
| `MAX_SEQUENCE_LENGTH` | `2000` | The engine is O(n²); this is the real ceiling. |
| `CORS_ORIGINS` | localhost:8013 | Comma-separated. |
| `RATE_LIMIT_AUTH` | `10/minute` | Per client IP, per path. |

## Production checklist

1. Set `SECRET_KEY` to at least 32 random characters.
2. Set `ENVIRONMENT=production` and `DEBUG=false`.
3. Point `DATABASE_URL` at a managed PostgreSQL instance.
4. Set `CORS_ORIGINS` to your real front-end origin — not `*`.
5. Put the app behind TLS (a reverse proxy or your platform's edge).
6. If you run more than one instance, back the rate limiter with Redis. See
   `app/ratelimit.py` — the interface is a single method.

## Running the tests

```bash
pytest -q
```

78 tests, no external services required — they use an in-memory SQLite database
and a fresh rate limiter per test.

## Linting

```bash
ruff check .
black --check .
```

Both must pass cleanly. `ruff check --fix .` and `black .` will fix most issues.

## Troubleshooting

**`RuntimeError: Invalid configuration`** — you set `ENVIRONMENT=production`
without a proper `SECRET_KEY`. That is the check doing its job.

**`sqlite3.OperationalError: unable to open database file`** — on a serverless
platform the filesystem is read-only outside `/tmp`. `app/database.py` handles
this automatically when it detects Vercel or Lambda; if you're on another
platform, set `DATABASE_URL` to a path under `/tmp` or use Postgres.

**429 responses during development** — the rate limiter is working. Auth is
capped at 10 requests/minute per IP. Restart the server to clear it, or raise
`RATE_LIMIT_AUTH` in `.env`.
