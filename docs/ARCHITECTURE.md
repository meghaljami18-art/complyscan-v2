# COMPLYSCAN target architecture

## Implemented flow

```text
Next.js / React frontend
  -> image-quality preflight and bounded derivatives
  -> authenticated browser-direct private Blob upload on Vercel
  -> FastAPI inspection service
       -> provider layer (Gemini or deterministic fixture)
       -> strict extraction validation
       -> evidence assurance and conflict detection
       -> product context and applicability
       -> versioned five-rule deterministic engine
       -> PASS / FAIL / REVIEW / NOT_APPLICABLE
       -> role-gated human review
       -> editable JSON / printable report and append-only audit events
  -> PostgreSQL inspection aggregates + storage metadata + audit events
  -> private object storage for package evidence
```

## Boundaries

- AI extracts visible facts; it does not decide legal compliance.
- Applicability is resolved before a rule is applied.
- FastAPI is the only authoritative rule engine. The browser never creates or changes a rule result.
- Missing declarations become `FAIL` only when the mandatory declaration panel is established as visible. Insufficient coverage becomes `REVIEW`.
- Poor image quality routes affected checks to `REVIEW`; it does not prove non-compliance.
- Exact legal font size and physical net quantity are not inferred from uncalibrated photographs.
- Every analysis freezes provider/model, prompt version, ruleset version, quality policy and deployment/audit provenance.
- Human review is mandatory, and reports explicitly state that the output is not a final legal or enforcement determination.

## Five-rule MVP

| ID | Check | Verification mode |
|---|---|---|
| LMPC-MVP-001 | MRP / retail sale price declaration | IMAGE_ASSISTED |
| LMPC-MVP-002 | Net quantity and unit declaration | IMAGE_ASSISTED |
| LMPC-MVP-003 | Responsible entity and address | IMAGE_ASSISTED |
| LMPC-MVP-004 | Applicable date declaration | IMAGE_ASSISTED |
| LMPC-MVP-005 | Placement and legibility | IMAGE_ASSISTED |

The backend preserves the legacy 0.65 candidate threshold, conflict routing, branch order, and overall precedence (`FAIL > REVIEW > PASS > NOT_APPLICABLE`).

## Service layout

- `apps/web`: Next.js App Router, TypeScript, responsive dashboard/capture/review/history/rules/admin surfaces.
- `apps/api`: FastAPI, Pydantic contracts, RBAC, audit, provider layer, evidence assurance, applicability and deterministic rules.
- `vercel.json`: one Vercel project with `web` and `api` Services; `/api/blob-upload` stays in Next.js and other `/api/*` traffic goes to FastAPI.

## Storage model

The operational MVP uses three durable PostgreSQL tables:

- `inspections`: versioned inspection aggregate containing context, quality, extraction, applicable checks, evidence links and review decisions.
- `storage_objects`: immutable object metadata and ownership.
- `audit_events`: append-only actor/action/target/reason/provenance records.

Mutations and their audit event are committed in one SQLAlchemy transaction. Package-image bytes never live in PostgreSQL or a Vercel Function filesystem.

## Authentication and RBAC

- `COMPLIANCE_ANALYST`: create, upload and analyze.
- `LEGAL_REVIEWER`: analyst actions plus reasoned rule dispositions.
- `ADMIN`: reviewer actions plus audit/admin access.
- `VIEWER`: read-only inspections and reports.

Demo bearer identities are accepted only when `AUTH_MODE=demo` and are rejected by configuration when `APP_ENV=production`. Production uses JWT issuer/audience/JWKS verification.
