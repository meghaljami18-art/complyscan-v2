from __future__ import annotations

import re
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import HTTPException

from .config import Settings
from .models import ImageReference, StorageObjectMetadata, StorageObjectRegister, UploadIntentInput, User


def _allowed_url(url: str, settings: Settings) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in {None, 443}:
        return False
    hostname = parsed.hostname.lower().rstrip(".")
    for configured in settings.object_allowed_hosts:
        suffix = configured.lower().strip().rstrip(".")
        bare = suffix.lstrip(".")
        if hostname == bare or (suffix.startswith(".") and hostname.endswith(suffix)):
            return True
    return False


def build_upload_intent(payload: UploadIntentInput, actor: User, settings: Settings) -> dict[str, object]:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", payload.file_name).strip("._") or "image"
    object_id = str(uuid4())
    object_key = f"complyscan/{actor.subject[:48].replace('@', '_')}/{object_id}/{safe_name}"
    return {
        "object_id": object_id,
        "object_key": object_key,
        "provider": "vercel_blob" if settings.blob_read_write_token else "external_object_storage",
        "upload_strategy": "CLIENT_DIRECT",
        "proxy_upload_supported": False,
        "registration_endpoint": "/api/storage/objects",
        "requirements": {
            "content_type": payload.content_type,
            "size_bytes": payload.size_bytes,
            "allowed_https_hosts": list(settings.object_allowed_hosts),
        },
        "notice": "Upload directly with the configured object-storage client, then register immutable metadata. Image bytes are never accepted by this API.",
    }


def register_metadata(payload: StorageObjectRegister, actor: User, settings: Settings, object_id: str | None = None) -> StorageObjectMetadata:
    if not _allowed_url(str(payload.download_url), settings):
        raise HTTPException(status_code=400, detail={"code": "UNSAFE_OBJECT_URL", "message": "download_url must use HTTPS on an allowed object-storage host."})
    return StorageObjectMetadata(
        object_id=object_id or payload.object_id or str(uuid4()),
        object_key=payload.object_key,
        file_name=payload.file_name,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        sha256=payload.sha256,
        download_url=payload.download_url,
        uploaded_by=actor.subject,
    )


def fixture_image(name: str, fixture_key: str | None) -> ImageReference:
    return ImageReference(object_key=f"fixture/{name}", file_name=name, content_type="image/jpeg", size_bytes=0, fixture_key=fixture_key or "good")
