from datetime import datetime
from decimal import Decimal
from inspect import signature
from itertools import permutations

import pytest

from oceanpilot.domain.enums import (
    EvidenceAvailability,
    EvidenceCode,
    StopReason,
    TargetRole,
)
from oceanpilot.domain.evidence_policy import assess_readiness, build_active_evidence_view

PRIORITY_INPUTS = (
    ("transaction.reference", "txn_1"),
    ("transaction.occurred_at", datetime.fromisoformat("2026-07-18T12:00:00+08:00")),
    ("context.environment", "PROD"),
    ("symptom.status", "FAILED"),
    ("integration.type", "API"),
)
PRIORITY_SLOTS = (
    "transaction.reference",
    "transaction.occurred_at",
    "context.environment",
    "symptom.signal",
    "integration.type",
)
PRIORITY_REASONS = (
    "定位同一笔交易",
    "对齐订单、回调和风控时间线",
    "区分配置与凭据环境",
    "确认可观察症状",
    "决定后续条件槽位",
)
SYMPTOM_CODES = (
    "symptom.status",
    "symptom.error_code",
    "authentication.status",
    "authentication.result_code",
    "callback.delivery_status",
    "risk.decision_code",
    "configuration.check_result",
)


def progressive_items(evidence_factory, count: int, *, integration: str = "API"):
    values = (*PRIORITY_INPUTS[:4], ("integration.type", integration))
    return [
        evidence_factory(
            code=code,
            value=value,
            evidence_id=f"00000000-0000-4000-8000-{index:012d}",
        )
        for index, (code, value) in enumerate(values[:count], start=1)
    ]


def test_assess_readiness_has_the_locked_single_parameter_interface() -> None:
    assert tuple(signature(assess_readiness).parameters) == ("view",)


def test_empty_readiness_uses_first_question_and_lexical_missing_fields() -> None:
    result = assess_readiness(build_active_evidence_view([]))

    assert result.ready is False
    assert result.next_question == "transaction.reference"
    assert result.question_reason == "定位同一笔交易"
    assert result.target_role is TargetRole.MERCHANT_TECH
    assert result.missing_fields == tuple(sorted(PRIORITY_SLOTS))
    assert result.known_unknown_fields == ()
    assert result.completion_ratio == Decimal("0.0000")
    assert result.stop_reason is StopReason.NEED_MORE_EVIDENCE


@pytest.mark.parametrize(
    ("count", "next_question", "reason", "ratio"),
    (
        (0, PRIORITY_SLOTS[0], PRIORITY_REASONS[0], "0.0000"),
        (1, PRIORITY_SLOTS[1], PRIORITY_REASONS[1], "0.2000"),
        (2, PRIORITY_SLOTS[2], PRIORITY_REASONS[2], "0.4000"),
        (3, PRIORITY_SLOTS[3], PRIORITY_REASONS[3], "0.6000"),
        (4, PRIORITY_SLOTS[4], PRIORITY_REASONS[4], "0.8000"),
        (5, None, None, "1.0000"),
    ),
)
def test_readiness_follows_the_exact_priority_steps(
    evidence_factory,
    count: int,
    next_question: str | None,
    reason: str | None,
    ratio: str,
) -> None:
    result = assess_readiness(
        build_active_evidence_view(progressive_items(evidence_factory, count))
    )

    assert result.next_question == next_question
    assert result.question_reason == reason
    assert result.target_role is (TargetRole.MERCHANT_TECH if next_question else None)
    assert str(result.completion_ratio) == ratio
    assert result.ready is (count == 5)


def test_plugin_activates_conditional_rows_at_five_of_seven(evidence_factory) -> None:
    items = progressive_items(evidence_factory, 5, integration="PLUGIN")
    result = assess_readiness(build_active_evidence_view(items))

    assert result.completion_ratio == Decimal("0.7143")
    assert result.next_question == "integration.platform"
    assert result.question_reason == "确定插件上下文"
    assert result.missing_fields == (
        "integration.platform",
        "integration.plugin_version",
    )
    assert result.stop_reason is StopReason.NEED_MORE_EVIDENCE


def test_plugin_platform_answer_advances_to_version_question(evidence_factory) -> None:
    items = progressive_items(evidence_factory, 5, integration="PLUGIN")
    items.append(
        evidence_factory(
            code="integration.platform",
            value="SHOPIFY",
            evidence_id="00000000-0000-4000-8000-000000000006",
        )
    )
    result = assess_readiness(build_active_evidence_view(items))

    assert result.completion_ratio == Decimal("0.8571")
    assert result.next_question == "integration.plugin_version"
    assert result.question_reason == "排查版本差异"
    assert result.target_role is TargetRole.MERCHANT_TECH


def test_complete_plugin_context_is_ready(evidence_factory) -> None:
    items = progressive_items(evidence_factory, 5, integration="PLUGIN")
    items.extend(
        (
            evidence_factory(
                code="integration.platform",
                value="SHOPIFY",
                evidence_id="00000000-0000-4000-8000-000000000006",
            ),
            evidence_factory(
                code="integration.plugin_version",
                value="v1.2.3",
                evidence_id="00000000-0000-4000-8000-000000000007",
            ),
        )
    )
    result = assess_readiness(build_active_evidence_view(items))

    assert result.ready is True
    assert result.completion_ratio == Decimal("1.0000")
    assert result.next_question is None
    assert result.question_reason is None
    assert result.target_role is None
    assert result.stop_reason is StopReason.READY


def test_noncore_confirmed_unknown_counts_answered(evidence_factory) -> None:
    items = progressive_items(evidence_factory, 4)
    items.append(
        evidence_factory(
            code="integration.type",
            availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
            evidence_id="00000000-0000-4000-8000-000000000005",
        )
    )
    result = assess_readiness(build_active_evidence_view(items))

    assert result.ready is True
    assert result.known_unknown_fields == ("integration.type",)
    assert result.missing_fields == ()
    assert result.next_question is None
    assert result.stop_reason is StopReason.READY


def test_all_symptom_members_unavailable_make_core_confirmed_unknown(
    evidence_factory,
) -> None:
    items = progressive_items(evidence_factory, 3)
    items.extend(
        evidence_factory(
            code=code,
            availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
            evidence_id=f"00000000-0000-4000-8000-{index:012d}",
        )
        for index, code in enumerate(SYMPTOM_CODES, start=10)
    )
    items.append(
        evidence_factory(
            code="integration.type",
            value="API",
            evidence_id="00000000-0000-4000-8000-000000000020",
        )
    )
    result = assess_readiness(build_active_evidence_view(items))

    assert result.completion_ratio == Decimal("1.0000")
    assert result.missing_fields == ("symptom.signal",)
    assert result.known_unknown_fields == ()
    assert result.next_question is None
    assert result.stop_reason is StopReason.CONFIRMED_UNKNOWN
    assert result.ready is False


def test_partial_symptom_unknown_remains_missing(evidence_factory) -> None:
    items = progressive_items(evidence_factory, 3)
    items.extend(
        (
            evidence_factory(
                code="symptom.status",
                availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
                evidence_id="00000000-0000-4000-8000-000000000004",
            ),
            evidence_factory(
                code="integration.type",
                value="API",
                evidence_id="00000000-0000-4000-8000-000000000005",
            ),
        )
    )
    result = assess_readiness(build_active_evidence_view(items))

    assert result.next_question == "symptom.signal"
    assert result.completion_ratio == Decimal("0.8000")
    assert result.stop_reason is StopReason.NEED_MORE_EVIDENCE


def test_core_confirmed_unknown_has_no_question_after_all_rows_answered(
    evidence_factory,
) -> None:
    items = progressive_items(evidence_factory, 5)
    items[0] = evidence_factory(
        code="transaction.reference",
        availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
        evidence_id="00000000-0000-4000-8000-000000000001",
    )
    result = assess_readiness(build_active_evidence_view(items))

    assert result.missing_fields == ("transaction.reference",)
    assert result.next_question is None
    assert result.question_reason is None
    assert result.target_role is None
    assert result.completion_ratio == Decimal("1.0000")
    assert result.stop_reason is StopReason.CONFIRMED_UNKNOWN


def test_unanswered_row_precedes_core_confirmed_unknown(evidence_factory) -> None:
    item = evidence_factory(
        code="transaction.reference",
        availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
        evidence_id="00000000-0000-4000-8000-000000000001",
    )
    result = assess_readiness(build_active_evidence_view([item]))

    assert result.completion_ratio == Decimal("0.2000")
    assert result.next_question == "transaction.occurred_at"
    assert result.question_reason == "对齐订单、回调和风控时间线"
    assert result.stop_reason is StopReason.NEED_MORE_EVIDENCE


def test_core_conflict_counts_available_and_can_be_ready(evidence_factory) -> None:
    items = progressive_items(evidence_factory, 5)
    items.append(
        evidence_factory(
            code="transaction.reference",
            value="txn_2",
            evidence_id="00000000-0000-4000-8000-000000000010",
        )
    )
    result = assess_readiness(build_active_evidence_view(items))

    assert result.ready is True
    assert result.missing_fields == ()
    assert result.stop_reason is StopReason.READY


def test_symptom_member_conflict_counts_the_composite_available(evidence_factory) -> None:
    items = progressive_items(evidence_factory, 3)
    items.extend(
        (
            evidence_factory(
                code="symptom.status",
                value="FAILED",
                evidence_id="00000000-0000-4000-8000-000000000004",
            ),
            evidence_factory(
                code="symptom.status",
                value="SUCCEEDED",
                evidence_id="00000000-0000-4000-8000-000000000005",
            ),
            evidence_factory(
                code="integration.type",
                value="API",
                evidence_id="00000000-0000-4000-8000-000000000006",
            ),
        )
    )
    view = build_active_evidence_view(items)
    result = assess_readiness(view)

    assert view.slots[EvidenceCode.SYMPTOM_STATUS].conflicting is True
    assert result.ready is True
    assert result.completion_ratio == Decimal("1.0000")
    assert result.stop_reason is StopReason.READY


def test_integration_conflict_does_not_activate_plugin_rows(evidence_factory) -> None:
    items = progressive_items(evidence_factory, 4)
    items.extend(
        (
            evidence_factory(
                code="integration.type",
                value="API",
                evidence_id="00000000-0000-4000-8000-000000000005",
            ),
            evidence_factory(
                code="integration.type",
                value="PLUGIN",
                evidence_id="00000000-0000-4000-8000-000000000006",
            ),
        )
    )
    result = assess_readiness(build_active_evidence_view(items))

    assert result.ready is True
    assert result.completion_ratio == Decimal("1.0000")
    assert result.missing_fields == ()


def test_inactive_presupplied_plugin_evidence_has_no_effect(evidence_factory) -> None:
    items = progressive_items(evidence_factory, 4)
    items.extend(
        (
            evidence_factory(
                code="integration.platform",
                value="SHOPIFY",
                evidence_id="00000000-0000-4000-8000-000000000006",
            ),
            evidence_factory(
                code="integration.plugin_version",
                value="v1",
                evidence_id="00000000-0000-4000-8000-000000000007",
            ),
        )
    )
    result = assess_readiness(build_active_evidence_view(items))

    assert result.completion_ratio == Decimal("0.8000")
    assert result.next_question == "integration.type"
    assert result.missing_fields == ("integration.type",)
    assert result.known_unknown_fields == ()


def test_plugin_known_unknown_fields_are_lexically_sorted(evidence_factory) -> None:
    items = progressive_items(evidence_factory, 5, integration="PLUGIN")
    items.extend(
        (
            evidence_factory(
                code="integration.plugin_version",
                availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
                evidence_id="00000000-0000-4000-8000-000000000006",
            ),
            evidence_factory(
                code="integration.platform",
                availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
                evidence_id="00000000-0000-4000-8000-000000000007",
            ),
        )
    )
    result = assess_readiness(build_active_evidence_view(items))

    assert result.ready is True
    assert result.known_unknown_fields == (
        "integration.platform",
        "integration.plugin_version",
    )
    assert result.stop_reason is StopReason.READY


def test_readiness_is_invariant_to_evidence_permutations(evidence_factory) -> None:
    items = progressive_items(evidence_factory, 5)
    expected = assess_readiness(build_active_evidence_view(items))
    results = (
        assess_readiness(build_active_evidence_view((*order, *items[3:])))
        for order in permutations(items[:3])
    )
    assert all(result == expected for result in results)
