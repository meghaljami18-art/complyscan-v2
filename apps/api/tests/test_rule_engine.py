from app.models import InspectionContext, QualityStatus, QualitySummary
from app.rule_engine import evaluate_compliance
from app.vision import fixture_extraction


def context(**overrides):
    data = {"package_context": "RETAIL", "medical_device": "FALSE", "date_required": "TRUE", "commodity_type": "Cosmetic"}
    data.update(overrides)
    return InspectionContext(**data)


def quality(status="GOOD"):
    return QualitySummary(status=status, score=0.95)


def run(fixture="good", *, ctx=None, image_quality="GOOD"):
    return evaluate_compliance(fixture_extraction(fixture), ctx or context(), ["label.jpg"], quality(image_quality))


def test_complete_readable_label_passes_exactly_five_selected_checks():
    assessment = run()
    assert assessment.overall_status == "PASS"
    assert len(assessment.results) == 5
    assert [item.rule_id for item in assessment.results] == [f"LMPC-MVP-00{i}" for i in range(1, 6)]
    assert sum(item.status == "PASS" for item in assessment.results) == 5
    assert assessment.requires_human_review is True
    assert assessment.final_legal_determination is False


def test_conflicting_mrp_routes_to_review_without_choosing_value():
    assessment = run("conflicting_mrp")
    assert assessment.results[0].status == "REVIEW"
    assert assessment.overall_status == "REVIEW"
    assert assessment.evidence_assurance.conflicting_fields == ["mrp"]


def test_missing_quantity_on_visible_panel_is_failure_candidate():
    assessment = run("missing_quantity")
    assert assessment.results[1].status == "FAIL"
    assert assessment.overall_status == "FAIL"


def test_front_only_images_route_missing_declarations_to_review():
    assessment = run("front_only")
    assert assessment.results[0].status == "REVIEW"
    assert assessment.results[2].status == "REVIEW"


def test_poor_client_image_quality_routes_visual_check_to_review():
    assessment = run(image_quality="POOR")
    assert assessment.results[4].status == "REVIEW"


def test_unknown_medical_device_does_not_block_ordinary_visual_predicate():
    assessment = run(ctx=context(medical_device="UNKNOWN"))
    assert assessment.results[4].status == "PASS"


def test_date_false_is_not_applicable_and_export_excludes_mrp_quantity():
    assessment = run(ctx=context(package_context="EXPORT", date_required="FALSE"))
    assert assessment.results[0].status == "NOT_APPLICABLE"
    assert assessment.results[1].status == "NOT_APPLICABLE"
    assert assessment.results[3].status == "NOT_APPLICABLE"
    assert assessment.applicability[3].selected is False


def test_fail_precedes_review_and_pass_in_overall_state():
    assessment = run("poor_legibility")
    assert assessment.results[4].status == "FAIL"
    assert assessment.overall_status == "FAIL"
