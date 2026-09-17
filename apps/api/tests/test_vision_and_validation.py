import json

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.models import AnalyzeInput, InspectionCreate
from app.storage import _allowed_url
from app.vision import build_gemini_payload, fixture_extraction


def walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_keys(item)


def test_gemini_payload_is_prompt_only_json_contract_without_schema_field():
    payload = build_gemini_payload([("image/jpeg", "YWJj")])
    keys = set(walk_keys(payload))
    assert "response" + "Schema" not in keys
    assert "response_schema" not in keys
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "api" + "Key" not in json.dumps(payload)


def test_fixture_provider_is_deterministic():
    first = fixture_extraction("good").model_dump(mode="json")
    second = fixture_extraction("good").model_dump(mode="json")
    assert first == second
    assert first["fields"]["mrp"][0]["method"] == "PRE_EXTRACTED_FIXTURE"


def test_analyze_contract_rejects_client_supplied_api_key():
    with pytest.raises(ValidationError):
        AnalyzeInput.model_validate({"provider": "gemini", "api_key": "must-never-be-accepted"})


def test_strict_inspection_contract_requires_images_and_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        InspectionCreate.model_validate({"context": {}, "quality": {}, "unknown": True})
    with pytest.raises(ValidationError):
        InspectionCreate.model_validate({"context": {}, "quality": {}})


def test_object_url_policy_rejects_ssrf_and_allows_exact_suffix():
    settings = Settings(_env_file=None, object_allowed_hosts=(".blob.vercel-storage.com",))
    assert _allowed_url("https://assets.blob.vercel-storage.com/file.jpg", settings)
    assert not _allowed_url("https://assets.blob.vercel-storage.com.evil.example/file.jpg", settings)
    assert not _allowed_url("http://assets.blob.vercel-storage.com/file.jpg", settings)
    assert not _allowed_url("https://127.0.0.1/file.jpg", settings)
