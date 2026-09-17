from __future__ import annotations

from statistics import mean

from .models import ApplicabilityDecision, EvidenceAssurance, Extraction, InspectionContext, QualityStatus

FIELD_KEYS = ("mrp", "net_quantity", "responsible_entity", "address", "date", "consumer_care")


def assess_evidence(extraction: Extraction, quality: QualityStatus) -> EvidenceAssurance:
    confidences: list[float] = []
    low_fields: list[str] = []
    conflicts: list[str] = []
    for key in FIELD_KEYS:
        candidates = list(getattr(extraction.fields, key))
        confidences.extend(item.confidence for item in candidates)
        if candidates and max(item.confidence for item in candidates) < 0.85:
            low_fields.append(key)
        distinct = {item.value.strip().lower() for item in candidates if item.value.strip()}
        if len(distinct) > 1:
            conflicts.append(key)

    average_confidence = mean(confidences) if confidences else 0.0
    panel_factor = {"YES": 1.0, "UNCERTAIN": 0.55, "NO": 0.25}[extraction.coverage.mandatory_declaration_panel_visible.value]
    quality_factor = {QualityStatus.GOOD: 1.0, QualityStatus.FAIR: 0.6, QualityStatus.POOR: 0.25}[quality]
    conflict_factor = 0.65 if conflicts else 1.0
    score = max(0.0, min(1.0, (average_confidence * 0.55 + panel_factor * 0.25 + quality_factor * 0.20) * conflict_factor))

    reasons: list[str] = []
    if not confidences:
        reasons.append("No declaration candidates were extracted.")
    if extraction.coverage.mandatory_declaration_panel_visible.value != "YES":
        reasons.append("The mandatory-declaration panel is not conclusively visible.")
    if quality != QualityStatus.GOOD:
        reasons.append("Image quality is not rated GOOD.")
    if low_fields:
        reasons.append("One or more extracted fields are below the 0.85 evidence-assurance gate.")
    if conflicts:
        reasons.append("Conflicting values require a human to choose or request more evidence.")
    if not reasons:
        reasons.append("Coverage, image quality and extraction confidence support review; a human disposition is still required.")

    if score >= 0.85 and not conflicts:
        level = "HIGH"
    elif score >= 0.65:
        level = "MEDIUM"
    elif score > 0:
        level = "LOW"
    else:
        level = "INSUFFICIENT"

    return EvidenceAssurance(
        level=level,
        score=round(score, 4),
        sufficient_for_automated_pass=level == "HIGH" and not low_fields and not conflicts,
        reasons=reasons,
        low_confidence_fields=low_fields,
        conflicting_fields=conflicts,
    )


def decide_applicability(extraction: Extraction, context: InspectionContext) -> list[ApplicabilityDecision]:
    package_context = context.package_context
    medical_device = context.medical_device.value
    date_required = context.date_required.value
    return [
        ApplicabilityDecision(
            rule_id="LMPC-MVP-001",
            selected=package_context != "EXPORT",
            outcome="NOT_APPLICABLE" if package_context == "EXPORT" else ("REVIEW" if medical_device == "TRUE" else "APPLICABLE"),
            reason="Export context excludes the prototype retail-MRP predicate." if package_context == "EXPORT" else "Medical-device routing may change the declaration regime." if medical_device == "TRUE" else "The selected package context selects the MRP predicate.",
        ),
        ApplicabilityDecision(
            rule_id="LMPC-MVP-002",
            selected=package_context != "EXPORT",
            outcome="NOT_APPLICABLE" if package_context == "EXPORT" else "APPLICABLE",
            reason="Export context excludes this prototype quantity route." if package_context == "EXPORT" else "The selected package context selects the quantity predicate.",
        ),
        ApplicabilityDecision(
            rule_id="LMPC-MVP-003",
            selected=True,
            outcome="REVIEW" if medical_device == "TRUE" else "APPLICABLE",
            reason="Medical-device status requires MDR priority review." if medical_device == "TRUE" else "The general responsible-entity declaration predicate is selected.",
        ),
        ApplicabilityDecision(
            rule_id="LMPC-MVP-004",
            selected=date_required != "FALSE",
            outcome="NOT_APPLICABLE" if date_required == "FALSE" else ("APPLICABLE" if date_required == "TRUE" else "REVIEW"),
            reason="The selected commodity/context says the date predicate is not required." if date_required == "FALSE" else "The selected commodity/context requires the date predicate." if date_required == "TRUE" else "Date applicability is unresolved and must be reviewed.",
        ),
        ApplicabilityDecision(
            rule_id="LMPC-MVP-005",
            selected=True,
            outcome="REVIEW" if medical_device == "TRUE" else "APPLICABLE",
            reason="Medical-device status requires the MDR visual route." if medical_device == "TRUE" else "Observable placement and legibility screening is selected.",
        ),
    ]
