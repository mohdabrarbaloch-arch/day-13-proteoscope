# API Reference

Base URL in development: `http://localhost:8013`

Interactive docs (OpenAPI): `/api/docs`

All request and response bodies are JSON. Authenticated endpoints expect
`Authorization: Bearer <token>`.

## Error format

Every error returns the same shape:

```json
{
  "error": "validation_error",
  "detail": "Request validation failed",
  "request_id": "1ebe08ec4424",
  "fields": [
    { "loc": ["body", "sequence"], "msg": "Value error, Sequence contains non-standard residues: O, Z." }
  ]
}
```

`error` is one of `validation_error`, `http_error`, or `internal_error`.
`request_id` is echoed in the `X-Request-ID` response header — quote it when
reporting a problem.

| Status | Meaning |
|---|---|
| 200 | OK |
| 201 | Created |
| 204 | Deleted (no body) |
| 401 | Missing, malformed, or expired token |
| 404 | Not found, or not yours |
| 409 | Email already registered |
| 422 | Validation failed |
| 429 | Rate limited (see `Retry-After`) |
| 500 | Unexpected server error |

---

## Health

### `GET /api/health`

Liveness probe. No auth, no database access.

```json
{
  "status": "ok",
  "app": "Proteoscope",
  "engine": "Proteoscope",
  "version": "1.0.0",
  "environment": "development"
}
```

---

## Authentication

### `POST /api/auth/register`

Create an account. Returns a token immediately — registering logs you in.

**Body**

| Field | Type | Required | Notes |
|---|---|---|---|
| `email` | string | yes | Valid email. Stored lowercased. |
| `password` | string | yes | 8–128 chars, must mix letters and numbers. |
| `full_name` | string | no | Max 120 chars. |

**201**

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": { "id": 1, "email": "you@example.com", "full_name": "You", "created_at": "2026-11-06T19:14:00Z" }
}
```

**409** — email already registered.

### `POST /api/auth/login`

**Body:** `{ "email": "...", "password": "..." }`

**200** — same shape as register.

**401** — incorrect email or password. The same message is returned whether the
email exists or not, so this endpoint cannot be used to enumerate accounts.

### `GET /api/auth/me`

Returns the authenticated user. **401** without a valid token.

---

## Predictions

### `POST /api/predictions`

Run the structure engine. Optionally save the result.

**Body**

| Field | Type | Default | Notes |
|---|---|---|---|
| `sequence` | string | — | Bare sequence or FASTA. 10–2000 residues. |
| `label` | string | `""` | Max 160 chars. Falls back to the FASTA header, then "Untitled". |
| `save` | boolean | `false` | Persist the result. |
| `include_profile` | boolean | `true` | Include the per-residue hydropathy and moment arrays. |

**201**

```json
{
  "result": {
    "engine": { "name": "Proteoscope", "version": "1.0.0", "method": "..." },
    "sequence": { "header": "sp|P00698|LYSC_CHICK Lysozyme C", "length": 78, "cleaned": "MKTAY...", "residues_removed": 0 },
    "properties": {
      "length": 78,
      "molecular_weight_da": 8776.17,
      "isoelectric_point": 10.62,
      "net_charge_ph7": 8.9,
      "gravy": -0.42,
      "aromaticity": 0.0897,
      "aliphatic_index": 78.4,
      "extinction_coefficient_m1cm1": 32390,
      "absorbance_280_1g_per_l": 3.69
    },
    "secondary_structure": {
      "assignment": "CHHHHH...",
      "helix_fraction": 0.4744,
      "sheet_fraction": 0.0,
      "turn_fraction": 0.282,
      "coil_fraction": 0.2436,
      "segments": [ { "type": "helix", "start": 2, "end": 12, "length": 11 } ]
    },
    "contacts": {
      "count": 100,
      "density": 0.0333,
      "max_sequence_separation": 61,
      "pairs": [ { "i": 1, "j": 20, "score": 0.61 } ]
    },
    "structure": {
      "coordinates": [ { "residue": 1, "x": 1.003, "y": 2.822, "z": -21.569 } ],
      "confidence": [0.35, 0.65, ...],
      "mean_confidence": 0.4737,
      "radius_of_gyration": 8.952,
      "end_to_end_distance": 12.4
    },
    "residue_table": [ { "index": 1, "residue": "M", "residue_name": "Met", "ss": "C", "confidence": 0.35 } ],
    "profiles": { "hydropathy": [...], "hydrophobic_moment": [...] }
  },
  "saved": true,
  "id": 1
}
```

**422** — the sequence is empty, too short, too long, or contains non-standard
residues. The `fields` array says which.

### `GET /api/predictions`

List your saved predictions, newest first.

**Query:** `limit` (1–200, default 50), `offset` (default 0).

**200** — an array of summaries (no coordinates, no profiles):

```json
[ { "id": 1, "label": "Lysozyme C", "length": 78, "mean_confidence": 0.4737,
    "helix_fraction": 0.4744, "sheet_fraction": 0.0, "contact_count": 100,
    "created_at": "2026-11-06T19:14:00Z" } ]
```

### `GET /api/predictions/{id}`

Fetch one saved prediction, including the full result.

**200** — the summary fields plus `sequence` and `result`.

**404** — not found, or not yours. A 403 would confirm the id exists, so this
returns 404 instead.

### `DELETE /api/predictions/{id}`

**204** — deleted, no body.

**404** — not found, or not yours.

### `GET /api/predictions/{id}/export`

Download a saved prediction.

**Query:** `fmt` — one of `pdb` (default), `csv`, `txt`.

| Format | Content type | What you get |
|---|---|---|
| `pdb` | `chemical/x-pdb` | C-alpha-only trace. Loads in any PDB viewer. |
| `csv` | `text/csv` | Per-residue table with coordinates. |
| `txt` | `text/plain` | Formatted report with every computed value. |

The response carries `Content-Disposition: attachment` with a filename.

**422** — unknown format.

---

## Rate limits

Per client IP, per path prefix. The longest matching prefix wins.

| Prefix | Default |
|---|---|
| `/api/auth` | 10/minute |
| `/api/predictions` | 30/minute |
| `/api` | 120/minute |

A 429 response includes `Retry-After` in seconds.

## Security headers

Every response carries:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Permissions-Policy: geolocation=(), microphone=(), camera=()
Cross-Origin-Opener-Policy: same-origin
X-Request-ID: <12 hex chars>
```
