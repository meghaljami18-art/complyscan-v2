# COMPLYSCAN

Evidence-first packaged-commodity inspection prototype rebuilt as a deployable Next.js + FastAPI application for Vercel.

COMPLYSCAN turns package photographs into a structured inspection, checks applicability, executes five conservative deterministic rules, links each result to visible evidence and routes the result to a role-gated human review. It is decision support—not a final legal, enforcement or prosecution determination.

## What is implemented

- Next.js 15 App Router frontend with TypeScript and responsive capture, dashboard, inspection, review, history, rules and admin surfaces.
- Browser-side quality preflight with bounded image derivatives.
- Browser-direct private Vercel Blob uploads, avoiding Function body-size limits.
- FastAPI service with strict Pydantic request/response contracts.
- Server-only Gemini multimodal provider plus deterministic fixtures for tests and judge demonstrations.
- Evidence assurance for confidence, conflicts and coverage.
- Product context/applicability before deterministic legal-rule evaluation.
- The original five-rule MVP behavior and conservative review boundaries.
- RBAC: `ADMIN`, `LEGAL_REVIEWER`, `COMPLIANCE_ANALYST`, `VIEWER`.
- PostgreSQL repository with atomic append-only audit events and an explicit local in-memory fallback.
- Editable JSON export and printable evidence report.
- One-project Vercel Services routing for the Next.js and Python services.

## Repository

```text
apps/
  web/                       Next.js/React interface and upload-token route
  api/                       FastAPI, providers, assurance, rules, RBAC, repository
    app/
    tests/
docs/
  ARCHITECTURE.md            implemented flow, boundaries and storage design
  DEPLOYMENT.md              exact Vercel, PostgreSQL, Blob and JWT setup
.env.example                 safe environment-variable names and modes
vercel.json                  Vercel Services and same-origin routing
```

## Run locally

### One-click Windows launcher

Double-click `START_COMPLYSCAN.bat` in the repository root. On its first run it will:

1. Verify Python 3.12+, Node.js 20+ and npm.
2. Create `apps/api/.venv` and install backend dependencies.
3. Create safe local fixture/demo environment files.
4. Install frontend dependencies.
5. Start FastAPI and Next.js in separate windows, wait for both health checks and open `http://127.0.0.1:3000`.

Keep the two server windows open. Press `Ctrl+C` inside each server window to stop COMPLYSCAN. The launcher never asks for or writes a Gemini key; real Gemini setup remains a deliberate server-side step.

### Manual API start

```powershell
cd apps/api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:APP_ENV="development"
$env:AUTH_MODE="demo"
$env:VISION_PROVIDER="fixture"
$env:ALLOW_MEMORY_FALLBACK="true"
uvicorn app.main:app --reload --port 8000
```

### Web

```powershell
cd apps/web
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. Local fixture mode uses explicit ephemeral storage and demo bearer identities. Do not use it as production.

## Demo identities

```text
demo:analyst@example.test:COMPLIANCE_ANALYST
demo:reviewer@example.test:LEGAL_REVIEWER
demo:viewer@example.test:VIEWER
demo:admin@example.test:ADMIN
```

They are accepted only outside `APP_ENV=production`.

## Validation

The final source has been checked with:

```text
Backend:  22/22 Pytest tests passed
Frontend: 3/3 Node quality-gate tests passed
TypeScript: tsc --noEmit passed
Lint: ESLint passed with no findings
Build: optimized Next.js production build passed
Smoke: web 200; API health 200; inspection 201; analysis 200; five rule results; human review still required
Vercel: manifest fields checked against the live Vercel OpenAPI schema
```

The suite covers the five deterministic rules and precedence, AI/evidence assurance, request validation, transport image-count invariants, RBAC, reasoned reviews, reports, audit behavior, safe object URLs, repository fallback and production configuration guards.

## Deploy

Read [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). In summary:

1. Push this folder as the Git repository root.
2. Import it as one Vercel project; `vercel.json` creates the `web` and `api` Services.
3. Connect a pooled PostgreSQL database and a private Vercel Blob store.
4. Add `.env.example` names in Vercel, using `APP_ENV=preview` + `AUTH_MODE=demo` for a controlled SIH preview or complete JWT configuration for production.
5. Run `python -m app.init_db` from `apps/api` once against the target database.
6. Add the Gemini key only as server-side `GEMINI_API_KEY`.
7. Deploy and complete the verification checklist.

The deployment intentionally fails fast in production if PostgreSQL, non-ephemeral persistence, JWT authentication, Gemini or private Blob storage is missing.

## Security and legal boundaries

- No client-side Gemini secret or API-key input exists.
- Blob upload tokens are short-lived, role-gated, content-type/size restricted and limited to a safe `complyscan/` path.
- Private evidence is downloaded by FastAPI with the server-side Blob token.
- Arbitrary image hosts, localhost/private-network URLs and unsupported MIME/magic bytes are rejected.
- The FastAPI rule engine is authoritative; frontend data adapters are display-only.
- Audit events include actor, action, target, reason/diff and frozen provenance; they exclude signed URLs and secrets.
- Low quality, insufficient coverage, ambiguous applicability and extraction conflicts route to review instead of unsafe automatic failure.

Current platform references used for the deployment design: [Vercel Services](https://vercel.com/docs/services), [Vercel rewrites](https://vercel.com/docs/rewrites), [client uploads to Vercel Blob](https://vercel.com/docs/vercel-blob/client-upload), [Vercel Functions limitations](https://vercel.com/docs/functions/limitations), and [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi).
