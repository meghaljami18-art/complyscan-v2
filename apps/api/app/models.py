from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Role(str, Enum):
    ADMIN = "ADMIN"
    LEGAL_REVIEWER = "LEGAL_REVIEWER"
    COMPLIANCE_ANALYST = "COMPLIANCE_ANALYST"
    VIEWER = "VIEWER"


class RuleStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    FUTURE = "FUTURE"


class TriState(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class PanelVisibility(str, Enum):
    YES = "YES"
    NO = "NO"
    UNCERTAIN = "UNCERTAIN"


class QualityStatus(str, Enum):
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


class FieldCandidate(StrictModel):
    value: str = Field(min_length=1, max_length=500)
    qualifier: str | None = Field(default=None, max_length=200)
    confidence: float = Field(ge=0, le=1)
    evidence: str = Field(default="", max_length=1500)
    image_index: int = Field(default=0, ge=0, le=5)
    method: Literal["AI_VISION", "OCR", "MANUAL", "PRE_EXTRACTED_FIXTURE"] = "AI_VISION"

    @model_validator(mode="after")
    def preserve_evidence(self) -> "FieldCandidate":
        if not self.evidence:
            self.evidence = self.value
        return self


class ProductExtraction(StrictModel):
    name: str | None = Field(default=None, max_length=300)
    brand: str | None = Field(default=None, max_length=300)
    commodity_type: str | None = Field(default=None, max_length=300)
    medical_device: TriState = TriState.UNKNOWN


class Coverage(StrictModel):
    package_sides_visible: list[str] = Field(default_factory=list, max_length=6)
    mandatory_declaration_panel_visible: PanelVisibility = PanelVisibility.UNCERTAIN
    coverage_notes: list[str] = Field(default_factory=list, max_length=20)


class ExtractionFields(StrictModel):
    mrp: list[FieldCandidate] = Field(default_factory=list, max_length=20)
    net_quantity: list[FieldCandidate] = Field(default_factory=list, max_length=20)
    responsible_entity: list[FieldCandidate] = Field(default_factory=list, max_length=20)
    address: list[FieldCandidate] = Field(default_factory=list, max_length=20)
    date: list[FieldCandidate] = Field(default_factory=list, max_length=20)
    consumer_care: list[FieldCandidate] = Field(default_factory=list, max_length=20)


class VisualExtraction(StrictModel):
    overall_legibility: Literal["CLEAR", "PARTIAL", "POOR", "UNCERTAIN"] = "UNCERTAIN"
    contrast: Literal["ADEQUATE", "LOW", "UNCERTAIN"] = "UNCERTAIN"
    principal_display_panel_visible: PanelVisibility = PanelVisibility.UNCERTAIN
    exact_font_size_verifiable: Literal[False] = False
    notes: list[str] = Field(default_factory=list, max_length=20)


class RawImageText(StrictModel):
    image_index: int = Field(ge=0, le=5)
    text: str = Field(default="", max_length=10000)


class Extraction(StrictModel):
    product: ProductExtraction = Field(default_factory=ProductExtraction)
    coverage: Coverage = Field(default_factory=Coverage)
    fields: ExtractionFields = Field(default_factory=ExtractionFields)
    visual: VisualExtraction = Field(default_factory=VisualExtraction)
    raw_text_by_image: list[RawImageText] = Field(default_factory=list, max_length=6)


class InspectionContext(StrictModel):
    package_context: Literal["RETAIL", "ECOMMERCE", "WHOLESALE", "EXPORT"] = "RETAIL"
    commodity_type: str = Field(default="UNKNOWN", min_length=1, max_length=300)
    date_required: TriState = TriState.UNKNOWN
    medical_device: TriState = TriState.UNKNOWN


class NormalizedContext(StrictModel):
    package_context: str
    commodity_type: str
    date_required: str
    medical_device: str


class QualityReason(StrictModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)


class QualitySummary(StrictModel):
    status: QualityStatus = QualityStatus.FAIR
    score: float = Field(default=0.5, ge=0, le=1)
    policy_version: str = Field(default="QUALITY_BROWSER_V1", min_length=1, max_length=100)
    reasons: list[QualityReason] = Field(default_factory=list, max_length=20)


class ImageReference(StrictModel):
    object_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=128)
    object_key: str = Field(min_length=1, max_length=500)
    file_name: str = Field(min_length=1, max_length=255)
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(ge=0, le=15_000_000)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    download_url: HttpUrl | None = None
    fixture_key: Literal["good", "conflicting_mrp", "front_only", "missing_quantity", "poor_legibility"] | None = None


class StorageObjectRegister(StrictModel):
    object_id: str | None = Field(default=None, min_length=1, max_length=128)
    object_key: str = Field(min_length=1, max_length=500)
    file_name: str = Field(min_length=1, max_length=255)
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(ge=1, le=15_000_000)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    download_url: HttpUrl


class UploadIntentInput(StrictModel):
    file_name: str = Field(min_length=1, max_length=255)
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(ge=1, le=15_000_000)


class StorageObjectMetadata(ImageReference):
    uploaded_by: str
    uploaded_at: datetime = Field(default_factory=utc_now)


class InspectionCreate(StrictModel):
    context: InspectionContext = Field(default_factory=InspectionContext)
    quality: QualitySummary = Field(default_factory=QualitySummary)
    image_object_ids: list[str] = Field(default_factory=list, max_length=6)
    image_names: list[str] = Field(default_factory=list, max_length=6)
    fixture_key: Literal["good", "conflicting_mrp", "front_only", "missing_quantity", "poor_legibility"] | None = None

    @model_validator(mode="after")
    def require_images(self) -> "InspectionCreate":
        if not self.image_object_ids and not self.image_names:
            raise ValueError("at least one image_object_id or image_name is required")
        if self.image_object_ids and self.image_names:
            raise ValueError("use image_object_ids or image_names, not both")
        if self.fixture_key is not None and not self.image_names:
            raise ValueError("fixture_key may only be used with image_names")
        return self


class InlineImageInput(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    data: str = Field(min_length=4, max_length=5_000_000, pattern=r"^[A-Za-z0-9+/]*={0,2}$")
    quality: QualitySummary | None = None


class AnalyzeInput(StrictModel):
    provider: Literal["configured", "fixture", "gemini"] | None = None
    requested_provider: Literal["configured", "fixture"] = "configured"
    fixture_key: Literal["good", "conflicting_mrp", "front_only", "missing_quantity", "poor_legibility"] | None = None
    images: list[InlineImageInput] = Field(default_factory=list, max_length=6)
    image_urls: list[HttpUrl] = Field(default_factory=list, max_length=6)
    context: InspectionContext | None = None

    @model_validator(mode="after")
    def one_image_transport(self) -> "AnalyzeInput":
        if self.images and self.image_urls:
            raise ValueError("use inline images or image_urls, not both")
        if self.provider and self.provider != "configured" and self.requested_provider != "configured" and self.provider != self.requested_provider:
            raise ValueError("provider fields conflict")
        return self


class EvidenceItem(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    excerpt: str = Field(default="", max_length=1500)
    value: str | None = Field(default=None, max_length=500)
    confidence: float | None = Field(default=None, ge=0, le=1)
    image_index: int | None = Field(default=None, ge=0, le=5)
    image_name: str = Field(default="Uploaded images", max_length=1000)
    method: str = Field(default="AI_VISION", max_length=100)


class RuleResult(StrictModel):
    rule_id: str
    title: str
    source: str
    verification_mode: str
    status: RuleStatus
    ui_label: str
    legal_output: str
    explanation: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    next_action: str = ""


class EvidenceAssurance(StrictModel):
    level: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]
    score: float = Field(ge=0, le=1)
    sufficient_for_automated_pass: bool
    reasons: list[str]
    low_confidence_fields: list[str]
    conflicting_fields: list[str]


class ApplicabilityDecision(StrictModel):
    rule_id: str
    selected: bool
    outcome: Literal["APPLICABLE", "NOT_APPLICABLE", "REVIEW"]
    reason: str


class Assessment(StrictModel):
    ruleset_id: str
    ruleset_version: str
    overall_status: RuleStatus
    overall_label: str
    results: list[RuleResult] = Field(min_length=5, max_length=5)
    counts: dict[str, int]
    context: NormalizedContext
    evidence_assurance: EvidenceAssurance
    applicability: list[ApplicabilityDecision] = Field(min_length=5, max_length=5)
    guardrails: list[str]
    requires_human_review: Literal[True] = True
    final_legal_determination: Literal[False] = False


class ReviewDecisionInput(StrictModel):
    rule_id: str = Field(pattern=r"^LMPC-MVP-00[1-5]$")
    decision: Literal["CONFIRMED", "DISMISSED", "MORE_EVIDENCE", "ESCALATED"]
    reason: str = Field(min_length=3, max_length=1000)


class ReviewDecisionRecord(ReviewDecisionInput):
    reviewer_subject: str
    reviewer_role: Role
    decided_at: datetime = Field(default_factory=utc_now)


class InspectionRecord(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: Literal["DRAFT", "ANALYZED", "IN_REVIEW", "REVIEW_COMPLETE"] = "DRAFT"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    created_by: str
    context: InspectionContext
    images: list[ImageReference] = Field(min_length=1, max_length=6)
    quality: QualitySummary
    extraction: Extraction | None = None
    assessment: Assessment | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    review_decisions: dict[str, ReviewDecisionRecord] = Field(default_factory=dict)
    human_review_complete: bool = False


class User(StrictModel):
    subject: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    name: str = Field(min_length=1, max_length=255)
    role: Role


class AuditEvent(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str = Field(min_length=1, max_length=128)
    actor_subject: str
    actor_role: Role
    action: str
    target_type: str
    target_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    before_hash: str | None = None
    after_hash: str | None = None
    deployment_sha: str | None = None
    ruleset_version: str
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
