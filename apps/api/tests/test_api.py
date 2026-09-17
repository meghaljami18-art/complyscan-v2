from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.repository import InMemoryRepository, create_repository


ANALYST = {"Authorization": "Bearer demo:analyst@example.test:COMPLIANCE_ANALYST"}
REVIEWER = {"Authorization": "Bearer demo:reviewer@example.test:LEGAL_REVIEWER"}
VIEWER = {"Authorization": "Bearer demo:viewer@example.test:VIEWER"}
ADMIN = {"Authorization": "Bearer demo:admin@example.test:ADMIN"}


def client():
    settings = Settings(_env_file=None, app_env="development", auth_mode="demo", vision_provider="fixture", database_url="", object_allowed_hosts=(".blob.vercel-storage.com",))
    return TestClient(create_app(settings=settings, repository=InMemoryRepository()))


def inspection_payload(fixture="good"):
    return {
        "context": {"package_context": "RETAIL", "commodity_type": "Cosmetic", "date_required": "TRUE", "medical_device": "FALSE"},
        "quality": {"status": "GOOD", "score": 0.95, "policy_version": "QUALITY_BROWSER_V1", "reasons": []},
        "image_names": ["label.jpg"],
        "fixture_key": fixture,
    }


def test_health_is_public_and_explicit_about_ephemeral_storage_and_legal_guardrail():
    with client() as api:
        response = api.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["persistence"] == {"adapter": "memory_demo", "ephemeral": True}
        assert body["human_review_required"] is True
        assert body["final_legal_determination"] is False
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-request-id"]


def test_authentication_and_rbac_are_enforced():
    with client() as api:
        assert api.get("/api/inspections").status_code == 401
        assert api.post("/api/inspections", headers=VIEWER, json=inspection_payload()).status_code == 403
        assert api.post("/api/audit-events", headers=ANALYST, json={}).status_code == 405
        assert api.get("/api/audit-events", headers=ANALYST).status_code == 403
        assert api.get("/api/me", headers=VIEWER).json()["user"]["role"] == "VIEWER"


def test_full_fixture_inspection_review_report_and_audit_workflow():
    with client() as api:
        created = api.post("/api/inspections", headers=ANALYST, json=inspection_payload())
        assert created.status_code == 201, created.text
        inspection_id = created.json()["id"]

        analyzed = api.post(f"/api/inspections/{inspection_id}/analyze", headers=ANALYST, json={"provider": "fixture"})
        assert analyzed.status_code == 200, analyzed.text
        analyzed_body = analyzed.json()
        assert analyzed_body["assessment"]["overall_status"] == "PASS"
        assert len(analyzed_body["assessment"]["results"]) == 5
        assert analyzed_body["human_review_complete"] is False
        assert analyzed_body["status"] == "ANALYZED"

        analyst_review = api.post(f"/api/inspections/{inspection_id}/reviews", headers=ANALYST, json={"rule_id": "LMPC-MVP-001", "decision": "CONFIRMED", "reason": "Evidence verified."})
        assert analyst_review.status_code == 403

        for number in range(1, 6):
            reviewed = api.post(
                f"/api/inspections/{inspection_id}/reviews",
                headers=REVIEWER,
                json={"rule_id": f"LMPC-MVP-00{number}", "decision": "CONFIRMED", "reason": "Evidence reviewed against the original image."},
            )
            assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["human_review_complete"] is True
        assert reviewed.json()["status"] == "REVIEW_COMPLETE"

        report = api.get(f"/api/inspections/{inspection_id}/report.json", headers=VIEWER)
        assert report.status_code == 200
        assert report.json()["human_review_complete"] is True
        assert report.json()["final_legal_determination"] is False
        assert "final legal" in report.json()["notice"].lower()

        events = api.get("/api/audit-events", headers=ADMIN)
        assert events.status_code == 200
        assert events.json()["count"] == 7
        assert all("download_url" not in event.get("metadata", {}) for event in events.json()["events"])


def test_strict_validation_blocks_inline_secrets_and_unsafe_object_metadata():
    with client() as api:
        created = api.post("/api/inspections", headers=ANALYST, json={**inspection_payload(), "api_key": "secret"})
        assert created.status_code == 422
        unsafe = api.post(
            "/api/storage/objects",
            headers=ANALYST,
            json={"object_key": "x/y.jpg", "file_name": "y.jpg", "content_type": "image/jpeg", "size_bytes": 123, "download_url": "https://127.0.0.1/private"},
        )
        assert unsafe.status_code == 400


def test_registered_storage_object_can_back_an_inspection():
    with client() as api:
        registered = api.post(
            "/api/storage/objects",
            headers=ANALYST,
            json={"object_id": "object-1", "object_key": "x/y.jpg", "file_name": "y.jpg", "content_type": "image/jpeg", "size_bytes": 123, "download_url": "https://assets.blob.vercel-storage.com/y.jpg"},
        )
        assert registered.status_code == 201, registered.text
        created = api.post(
            "/api/inspections",
            headers=ANALYST,
            json={"context": {}, "quality": {}, "image_object_ids": ["object-1"]},
        )
        assert created.status_code == 201, created.text
        assert created.json()["images"][0]["object_id"] == "object-1"


def test_analyze_accepts_the_uploaded_inline_transport_and_rejects_count_drift():
    with client() as api:
        created = api.post("/api/inspections", headers=ANALYST, json=inspection_payload())
        inspection_id = created.json()["id"]
        image = {"name": "label.jpg", "mime_type": "image/jpeg", "data": "AAAA"}

        mismatch = api.post(
            f"/api/inspections/{inspection_id}/analyze",
            headers=ANALYST,
            json={"provider": "fixture", "images": [image, {**image, "name": "back.jpg"}]},
        )
        assert mismatch.status_code == 422, mismatch.text
        assert mismatch.json()["detail"]["code"] == "IMAGE_COUNT_MISMATCH"

        analyzed = api.post(
            f"/api/inspections/{inspection_id}/analyze",
            headers=ANALYST,
            json={"provider": "fixture", "images": [image]},
        )
        assert analyzed.status_code == 200, analyzed.text
        assert analyzed.json()["assessment"]["overall_status"] == "PASS"


def test_repository_uses_safe_memory_fallback_for_missing_or_malformed_url():
    assert create_repository("").kind == "memory_demo"
    assert create_repository("sqlite:///not-allowed.db", allow_memory_fallback=True).kind == "memory_demo"
