# Deploy COMPLYSCAN to Vercel

## 1. Prerequisites

- A Git repository containing this folder at its root.
- A Vercel project with Services available.
- A pooled PostgreSQL database from a Vercel Marketplace provider such as Neon or Supabase.
- A private Vercel Blob store connected to the project.
- A Google AI Studio Gemini API key.
- For production, an OIDC/JWT provider exposing issuer, audience and JWKS URL.

## 2. Configure environment variables

Copy the names from `.env.example` into Vercel Project Settings -> Environment Variables.

Required for an SIH preview:

```text
APP_ENV=preview
AUTH_MODE=demo
DATABASE_URL=<pooled PostgreSQL URL>
ALLOW_MEMORY_FALLBACK=false
VISION_PROVIDER=gemini
GEMINI_API_KEY=<server-side secret>
GEMINI_MODEL=gemini-2.5-flash
BLOB_READ_WRITE_TOKEN=<created by the connected private Blob store>
OBJECT_ALLOWED_HOSTS=.blob.vercel-storage.com
RULESET_ID=LMPC_MVP
RULESET_VERSION=LMPC_2026_08_26
```

Do not create `NEXT_PUBLIC_GEMINI_API_KEY`. The Gemini key must never enter the browser bundle.

For production, additionally set:

```text
APP_ENV=production
AUTH_MODE=jwt
AUTH_ISSUER=<issuer>
AUTH_AUDIENCE=<audience>
AUTH_JWKS_URL=<https JWKS endpoint>
```

## 3. Create PostgreSQL tables once

From `apps/api`, with `DATABASE_URL` set to a direct or migration-safe URL:

```bash
python -m app.init_db
```

Do not run table creation from a request handler or on every serverless cold start. For later schema changes, replace this bootstrap with versioned Alembic migrations.

## 4. Deploy

Import the Git repository in Vercel or run `vercel` from the repository root. `vercel.json` creates two Services:

- `web` rooted at `apps/web`
- `api` rooted at `apps/api` with entrypoint `index:app`

Routing is same-origin:

- `/api/blob-upload` -> Next.js upload-token route
- every other `/api/*` -> FastAPI
- all other paths -> Next.js

Choose the Vercel Function region closest to the PostgreSQL database. Do not hard-code Mumbai unless the database is also nearby.

## 5. Verify the preview

1. `GET /api/health` reports PostgreSQL, Gemini and Blob readiness without returning any secret.
2. Open the app and use the complete-label fixture before spending a Gemini request.
3. Upload a real JPG/PNG/WebP. Browser bytes must go directly to Blob, not through a Vercel Function.
4. Confirm that the Blob object is private and that FastAPI can retrieve it server-side.
5. Run analysis and verify five results with evidence, applicability, prompt/model/ruleset provenance and the human-review notice.
6. Confirm an Analyst cannot record a review disposition.
7. Confirm a Reviewer can disposition an applicable rule only with a reason.
8. Export JSON and print the same evidence snapshot.
9. Search built browser chunks for `GEMINI_API_KEY`; there must be no occurrence.
10. Redeploy/cold-start and verify inspections remain because persistence is PostgreSQL, not memory or `/tmp`.

## Vercel constraints addressed

- Function request/response bodies are kept below the platform limit. Normal production images use browser-direct Blob uploads.
- Inline Base64 is restricted to a small local-preview fallback and is not the production path.
- No durable data is written to the read-only deployment filesystem or `/tmp`.
- Gemini runs server-side with bounded images, timeout/retry controls and strict response validation.
- The Python function excludes tests and caches from its deployment bundle.

## Local development

API terminal:

```bash
cd apps/api
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Web terminal:

```bash
cd apps/web
npm install
# copy .env.local.example to .env.local; it sets browser and server API bases to http://127.0.0.1:8000
npm run dev
```

Use `VISION_PROVIDER=fixture`, `AUTH_MODE=demo`, an empty `DATABASE_URL`, and `ALLOW_MEMORY_FALLBACK=true` locally. This mode is visibly ephemeral and suitable only for development/judge-fixture demonstrations.

## Fallback if Vercel Services is unavailable

Create two Vercel projects from the same repository:

- Web project root: `apps/web`
- API project root: `apps/api`

Set `NEXT_PUBLIC_API_BASE_URL` in the web project to the API project URL, and add that exact web origin to `CORS_ORIGINS` in the API project. The one-project Services deployment is preferred because it avoids cross-origin cookie/token and preview-URL drift.
