import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from oceanpilot.adapters.feishu.cards import (
    NeedInfoCardInput,
    SyntheticEvidenceAction,
    render_diagnosis_card,
    render_need_info_card,
)
from oceanpilot.domain.enums import (
    CaseStatus,
    DiagnosisStatus,
    EvidenceCode,
    Priority,
    ResponsibleTeam,
    ReviewReason,
    TargetRole,
)
from oceanpilot.domain.models import (
    DiagnosisSnapshot,
    DiagnosisView,
    Hypothesis,
    HypothesisDraft,
    RoutingDecision,
    TicketDraft,
)

CASE_ID = "00000000-0000-4000-8000-000000000010"
DIAGNOSIS_ID = "00000000-0000-4000-8000-000000000050"
EVIDENCE_REFS = (
    "00000000-0000-4000-8000-000000000101",
    "00000000-0000-4000-8000-000000000103",
)


def _diagnosis_view(*, requires_human: bool) -> DiagnosisView:
    review_reasons = frozenset({ReviewReason.RISK_DECISION}) if requires_human else frozenset()
    hypothesis = Hypothesis(
        hypothesis_id="00000000-0000-4000-8000-000000000301",
        cause_code="SYNTHETIC_CAUSE",
        explanation="Synthetic candidate explanation",
        evidence_refs=EVIDENCE_REFS,
        confidence_score=Decimal("0.94"),
        confidence_method="HEURISTIC_V1",
        next_verification_action="Review decisive evidence",
        rule_id="SYNTHETIC_RULE_V1",
    )
    draft = HypothesisDraft(**hypothesis.model_dump(exclude={"hypothesis_id"}))
    route = RoutingDecision(
        responsible_team=(
            ResponsibleTeam.RISK if requires_human else ResponsibleTeam.TECHNICAL_SUPPORT
        ),
        priority=Priority.HIGH,
        reason="Synthetic responsibility route",
        evidence_refs=EVIDENCE_REFS,
        requires_human=requires_human,
        review_reasons=review_reasons,
    )
    ticket = TicketDraft(
        title="Synthetic review ticket",
        summary=hypothesis.explanation,
        evidence_summary=("synthetic evidence",),
        missing_material=(),
        hypotheses=(draft,),
        next_action=hypothesis.next_verification_action,
        responsible_team=route.responsible_team,
        synthetic=True,
    )
    snapshot = DiagnosisSnapshot(
        diagnosis_id=DIAGNOSIS_ID,
        case_id=CASE_ID,
        evidence_revision=5,
        policy_version="POLICY_V1",
        engine_version="RULES_V1",
        status=DiagnosisStatus.CURRENT,
        hypotheses=(hypothesis,),
        routing_decision=route,
        ticket_draft=ticket,
        requires_human=requires_human,
        review_reasons=review_reasons,
        synthetic=True,
        created_at=datetime(2026, 8, 5, 4, 0, tzinfo=UTC),
    )
    return DiagnosisView(
        case_id=CASE_ID,
        case_status=(CaseStatus.HUMAN_REVIEW if requires_human else CaseStatus.DIAGNOSED),
        case_revision=7,
        evidence_revision=5,
        diagnosis=snapshot,
    )


def _button_values(value: object) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if isinstance(value, dict):
        if value.get("tag") == "button" and isinstance(value.get("value"), dict):
            found.append(value["value"])
        for child in value.values():
            found.extend(_button_values(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_button_values(child))
    return found


def test_need_info_card_routes_the_question_to_the_target_role():
    card_input = NeedInfoCardInput(
        case_id=CASE_ID,
        case_revision=3,
        missing_fields=("transaction.reference", "symptom.signal"),
        target_role=TargetRole.MERCHANT_TECH,
        next_question="请提供交易参考号和可观察的失败状态。",
        question_reason="这些字段用于定位同一笔交易。",
        synthetic_action=SyntheticEvidenceAction(
            action="submit_evidence",
            case_id=CASE_ID,
            evidence_id="00000000-0000-4000-8000-000000000101",
            evidence_code=EvidenceCode.TRANSACTION_REFERENCE,
            availability="AVAILABLE",
            typed_value="txn_threeds_001",
            source_ref="feishu:synthetic-demo:transaction.reference",
        ),
    )

    card = render_need_info_card(card_input)
    rendered = json.dumps(card, ensure_ascii=False)
    assert "商户技术" in rendered
    assert "transaction.reference" in rendered
    assert "symptom.signal" in rendered
    assert card_input.next_question in rendered
    assert card_input.question_reason in rendered
    assert _button_values(card) == [
        {
            "action": "submit_evidence",
            "case_id": CASE_ID,
            "evidence_id": "00000000-0000-4000-8000-000000000101",
            "evidence_code": "transaction.reference",
            "availability": "AVAILABLE",
            "typed_value": "txn_threeds_001",
            "source_ref": "feishu:synthetic-demo:transaction.reference",
        }
    ]
    assert "提交当前合成示例" in rendered
    assert "比赛演示（合成数据）" in rendered
    assert "`transaction.reference` = `txn_threeds_001`" in rendered
    assert render_need_info_card(card_input) == card


def test_need_info_input_is_strict():
    with pytest.raises(ValidationError):
        NeedInfoCardInput(
            case_id=CASE_ID,
            case_revision="3",
            missing_fields=("transaction.reference",),
            target_role=TargetRole.MERCHANT_TECH,
            next_question="Provide the transaction reference.",
            question_reason="Locate the transaction.",
        )


def test_human_review_diagnosis_has_one_safe_confirmation_action():
    view = _diagnosis_view(requires_human=True)
    card = render_diagnosis_card(view)
    rendered = json.dumps(card, ensure_ascii=False)

    assert "SYNTHETIC_CAUSE" in rendered
    assert "Synthetic candidate explanation" in rendered
    assert "0.94" in rendered
    assert all(reference in rendered for reference in EVIDENCE_REFS)
    assert "RISK" in rendered
    assert "Review decisive evidence" in rendered
    assert _button_values(card) == [
        {
            "action": "confirm_review",
            "case_id": CASE_ID,
            "diagnosis_id": DIAGNOSIS_ID,
        }
    ]
    lowered = rendered.lower()
    assert "payment_action" not in lowered
    assert "refund" not in lowered
    assert "risk_release" not in lowered
    assert "risk-release" not in lowered


def test_diagnosed_card_has_no_action_and_requires_strict_view():
    card = render_diagnosis_card(_diagnosis_view(requires_human=False))
    assert _button_values(card) == []
    with pytest.raises(TypeError):
        render_diagnosis_card({"case_id": CASE_ID})  # type: ignore[arg-type]
