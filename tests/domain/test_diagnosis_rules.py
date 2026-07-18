from dataclasses import FrozenInstanceError
from datetime import datetime
from decimal import Decimal

import pytest

from oceanpilot.adapters.diagnosis.rules import RULES, RuleDiagnosisEngine
from oceanpilot.domain.diagnosis import DiagnosisEngine
from oceanpilot.domain.enums import (
    CaseStatus,
    CaseType,
    EvidenceAvailability,
    EvidenceCode,
    Priority,
    ResponsibleTeam,
    ReviewReason,
    SourceReliability,
    StopReason,
)
from oceanpilot.domain.evidence_policy import build_active_evidence_view
from oceanpilot.domain.models import MerchantSuccessCase, ReadinessAssessment

POLICY_VERSION = "POLICY_V1"


def make_case(**updates: object) -> MerchantSuccessCase:
    values = {
        "case_id": "00000000-0000-4000-8000-000000000010",
        "case_type": CaseType.PAYMENT_INCIDENT,
        "status": CaseStatus.EVIDENCE_READY,
        "schema_version": "1",
        "case_revision": 3,
        "evidence_revision": 5,
        "synthetic": True,
        "summary": "Synthetic incident",
        "merchant_ref": "merchant:demo",
        "created_at": datetime.fromisoformat("2026-07-18T12:00:00+08:00"),
        "updated_at": datetime.fromisoformat("2026-07-18T12:01:00+08:00"),
        "readiness": ReadinessAssessment(
            ready=True,
            missing_fields=(),
            known_unknown_fields=(),
            completion_ratio=Decimal("1"),
            stop_reason=StopReason.READY,
        ),
    }
    values.update(updates)
    return MerchantSuccessCase.model_validate(values)


def make_view(
    evidence_factory,
    facts: tuple[tuple[str, str], ...],
    *,
    reliability: SourceReliability = SourceReliability.SYNTHETIC_TEST,
    same_id: bool = False,
):
    count = len(facts)
    items = [
        evidence_factory(
            code=code,
            value=value,
            reliability=reliability,
            evidence_id=(
                "00000000-0000-4000-8000-000000000001"
                if same_id
                else f"00000000-0000-4000-8000-{count - index + 1:012d}"
            ),
        )
        for index, (code, value) in enumerate(facts, start=1)
    ]
    return build_active_evidence_view(items)


RULE_CASES = (
    {
        "rule_id": "THREEDS_INCOMPLETE_V1",
        "cause_code": "THREEDS_AUTH_OR_CALLBACK_INCOMPLETE",
        "facts": (
            ("symptom.status", "PENDING"),
            ("authentication.status", "REQUIRED"),
            ("callback.delivery_status", "NOT_RECEIVED"),
        ),
        "team": ResponsibleTeam.TECHNICAL_SUPPORT,
        "priority": Priority.MEDIUM,
        "forced": frozenset(),
        "next_action": "核对认证结果与服务器回调接收链，不自动重试付款",
        "explanation": "交易状态、认证状态与回调状态同时命中未完成规则，需核对认证与回调链路。",
        "routing_reason": "认证或回调链路需要技术支持复核。",
        "ticket_title": "复核 3DS 认证与回调链路",
    },
    {
        "rule_id": "RISK_DECLINE_V1",
        "cause_code": "RISK_DECLINE_REQUIRES_REVIEW",
        "facts": (
            ("symptom.status", "DECLINED"),
            ("risk.decision_code", "RISK_DECLINE"),
        ),
        "team": ResponsibleTeam.RISK,
        "priority": Priority.HIGH,
        "forced": frozenset({ReviewReason.RISK_DECISION}),
        "next_action": "由风控人员复核决策依据，不自动放行",
        "explanation": "交易状态与 RISK_DECLINE 决策码同时命中风险复核规则。",
        "routing_reason": "风险拒绝需要风控团队人工复核。",
        "ticket_title": "复核风险拒绝决策",
    },
    {
        "rule_id": "CONFIG_MISMATCH_MERCHANT_V1",
        "cause_code": "PAYMENT_CONFIGURATION_MISMATCH",
        "facts": (
            ("symptom.status", "PENDING"),
            ("context.environment", "PROD"),
            ("payment.method", "CARD"),
            ("configuration.check_result", "MERCHANT_SIDE_MISMATCH"),
        ),
        "team": ResponsibleTeam.TECHNICAL_SUPPORT,
        "priority": Priority.MEDIUM,
        "forced": frozenset(),
        "next_action": "生成商户侧环境/方式配置核对清单，不自动修改配置",
        "explanation": "环境、支付方式与配置检查结果命中商户侧配置不匹配规则。",
        "routing_reason": "商户侧支付配置需要技术支持核对。",
        "ticket_title": "核对商户侧支付配置",
    },
    {
        "rule_id": "CONFIG_MISMATCH_PSP_V1",
        "cause_code": "PAYMENT_CONFIGURATION_MISMATCH",
        "facts": (
            ("symptom.status", "PENDING"),
            ("context.environment", "PROD"),
            ("payment.method", "CARD"),
            ("configuration.check_result", "PSP_PROFILE_MISMATCH"),
        ),
        "team": ResponsibleTeam.PSP_SUPPORT,
        "priority": Priority.MEDIUM,
        "forced": frozenset(),
        "next_action": "生成 PSP 资料核对草稿，不触发生产变更",
        "explanation": "环境、支付方式与配置检查结果命中 PSP 侧资料配置不匹配规则。",
        "routing_reason": "PSP 侧资料配置需要支持团队核对。",
        "ticket_title": "核对 PSP 侧资料配置",
    },
)
RULE_BY_ID = {case["rule_id"]: case for case in RULE_CASES}

PREDICATE_VALUES = (
    (
        "THREEDS_INCOMPLETE_V1",
        "symptom.status",
        ("PENDING", "FAILED"),
        ("SUCCEEDED", "DECLINED", "UNKNOWN"),
    ),
    (
        "THREEDS_INCOMPLETE_V1",
        "authentication.status",
        ("REQUIRED", "CHALLENGE_PENDING", "FAILED"),
        ("AUTHENTICATED", "UNKNOWN"),
    ),
    (
        "THREEDS_INCOMPLETE_V1",
        "callback.delivery_status",
        ("NOT_RECEIVED", "FAILED"),
        ("DELIVERED", "UNKNOWN"),
    ),
    (
        "RISK_DECLINE_V1",
        "symptom.status",
        ("DECLINED", "FAILED"),
        ("PENDING", "SUCCEEDED", "UNKNOWN"),
    ),
    (
        "RISK_DECLINE_V1",
        "risk.decision_code",
        ("RISK_DECLINE",),
        ("UNKNOWN", "OTHER"),
    ),
    (
        "CONFIG_MISMATCH_MERCHANT_V1",
        "symptom.status",
        ("PENDING", "FAILED"),
        ("SUCCEEDED", "DECLINED", "UNKNOWN"),
    ),
    (
        "CONFIG_MISMATCH_MERCHANT_V1",
        "context.environment",
        ("PROD", "SANDBOX"),
        (),
    ),
    (
        "CONFIG_MISMATCH_MERCHANT_V1",
        "payment.method",
        ("CARD", "APPLE_PAY", "GOOGLE_PAY", "KLARNA", "LOCAL_PAYMENT", "OTHER"),
        (),
    ),
    (
        "CONFIG_MISMATCH_MERCHANT_V1",
        "configuration.check_result",
        ("MERCHANT_SIDE_MISMATCH",),
        ("PSP_PROFILE_MISMATCH", "NO_MISMATCH", "UNKNOWN"),
    ),
    (
        "CONFIG_MISMATCH_PSP_V1",
        "symptom.status",
        ("PENDING", "FAILED"),
        ("SUCCEEDED", "DECLINED", "UNKNOWN"),
    ),
    (
        "CONFIG_MISMATCH_PSP_V1",
        "context.environment",
        ("PROD", "SANDBOX"),
        (),
    ),
    (
        "CONFIG_MISMATCH_PSP_V1",
        "payment.method",
        ("CARD", "APPLE_PAY", "GOOGLE_PAY", "KLARNA", "LOCAL_PAYMENT", "OTHER"),
        (),
    ),
    (
        "CONFIG_MISMATCH_PSP_V1",
        "configuration.check_result",
        ("PSP_PROFILE_MISMATCH",),
        ("MERCHANT_SIDE_MISMATCH", "NO_MISMATCH", "UNKNOWN"),
    ),
)
ACCEPTED_PREDICATES = tuple(
    (rule_id, code, value)
    for rule_id, code, accepted, _ in PREDICATE_VALUES
    for value in accepted
)
EXCLUDED_PREDICATES = tuple(
    (rule_id, code, value)
    for rule_id, code, _, excluded in PREDICATE_VALUES
    for value in excluded
)
REQUIRED_PREDICATES = tuple(
    (case["rule_id"], code)
    for case in RULE_CASES
    for code, _ in case["facts"]
)


def replace_fact(
    facts: tuple[tuple[str, str], ...],
    code: str,
    value: str,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (item_code, value if item_code == code else item_value)
        for item_code, item_value in facts
    )


def test_rules_are_exact_and_deeply_immutable() -> None:
    assert isinstance(RULES, tuple)
    assert tuple(rule.rule_id for rule in RULES) == tuple(
        case["rule_id"] for case in RULE_CASES
    )
    assert all(isinstance(rule.required_predicates, tuple) for rule in RULES)
    assert all(
        isinstance(predicate.allowed_values, frozenset)
        for rule in RULES
        for predicate in rule.required_predicates
    )
    assert all(isinstance(rule.forced_review_reasons, frozenset) for rule in RULES)

    with pytest.raises(FrozenInstanceError):
        RULES[0].rule_id = "CHANGED"
    with pytest.raises(AttributeError):
        RULES[0].required_predicates[0].allowed_values.add("CHANGED")


def test_rule_engine_structurally_satisfies_the_single_domain_protocol() -> None:
    assert isinstance(RuleDiagnosisEngine(), DiagnosisEngine)


@pytest.mark.parametrize(("rule_id", "code", "value"), ACCEPTED_PREDICATES)
def test_every_accepted_predicate_value_matches(
    evidence_factory,
    rule_id: str,
    code: str,
    value: str,
) -> None:
    case = RULE_BY_ID[rule_id]
    facts = replace_fact(case["facts"], code, value)
    result = RuleDiagnosisEngine().evaluate(
        make_case(),
        make_view(evidence_factory, facts),
        policy_version=POLICY_VERSION,
    )
    assert tuple(hypothesis.rule_id for hypothesis in result.hypotheses) == (rule_id,)


@pytest.mark.parametrize(("rule_id", "code", "value"), EXCLUDED_PREDICATES)
def test_every_excluded_predicate_value_does_not_match(
    evidence_factory,
    rule_id: str,
    code: str,
    value: str,
) -> None:
    case = RULE_BY_ID[rule_id]
    facts = replace_fact(case["facts"], code, value)
    result = RuleDiagnosisEngine().evaluate(
        make_case(),
        make_view(evidence_factory, facts),
        policy_version=POLICY_VERSION,
    )
    matched_ids = tuple(hypothesis.rule_id for hypothesis in result.hypotheses)
    assert rule_id not in matched_ids
    if not matched_ids:
        assert result.review_reasons == frozenset({ReviewReason.POLICY_GAP})


@pytest.mark.parametrize(("rule_id", "missing_code"), REQUIRED_PREDICATES)
@pytest.mark.parametrize("availability", ("missing", "confirmed_unavailable"))
def test_missing_or_unavailable_required_predicate_never_emits_target_rule(
    evidence_factory,
    rule_id: str,
    missing_code: str,
    availability: str,
) -> None:
    rule_case = RULE_BY_ID[rule_id]
    remaining_facts = tuple(
        (code, value) for code, value in rule_case["facts"] if code != missing_code
    )
    remaining_view = make_view(evidence_factory, remaining_facts)
    evidence = [
        remaining_view.slots[EvidenceCode(code)].selected_evidence
        for code, _ in remaining_facts
    ]
    assert all(item is not None for item in evidence)
    if availability == "confirmed_unavailable":
        evidence.append(
            evidence_factory(
                code=missing_code,
                availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
                evidence_id="00000000-0000-4000-8000-000000000099",
            )
        )
    view = build_active_evidence_view(evidence)
    result = RuleDiagnosisEngine().evaluate(
        make_case(), view, policy_version=POLICY_VERSION
    )

    assert rule_id not in tuple(hypothesis.rule_id for hypothesis in result.hypotheses)


@pytest.mark.parametrize("rule_case", RULE_CASES, ids=lambda case: case["rule_id"])
def test_each_rule_emits_the_complete_fixed_output(evidence_factory, rule_case) -> None:
    case = make_case()
    view = make_view(evidence_factory, rule_case["facts"])
    result = RuleDiagnosisEngine().evaluate(
        case,
        view,
        policy_version=POLICY_VERSION,
    )

    assert len(result.hypotheses) == 1
    hypothesis = result.hypotheses[0]
    decisive = tuple(
        view.slots[EvidenceCode(code)].selected_evidence
        for code, _ in rule_case["facts"]
    )
    expected_refs = tuple(sorted(item.evidence_id for item in decisive if item is not None))
    assert hypothesis.rule_id == rule_case["rule_id"]
    assert hypothesis.cause_code == rule_case["cause_code"]
    assert hypothesis.explanation == rule_case["explanation"]
    assert hypothesis.evidence_refs == expected_refs
    assert hypothesis.confidence_score == Decimal("0.94")
    assert hypothesis.confidence_method == "HEURISTIC_V1"
    assert hypothesis.next_verification_action == rule_case["next_action"]

    assert result.review_reasons == rule_case["forced"]
    assert result.requires_human is bool(rule_case["forced"])
    route = result.routing_decision
    assert route is not None
    assert route.responsible_team is rule_case["team"]
    assert route.priority is rule_case["priority"]
    assert route.reason == rule_case["routing_reason"]
    assert route.evidence_refs == hypothesis.evidence_refs
    assert route.requires_human is result.requires_human
    assert route.review_reasons == result.review_reasons

    ticket = result.ticket_draft
    assert ticket is not None
    assert ticket.title == rule_case["ticket_title"]
    assert ticket.summary == rule_case["explanation"]
    assert ticket.evidence_summary == tuple(
        f"{code}={value}" for code, value in rule_case["facts"]
    )
    assert ticket.missing_material == ()
    assert ticket.hypotheses == (hypothesis,)
    assert ticket.next_action == rule_case["next_action"]
    assert ticket.responsible_team is route.responsible_team
    assert ticket.synthetic is case.synthetic is True


def test_decisive_refs_are_deduplicated_and_lexical(evidence_factory) -> None:
    rule_case = RULE_CASES[0]
    result = RuleDiagnosisEngine().evaluate(
        make_case(),
        make_view(evidence_factory, rule_case["facts"], same_id=True),
        policy_version=POLICY_VERSION,
    )
    hypothesis = result.hypotheses[0]
    assert hypothesis.evidence_refs == ("00000000-0000-4000-8000-000000000001",)
    assert result.routing_decision is not None
    assert result.routing_decision.evidence_refs == hypothesis.evidence_refs
    assert result.ticket_draft is not None
    assert len(result.ticket_draft.evidence_summary) == len(rule_case["facts"])


def test_conflicting_view_short_circuits_an_otherwise_matching_rule(
    evidence_factory,
) -> None:
    facts = (*RULE_CASES[0]["facts"], ("symptom.status", "FAILED"))
    view = make_view(evidence_factory, facts)
    result = RuleDiagnosisEngine().evaluate(
        make_case(), view, policy_version=POLICY_VERSION
    )

    assert ReviewReason.CONFLICTING_EVIDENCE in view.review_reasons
    assert result.hypotheses == ()
    assert result.routing_decision is None
    assert result.ticket_draft is None
    assert result.requires_human is True
    assert result.review_reasons == frozenset({ReviewReason.CONFLICTING_EVIDENCE})


def test_zero_matches_returns_policy_gap_only(evidence_factory) -> None:
    view = make_view(evidence_factory, (("symptom.status", "SUCCEEDED"),))
    result = RuleDiagnosisEngine().evaluate(
        make_case(), view, policy_version=POLICY_VERSION
    )

    assert result.hypotheses == ()
    assert result.routing_decision is None
    assert result.ticket_draft is None
    assert result.requires_human is True
    assert result.review_reasons == frozenset({ReviewReason.POLICY_GAP})


def test_multiple_matches_return_conflict_only_without_risk_or_confidence_reasons(
    evidence_factory,
) -> None:
    facts = (
        ("symptom.status", "FAILED"),
        ("authentication.status", "REQUIRED"),
        ("callback.delivery_status", "FAILED"),
        ("risk.decision_code", "RISK_DECLINE"),
    )
    result = RuleDiagnosisEngine().evaluate(
        make_case(),
        make_view(
            evidence_factory,
            facts,
            reliability=SourceReliability.USER_REPORTED,
        ),
        policy_version=POLICY_VERSION,
    )

    assert result.hypotheses == ()
    assert result.routing_decision is None
    assert result.ticket_draft is None
    assert result.requires_human is True
    assert result.review_reasons == frozenset({ReviewReason.CONFLICTING_EVIDENCE})


def test_user_reported_nonrisk_keeps_route_and_ticket(evidence_factory) -> None:
    rule_case = RULE_CASES[0]
    result = RuleDiagnosisEngine().evaluate(
        make_case(),
        make_view(
            evidence_factory,
            rule_case["facts"],
            reliability=SourceReliability.USER_REPORTED,
        ),
        policy_version=POLICY_VERSION,
    )
    assert result.hypotheses[0].confidence_score == Decimal("0.87")
    assert result.review_reasons == frozenset({
        ReviewReason.LOW_CONFIDENCE,
        ReviewReason.INSUFFICIENT_SOURCE_QUALITY,
    })
    assert result.requires_human is True
    assert result.routing_decision is not None
    assert result.ticket_draft is not None


def test_user_reported_risk_unions_all_reasons_and_keeps_risk_route(
    evidence_factory,
) -> None:
    rule_case = RULE_CASES[1]
    result = RuleDiagnosisEngine().evaluate(
        make_case(),
        make_view(
            evidence_factory,
            rule_case["facts"],
            reliability=SourceReliability.USER_REPORTED,
        ),
        policy_version=POLICY_VERSION,
    )
    assert result.hypotheses[0].confidence_score == Decimal("0.87")
    assert result.review_reasons == frozenset({
        ReviewReason.LOW_CONFIDENCE,
        ReviewReason.INSUFFICIENT_SOURCE_QUALITY,
        ReviewReason.RISK_DECISION,
    })
    assert result.routing_decision is not None
    assert result.routing_decision.responsible_team is ResponsibleTeam.RISK
    assert result.ticket_draft is not None
    assert result.ticket_draft.responsible_team is ResponsibleTeam.RISK


def test_unrelated_low_quality_evidence_does_not_change_confidence(
    evidence_factory,
) -> None:
    rule_case = RULE_CASES[0]
    baseline_view = make_view(evidence_factory, rule_case["facts"])
    decisive = [
        baseline_view.slots[EvidenceCode(code)].selected_evidence
        for code, _ in rule_case["facts"]
    ]
    assert all(item is not None for item in decisive)
    unrelated = evidence_factory(
        code="transaction.country",
        value="US",
        reliability=SourceReliability.USER_REPORTED,
        evidence_id="00000000-0000-4000-8000-000000000099",
    )
    unrelated_view = build_active_evidence_view([*decisive, unrelated])
    engine = RuleDiagnosisEngine()
    baseline = engine.evaluate(make_case(), baseline_view, policy_version=POLICY_VERSION)
    with_unrelated = engine.evaluate(
        make_case(), unrelated_view, policy_version=POLICY_VERSION
    )
    assert with_unrelated == baseline


def test_case_metadata_is_ignored_and_inputs_are_not_mutated(evidence_factory) -> None:
    view = make_view(evidence_factory, RULE_CASES[0]["facts"])
    first_case = make_case()
    second_case = make_case(
        case_id="00000000-0000-4000-8000-000000000099",
        status=CaseStatus.HUMAN_REVIEW,
        case_revision=99,
        evidence_revision=101,
        summary="Different summary",
        merchant_ref="merchant:different",
    )
    first_before = first_case.model_dump(mode="json")
    second_before = second_case.model_dump(mode="json")
    view_before = view.model_dump(mode="json")
    engine = RuleDiagnosisEngine()

    first = engine.evaluate(first_case, view, policy_version=POLICY_VERSION)
    second = engine.evaluate(second_case, view, policy_version=POLICY_VERSION)
    replay = engine.evaluate(first_case, view, policy_version=POLICY_VERSION)

    assert first == second == replay
    assert first_case.model_dump(mode="json") == first_before
    assert second_case.model_dump(mode="json") == second_before
    assert view.model_dump(mode="json") == view_before
