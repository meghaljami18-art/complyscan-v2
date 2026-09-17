from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .assurance import assess_evidence, decide_applicability
from .models import (
    Assessment,
    EvidenceItem,
    Extraction,
    FieldCandidate,
    InspectionContext,
    NormalizedContext,
    QualityStatus,
    QualitySummary,
    RuleResult,
    RuleStatus,
)

CONFIDENCE_THRESHOLD = 0.65


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    title: str
    source: str
    verification_mode: str
    purpose: str


RULES = (
    RuleDefinition("LMPC-MVP-001", "MRP / Retail Sale Price", "Rule 6 + applicable sticker provisions", "IMAGE_ONLY / IMAGE_ASSISTED", "Verify required MRP presence and readable form."),
    RuleDefinition("LMPC-MVP-002", "Net Quantity + Unit", "Rules 11–13 + Fourth Schedule where applicable", "IMAGE_ONLY / IMAGE_ASSISTED", "Verify declared quantity and unit/basis; not physical accuracy."),
    RuleDefinition("LMPC-MVP-003", "Manufacturer / Packer / Importer", "Rule 6 + Rule 10", "IMAGE_ONLY / IMAGE_ASSISTED / EXTERNAL_DATA", "Verify responsible entity identity and readable address."),
    RuleDefinition("LMPC-MVP-004", "Applicable Date Declaration", "Rule 6 + commodity applicability", "IMAGE_ONLY / IMAGE_ASSISTED", "Verify the selected date only when context establishes it is required."),
    RuleDefinition("LMPC-MVP-005", "Placement / Legibility", "Rules 7–9; MDR route where applicable", "IMAGE_ASSISTED", "Screen selected observable readability predicates; exact font height is not claimed."),
)
RULE_BY_ID = {rule.id: rule for rule in RULES}
STATUS_MAP = {
    RuleStatus.PASS: ("COMPLIANT", "Passed"),
    RuleStatus.FAIL: ("NON_COMPLIANT", "Non-compliant"),
    RuleStatus.REVIEW: ("REVIEW", "Needs review"),
    RuleStatus.NOT_APPLICABLE: ("NOT_APPLICABLE", "Not applicable"),
    RuleStatus.FUTURE: ("FUTURE", "Future rule"),
}


def _text(value: object | None) -> str:
    return str(value if value is not None else "").strip()


def _field(extraction: Extraction, key: str) -> list[FieldCandidate]:
    return list(getattr(extraction.fields, key))


def _unique_values(candidates: list[FieldCandidate]) -> set[str]:
    return {_text(item.value).lower() for item in candidates if _text(item.value)}


def _best(candidates: list[FieldCandidate]) -> FieldCandidate | None:
    return sorted(candidates, key=lambda item: item.confidence, reverse=True)[0] if candidates else None


def _panel_visible(extraction: Extraction) -> bool:
    return extraction.coverage.mandatory_declaration_panel_visible.value == "YES"


def _enough(candidate: FieldCandidate | None, threshold: float = CONFIDENCE_THRESHOLD) -> bool:
    return bool(candidate and _text(candidate.value) and candidate.confidence >= threshold)


def _evidence_of(candidate: FieldCandidate | None, image_names: list[str]) -> EvidenceItem | None:
    if candidate is None:
        return None
    image_index = candidate.image_index
    return EvidenceItem(
        excerpt=_text(candidate.evidence or candidate.value),
        value=_text(candidate.value),
        confidence=candidate.confidence,
        image_index=image_index,
        image_name=image_names[image_index] if image_index < len(image_names) else f"Image {image_index + 1}",
        method=candidate.method,
    )


def _result(rule_id: str, status: RuleStatus, explanation: str, evidence: list[EvidenceItem | None] | None = None, next_action: str = "") -> RuleResult:
    rule = RULE_BY_ID[rule_id]
    legal, label = STATUS_MAP[status]
    return RuleResult(
        rule_id=rule_id,
        title=rule.title,
        source=rule.source,
        verification_mode=rule.verification_mode,
        status=status,
        ui_label=label,
        legal_output=legal,
        explanation=explanation,
        evidence=[item for item in (evidence or []) if item is not None],
        next_action=next_action,
    )


def _evaluate_mrp(extraction: Extraction, context: NormalizedContext, image_names: list[str]) -> RuleResult:
    candidates = _field(extraction, "mrp")
    evidences = [_evidence_of(item, image_names) for item in candidates]
    if context.package_context == "EXPORT":
        return _result("LMPC-MVP-001", RuleStatus.NOT_APPLICABLE, "Export context selected; the prototype does not apply the retail MRP predicate.", evidences)
    if context.medical_device == "TRUE":
        return _result("LMPC-MVP-001", RuleStatus.REVIEW, "Medical-device routing can change the applicable declaration regime.", evidences, "Route to a reviewer with the applicable MDR evidence.")
    if len(_unique_values(candidates)) > 1:
        return _result("LMPC-MVP-001", RuleStatus.REVIEW, "Multiple distinct MRP candidates were extracted; the engine will not choose one automatically.", evidences, "Confirm the operative MRP and any sticker scenario.")
    candidate = _best(candidates)
    if _enough(candidate):
        return _result("LMPC-MVP-001", RuleStatus.PASS, f"A readable MRP candidate was found: {candidate.value}.", evidences, "Human reviewer should confirm the evidence before finalization.")
    if _panel_visible(extraction):
        return _result("LMPC-MVP-001", RuleStatus.FAIL, "The declaration panel appears visible, but no readable MRP was extracted.", evidences, "Confirm absence on the original image or request another view.")
    return _result("LMPC-MVP-001", RuleStatus.REVIEW, "The available images do not reliably show the mandatory-declaration panel.", evidences, "Capture the back/side panel containing statutory declarations.")


_QUANTITY_WITH_UNIT = re.compile(r"(?:\d|one|two)\s*(?:kg|g|gm|mg|l|ml|cl|m|cm|mm|sq\.?\s*(?:m|cm)|units?|pieces?|pcs?|nos?\.?|n)\b", re.IGNORECASE)


def _evaluate_quantity(extraction: Extraction, context: NormalizedContext, image_names: list[str]) -> RuleResult:
    candidate = _best(_field(extraction, "net_quantity"))
    evidence = [_evidence_of(candidate, image_names)]
    if context.package_context == "EXPORT":
        return _result("LMPC-MVP-002", RuleStatus.NOT_APPLICABLE, "Export context selected for this prototype route.", evidence)
    if _enough(candidate):
        if _QUANTITY_WITH_UNIT.search(_text(candidate.value)):
            return _result("LMPC-MVP-002", RuleStatus.PASS, f"A quantity with unit was found: {candidate.value}. Physical quantity accuracy is not assessed from the image.", evidence)
        return _result("LMPC-MVP-002", RuleStatus.REVIEW, f"A quantity candidate was found ({candidate.value}), but its permitted unit/basis is ambiguous.", evidence, "Confirm the unit and commodity-specific Schedule route.")
    if _panel_visible(extraction):
        return _result("LMPC-MVP-002", RuleStatus.FAIL, "The declaration panel appears visible, but no readable net quantity with unit was extracted.", evidence, "Confirm on the original label; physical measurement remains a separate inspection.")
    return _result("LMPC-MVP-002", RuleStatus.REVIEW, "Image coverage is insufficient to determine whether the quantity declaration is present.", evidence, "Capture the declaration panel.")


def _evaluate_identity(extraction: Extraction, context: NormalizedContext, image_names: list[str]) -> RuleResult:
    entity = _best(_field(extraction, "responsible_entity"))
    address = _best(_field(extraction, "address"))
    evidence = [_evidence_of(entity, image_names), _evidence_of(address, image_names)]
    if context.medical_device == "TRUE":
        return _result("LMPC-MVP-003", RuleStatus.REVIEW, "Medical-device status requires a priority route before applying the general identity predicate.", evidence, "Confirm the MDR declaration route.")
    if _enough(entity) and _enough(address):
        role = _text(entity.qualifier)
        return _result("LMPC-MVP-003", RuleStatus.PASS, f"A responsible entity{f' ({role})' if role else ''} and address were extracted.", evidence, "Confirm the declared legal role; brand ownership is not inferred.")
    if _panel_visible(extraction):
        missing = "responsible entity" if not _enough(entity) else "complete address"
        return _result("LMPC-MVP-003", RuleStatus.FAIL, f"The declaration panel appears visible, but the {missing} was not reliably extracted.", evidence, "Review the original label and any applicable exception.")
    return _result("LMPC-MVP-003", RuleStatus.REVIEW, "The available views do not establish the responsible entity and complete address.", evidence, "Capture the manufacturer/packer/importer panel.")


def _evaluate_date(extraction: Extraction, context: NormalizedContext, image_names: list[str]) -> RuleResult:
    candidate = _best(_field(extraction, "date"))
    evidence = [_evidence_of(candidate, image_names)]
    if context.date_required == "FALSE":
        return _result("LMPC-MVP-004", RuleStatus.NOT_APPLICABLE, "The user-selected commodity/context route does not require this date predicate.", evidence)
    if context.date_required != "TRUE":
        return _result("LMPC-MVP-004", RuleStatus.REVIEW, "Date applicability is unresolved for the selected commodity/context.", evidence, "Confirm the commodity-specific or special-law route.")
    if _enough(candidate):
        qualifier = f" ({candidate.qualifier})" if candidate.qualifier else ""
        return _result("LMPC-MVP-004", RuleStatus.PASS, f"An applicable date declaration was found: {candidate.value}{qualifier}.", evidence)
    if _panel_visible(extraction):
        return _result("LMPC-MVP-004", RuleStatus.FAIL, "The selected context requires a date declaration, but none was reliably extracted from the visible panel.", evidence, "Confirm the requirement and inspect the original label.")
    return _result("LMPC-MVP-004", RuleStatus.REVIEW, "The relevant date panel is not sufficiently visible.", evidence, "Capture the batch/date panel.")


def _evaluate_visual(extraction: Extraction, context: NormalizedContext, image_names: list[str], quality_status: QualityStatus) -> RuleResult:
    visual = extraction.visual
    image_evidence = [EvidenceItem(
        excerpt=" ".join(visual.notes) or f"Legibility: {visual.overall_legibility}",
        value=visual.overall_legibility,
        confidence=None,
        image_index=None,
        image_name=", ".join(image_names) or "Uploaded images",
        method="AI_VISION + CANVAS_QUALITY_GATE",
    )]
    if context.medical_device == "TRUE":
        return _result("LMPC-MVP-005", RuleStatus.REVIEW, "Medical-device status is explicitly true, so the MDR visual route must be checked.", image_evidence, "Confirm device status and route to the applicable visual requirements.")
    if quality_status == QualityStatus.POOR:
        return _result("LMPC-MVP-005", RuleStatus.REVIEW, "The client-side quality gate found insufficient image quality for a reliable visual predicate.", image_evidence, "Retake the image in better light and focus.")
    if visual.overall_legibility == "CLEAR" and visual.contrast == "ADEQUATE" and visual.principal_display_panel_visible.value != "NO":
        return _result("LMPC-MVP-005", RuleStatus.PASS, "The selected observable legibility and contrast predicate is supported. Exact legal font height is not claimed from an uncalibrated photograph.", image_evidence)
    if visual.overall_legibility == "POOR" and _panel_visible(extraction) and quality_status == QualityStatus.GOOD:
        return _result("LMPC-MVP-005", RuleStatus.FAIL, "The image is usable, but declaration text appears poorly legible.", image_evidence, "Reviewer should inspect the original package and calibrated measurements if required.")
    return _result("LMPC-MVP-005", RuleStatus.REVIEW, "Legibility, contrast, placement, or panel geometry is uncertain. Exact font size cannot be confirmed from this image.", image_evidence, "Request a front-on, high-resolution image with scale reference if dimensions matter.")


def evaluate_compliance(
    extraction: Extraction,
    context: InspectionContext,
    image_names: list[str],
    quality: QualitySummary,
    *,
    ruleset_id: str = "LMPC_MVP",
    ruleset_version: str = "LMPC_2026_08_26",
) -> Assessment:
    normalized = NormalizedContext(
        package_context=context.package_context,
        medical_device=context.medical_device.value,
        date_required=context.date_required.value,
        commodity_type=context.commodity_type or extraction.product.commodity_type or "UNKNOWN",
    )
    results = [
        _evaluate_mrp(extraction, normalized, image_names),
        _evaluate_quantity(extraction, normalized, image_names),
        _evaluate_identity(extraction, normalized, image_names),
        _evaluate_date(extraction, normalized, image_names),
        _evaluate_visual(extraction, normalized, image_names, quality.status),
    ]
    overall = RuleStatus.NOT_APPLICABLE
    if any(item.status == RuleStatus.FAIL for item in results):
        overall = RuleStatus.FAIL
    elif any(item.status == RuleStatus.REVIEW for item in results):
        overall = RuleStatus.REVIEW
    elif any(item.status == RuleStatus.FUTURE for item in results):
        overall = RuleStatus.FUTURE
    elif any(item.status == RuleStatus.PASS for item in results):
        overall = RuleStatus.PASS
    counts = Counter(item.status.value for item in results)
    return Assessment(
        ruleset_id=ruleset_id,
        ruleset_version=ruleset_version,
        overall_status=overall,
        overall_label=STATUS_MAP[overall][1],
        results=results,
        counts=dict(counts),
        context=normalized,
        evidence_assurance=assess_evidence(extraction, quality.status),
        applicability=decide_applicability(extraction, context),
        guardrails=[
            "Automated output is screening support, not a final legal or enforcement determination.",
            "Every applicable result, including a pass, requires an authorized human disposition.",
            "Physical quantity accuracy is not inferred from a photograph.",
            "Exact legal font height is not claimed without calibrated measurement.",
            "Low-confidence or applicability-ambiguous inputs route to human review.",
        ],
        requires_human_review=True,
        final_legal_determination=False,
    )
