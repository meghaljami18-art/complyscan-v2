from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from .config import Settings
from .models import AuditEvent, User

SENSITIVE_FRAGMENTS = ("password", "secret", "token", "authorization", "cookie", "api_key", "apikey", "image_bytes", "inline_data", "download_url")


def _redact(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _redact(item) for key, item in value.items() if not any(fragment in str(key).lower() for fragment in SENSITIVE_FRAGMENTS)}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def canonical_hash(value: Any | None) -> str | None:
    if value is None:
        return None
    encoded = json.dumps(_redact(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_audit_event(
    *,
    request_id: str,
    actor: User,
    action: str,
    target_type: str,
    target_id: str,
    settings: Settings,
    before: Any | None = None,
    after: Any | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    return AuditEvent(
        request_id=request_id,
        actor_subject=actor.subject,
        actor_role=actor.role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_hash=canonical_hash(before),
        after_hash=canonical_hash(after),
        deployment_sha=settings.vercel_git_commit_sha,
        ruleset_version=settings.ruleset_version,
        reason=reason,
        metadata=_redact(metadata or {}),
    )
