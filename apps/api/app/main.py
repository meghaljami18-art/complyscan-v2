from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .audit import make_audit_event
from .auth import authenticate_request, require_roles
from .config import Settings, get_settings
from .models import (
    AnalyzeInput,
    ImageReference,
    InspectionCreate,
    InspectionRecord,
    ReviewDecisionInput,
    ReviewDecisionRecord,
    Role,
    StorageObjectRegister,
    UploadIntentInput,
    User,
)
from .repository import Repository, create_repository
from .rule_engine import RULES, evaluate_compliance
from .storage import build_upload_intent, fixture_image, register_metadata
from .vision import VisionProviderError, get_vision_provider

LOGGER = logging.getLogger("complyscan.api")
ALL_ROLES = {Role.ADMIN, Role.LEGAL_REVIEWER, Role.COMPLIANCE_ANALYST, Role.VIEWER}
WRITERS = {Role.ADMIN, Role.LEGAL_REVIEWER, Role.COMPLIANCE_ANALYST}
REVIEWERS = {Role.ADMIN, Role.LEGAL_REVIEWER}
LEGAL_NOTICE = "COMPLYSCAN provides evidence-backed screening support. It does not make a final legal, enforcement, or adjudicatory determination."


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "INSPECTION_NOT_FOUND", "message": "Inspection was not found."})


def _report(record: InspectionRecord) -> dict[str, Any]:
    return {
        "schema_version": "COMPLYSCAN_REPORT_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inspection_id": record.id,
        "inspection_status": record.status,
        "screening_status": record.assessment.overall_status if record.assessment else None,
        "human_review_complete": record.human_review_complete,
        "final_legal_determination": False,
        "notice": LEGAL_NOTICE,
        "context": record.context.model_dump(mode="json"),
        "quality": record.quality.model_dump(mode="json"),
        "images": [{"object_id": item.object_id, "file_name": item.file_name, "content_type": item.content_type} for item in record.images],
        "extraction": record.extraction.model_dump(mode="json") if record.extraction else None,
        "assessment": record.assessment.model_dump(mode="json") if record.assessment else None,
        "review_decisions": {key: value.model_dump(mode="json") for key, value in record.review_decisions.items()},
        "provenance": {
            "provider": record.provider,
            "model": record.model,
            "prompt_version": record.prompt_version,
            "ruleset_version": record.assessment.ruleset_version if record.assessment else None,
        },
    }


def create_app(*, settings: Settings | None = None, repository: Repository | None = None) -> FastAPI:
    cfg = settings or get_settings()
    repo = repository or create_repository(cfg.database_url, cfg.allow_memory_fallback)
    app = FastAPI(
        title="COMPLYSCAN API",
        version="1.0.0",
        description="Evidence-first packaged-commodity label screening. Human review is mandatory; automated output is never a final legal determination.",
    )
    app.state.settings = cfg
    app.state.repository = repo
    app.add_middleware(CORSMiddleware, allow_origins=list(cfg.cors_origins), allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"])

    @app.middleware("http")
    async def request_controls(request: Request, call_next: Callable[..., Any]):
        request.state.request_id = request.headers.get("x-request-id", str(uuid4()))[:128]
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > cfg.max_request_bytes:
            return JSONResponse(status_code=413, content={"error": {"code": "REQUEST_TOO_LARGE", "message": "Request exceeds the metadata API limit."}, "request_id": _request_id(request)})
        response = await call_next(request)
        response.headers["X-Request-ID"] = _request_id(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [{"location": ".".join(str(part) for part in item["loc"]), "message": item["msg"], "type": item["type"]} for item in exc.errors()]
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "Request validation failed.", "details": errors}, "request_id": _request_id(request)})

    @app.exception_handler(VisionProviderError)
    async def vision_error(request: Request, exc: VisionProviderError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": str(exc), "retryable": exc.retryable}, "request_id": _request_id(request)})

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        LOGGER.exception("Unhandled API error request_id=%s", _request_id(request), exc_info=exc)
        return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "Unexpected server error."}, "request_id": _request_id(request)})

    def current_user(request: Request) -> User:
        return authenticate_request(request, cfg)

    def read_user(user: User = Depends(current_user)) -> User:
        return require_roles(user, ALL_ROLES)

    def write_user(user: User = Depends(current_user)) -> User:
        return require_roles(user, WRITERS)

    def review_user(user: User = Depends(current_user)) -> User:
        return require_roles(user, REVIEWERS)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": repo.healthcheck(),
            "service": cfg.service_name,
            "environment": cfg.app_env,
            "time": datetime.now(timezone.utc).isoformat(),
            "persistence": {"adapter": repo.kind, "ephemeral": repo.ephemeral},
            "vision": {"provider": cfg.vision_provider, "gemini_configured": bool(cfg.gemini_api_key), "model": cfg.gemini_model},
            "storage": {"provider": "vercel_blob" if cfg.blob_read_write_token else "inline_preview", "direct_upload": bool(cfg.blob_read_write_token)},
            "auth_mode": cfg.auth_mode,
            "ruleset": {"id": cfg.ruleset_id, "version": cfg.ruleset_version, "rules": len(RULES)},
            "human_review_required": True,
            "final_legal_determination": False,
            "notice": LEGAL_NOTICE,
        }

    @app.get("/api/me")
    def me(user: User = Depends(read_user)) -> dict[str, Any]:
        return {"authenticated": True, "user": user}

    @app.get("/api/rules")
    def rules(user: User = Depends(read_user)) -> dict[str, Any]:
        return {"ruleset_id": cfg.ruleset_id, "ruleset_version": cfg.ruleset_version, "rules": [rule.__dict__ for rule in RULES], "notice": LEGAL_NOTICE}

    @app.post("/api/storage/upload-intents", status_code=201)
    def upload_intent(payload: UploadIntentInput, user: User = Depends(write_user)) -> dict[str, Any]:
        return build_upload_intent(payload, user, cfg)

    @app.post("/api/storage/objects", status_code=201)
    def save_storage_object(payload: StorageObjectRegister, request: Request, user: User = Depends(write_user)):
        metadata = register_metadata(payload, user, cfg)
        event = make_audit_event(request_id=_request_id(request), actor=user, action="STORAGE_OBJECT_REGISTERED", target_type="storage_object", target_id=metadata.object_id, settings=cfg, after=metadata, metadata={"file_name": metadata.file_name, "content_type": metadata.content_type, "size_bytes": metadata.size_bytes})
        try:
            return repo.save_storage_object(metadata, event)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "OBJECT_ALREADY_EXISTS", "message": str(exc)}) from exc

    @app.get("/api/inspections")
    def list_inspections(user: User = Depends(read_user), limit: int = Query(default=100, ge=1, le=100)) -> dict[str, Any]:
        records = repo.list_inspections(limit)
        return {"inspections": records, "count": len(records), "ephemeral": repo.ephemeral, "notice": LEGAL_NOTICE}

    @app.post("/api/inspections", status_code=201)
    def create_inspection(payload: InspectionCreate, request: Request, user: User = Depends(write_user)):
        if payload.image_object_ids:
            stored = repo.get_storage_objects(payload.image_object_ids)
            if len(stored) != len(payload.image_object_ids):
                raise HTTPException(status_code=422, detail={"code": "UNKNOWN_IMAGE_OBJECT", "message": "One or more image object identifiers are not registered."})
            if user.role != Role.ADMIN and any(item.uploaded_by != user.subject for item in stored):
                raise HTTPException(status_code=403, detail={"code": "OBJECT_ACCESS_DENIED", "message": "One or more image objects belong to another user."})
            images = [item.model_copy() for item in stored]
        else:
            images = [fixture_image(name, payload.fixture_key) for name in payload.image_names]
        record = InspectionRecord(created_by=user.subject, context=payload.context, images=images, quality=payload.quality)
        event = make_audit_event(request_id=_request_id(request), actor=user, action="INSPECTION_CREATED", target_type="inspection", target_id=record.id, settings=cfg, after=record, metadata={"image_count": len(images)})
        return repo.create_inspection(record, event)

    @app.get("/api/inspections/{inspection_id}")
    def get_inspection(inspection_id: str, user: User = Depends(read_user)):
        record = repo.get_inspection(inspection_id)
        if record is None:
            raise _not_found()
        return record

    @app.post("/api/inspections/{inspection_id}/analyze")
    async def analyze_inspection(inspection_id: str, request: Request, user: User = Depends(write_user), payload: AnalyzeInput = Body(default_factory=AnalyzeInput)):
        before = repo.get_inspection(inspection_id)
        if before is None:
            raise _not_found()
        if payload.context is not None and payload.context != before.context:
            raise HTTPException(status_code=409, detail={"code": "CONTEXT_MISMATCH", "message": "Analysis context must match the saved inspection draft."})

        selected_provider = payload.provider or payload.requested_provider
        provider = get_vision_provider(cfg, selected_provider)
        analysis_images = before.images
        if payload.image_urls:
            if len(payload.image_urls) != len(before.images):
                raise HTTPException(status_code=422, detail={"code": "IMAGE_COUNT_MISMATCH", "message": "Object-storage URLs must match the draft image count."})
            analysis_images = [
                ImageReference(
                    object_key=f"direct/{inspection_id}/{index}",
                    file_name=before.images[index].file_name,
                    content_type=before.images[index].content_type,
                    size_bytes=0,
                    download_url=url,
                )
                for index, url in enumerate(payload.image_urls)
            ]
        elif payload.images and len(payload.images) != len(before.images):
            raise HTTPException(status_code=422, detail={"code": "IMAGE_COUNT_MISMATCH", "message": "Inline images must match the draft image count."})

        result = await provider.analyze(analysis_images, payload.fixture_key, payload.images or None)
        assessment = evaluate_compliance(result.extraction, before.context, [item.file_name for item in analysis_images], before.quality, ruleset_id=cfg.ruleset_id, ruleset_version=cfg.ruleset_version)
        updated = before.model_copy(deep=True)
        updated.images = analysis_images
        updated.extraction = result.extraction
        updated.assessment = assessment
        updated.provider = result.provider
        updated.model = result.model
        updated.prompt_version = result.prompt_version
        updated.status = "ANALYZED"
        updated.updated_at = datetime.now(timezone.utc)
        updated.review_decisions = {}
        updated.human_review_complete = False
        event = make_audit_event(request_id=_request_id(request), actor=user, action="INSPECTION_ANALYZED", target_type="inspection", target_id=updated.id, settings=cfg, before=before, after=updated, metadata={"provider": result.provider, "model": result.model, "overall_status": assessment.overall_status.value, "transport": "object_storage" if payload.image_urls else "inline" if payload.images else "fixture"})
        return repo.save_inspection(updated, event)

    @app.post("/api/inspections/{inspection_id}/reviews")
    def review_inspection(inspection_id: str, payload: ReviewDecisionInput, request: Request, user: User = Depends(review_user)):
        before = repo.get_inspection(inspection_id)
        if before is None:
            raise _not_found()
        if before.assessment is None:
            raise HTTPException(status_code=409, detail={"code": "ANALYSIS_REQUIRED", "message": "Analyze the inspection before recording a human disposition."})
        result_by_id = {item.rule_id: item for item in before.assessment.results}
        if payload.rule_id not in result_by_id:
            raise HTTPException(status_code=422, detail={"code": "UNKNOWN_RULE", "message": "Rule is not part of this assessment."})
        if result_by_id[payload.rule_id].status.value == "NOT_APPLICABLE":
            raise HTTPException(status_code=409, detail={"code": "RULE_NOT_APPLICABLE", "message": "A not-applicable rule does not accept a disposition."})
        updated = before.model_copy(deep=True)
        updated.review_decisions[payload.rule_id] = ReviewDecisionRecord(**payload.model_dump(), reviewer_subject=user.subject, reviewer_role=user.role)
        applicable = {item.rule_id for item in updated.assessment.results if item.status.value != "NOT_APPLICABLE"}
        updated.human_review_complete = applicable.issubset(updated.review_decisions.keys())
        updated.status = "REVIEW_COMPLETE" if updated.human_review_complete else "IN_REVIEW"
        updated.updated_at = datetime.now(timezone.utc)
        event = make_audit_event(request_id=_request_id(request), actor=user, action="RULE_REVIEW_RECORDED", target_type="inspection", target_id=updated.id, settings=cfg, before=before, after=updated, reason=payload.reason, metadata={"rule_id": payload.rule_id, "decision": payload.decision, "human_review_complete": updated.human_review_complete})
        return repo.save_inspection(updated, event)

    @app.get("/api/inspections/{inspection_id}/report")
    @app.get("/api/inspections/{inspection_id}/report.json")
    def inspection_report(inspection_id: str, user: User = Depends(read_user)):
        record = repo.get_inspection(inspection_id)
        if record is None:
            raise _not_found()
        return _report(record)

    @app.get("/api/audit-events")
    def audit_events(user: User = Depends(review_user), limit: int = Query(default=200, ge=1, le=500)) -> dict[str, Any]:
        events = repo.list_audit_events(limit)
        return {"events": events, "count": len(events)}

    return app


app = create_app()
