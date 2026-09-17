# COMPLYSCAN API

Vercel-compatible FastAPI backend for evidence-first Legal Metrology packaged-commodity screening. AI extracts visible facts; applicability selects checks; the deterministic five-rule engine evaluates; an authorized human reviewer must disposition each applicable check. Output is decision support, never a final legal or enforcement determination.

## Local test / preview

```powershell
python -m pytest
$env:VISION_PROVIDER='fixture'
uvicorn app.main:app --reload
```

When `DATABASE_URL` is absent, the API uses a process-memory demo repository. It never writes durable local files. When `DATABASE_URL` is present, standard PostgreSQL via SQLAlchemy is used. Create tables through release/migration tooling by setting `COMPLYSCAN_CREATE_TABLES=1` for a one-off controlled bootstrap; imports never run migrations.

## Authentication

`AUTH_MODE=demo` accepts only explicitly supplied development bearer identities:

```text
Authorization: Bearer demo:<subject>:<ROLE>
```

Roles: `ADMIN`, `LEGAL_REVIEWER`, `COMPLIANCE_ANALYST`, `VIEWER`. Demo auth is refused in `APP_ENV=production`. Production should set `AUTH_MODE=jwt`, `AUTH_ISSUER`, `AUTH_AUDIENCE`, and `AUTH_JWKS_URL`; JWT roles are accepted from `role` or `roles` only after signature, issuer, and audience verification.

## Vision

`VISION_PROVIDER=fixture` is deterministic and visibly marked as pre-extracted demo evidence. `VISION_PROVIDER=gemini` requires server-only `GEMINI_API_KEY`. The Gemini payload includes the JSON contract in the text prompt and `generationConfig.responseMimeType = application/json`; it deliberately contains neither `responseSchema` nor `response_schema`.

The analyze endpoint accepts image *metadata/object references*, not large image bodies. Configure object URLs that the server/provider can retrieve, or use fixture references for the judge-demo path. Browser uploads must transfer directly to object storage.

## Main endpoints

- `GET /api/health`
- `GET|POST /api/inspections`
- `GET /api/inspections/{id}`
- `POST /api/inspections/{id}/analyze`
- `POST /api/inspections/{id}/reviews`
- `GET /api/inspections/{id}/report.json`
- `GET /api/audit-events`
- `POST /api/storage/upload-intents` (metadata/direct-upload contract only)
- `POST /api/storage/objects` (register completed direct upload metadata)

No secret, image bytes, generated PDF, or large object body is returned by the function.
