import json
from datetime import UTC, datetime

import pytest

from oceanpilot.adapters.persistence.chargeback_review_sqlite import SqliteCaseReviewStore
from oceanpilot.adapters.persistence.chargeback_sqlite import (
    SqliteChargebackCaseStore,
    initialize_chargeback_schema,
)
from oceanpilot.application.case_review import AgentTurnRecord, ReviewStatus
from oceanpilot.application.errors import ConcurrentCaseWrite


def _proposal(status: str = "APPROVED") -> str:
    return json.dumps(
        {
            "status": status,
            "summary": "审核人员确认 Synthetic 材料内容一致。",
            "confirmed_materials": ["transaction.receipt"],
            "citation_ids": ["visa-10-4-demo-v1"],
        },
        ensure_ascii=False,
    )


def test_review_confirmation_is_atomic_replayable_and_revision_checked(tmp_path):
    path = tmp_path / "review.db"
    initialize_chargeback_schema(path)
    case_store = SqliteChargebackCaseStore(path)
    review_store = SqliteCaseReviewStore(path)
    case_id = case_store.create()
    revision = review_store.current_revision(case_id)
    turn = AgentTurnRecord(
        turn_id="turn-1",
        case_id=case_id,
        case_revision=revision,
        trigger="USER_MESSAGE",
        response_json='{"turn_kind":"CASE_ANALYZED"}',
        proposal_json=_proposal(),
        created_at=datetime(2026, 8, 16, tzinfo=UTC),
    )
    review_store.save_turn(turn)

    created = review_store.confirm_review(
        case_id=case_id,
        source_turn_id=turn.turn_id,
        expected_revision=revision,
        confirmed_by="judge_reviewer_01",
    )
    replayed = review_store.confirm_review(
        case_id=case_id,
        source_turn_id=turn.turn_id,
        expected_revision=revision,
        confirmed_by="judge_reviewer_01",
    )

    assert created.result == "CREATED"
    assert replayed.result == "REPLAYED"
    assert replayed.decision.decision_id == created.decision.decision_id
    assert created.decision.status is ReviewStatus.APPROVED
    assert review_store.current_revision(case_id) == revision + 1
    assert review_store.latest_decision(case_id) == created.decision
    audit = review_store.audit_trail(case_id)
    assert len(audit) == 1
    assert audit[0].event_type == "REVIEW_DECISION_CONFIRMED"

    stale_turn = AgentTurnRecord(
        turn_id="turn-stale",
        case_id=case_id,
        case_revision=revision,
        trigger="USER_MESSAGE",
        response_json='{"turn_kind":"CASE_ANALYZED"}',
        proposal_json=_proposal("NEEDS_MORE_INFO"),
        created_at=datetime(2026, 8, 16, 0, 1, tzinfo=UTC),
    )
    with pytest.raises(ConcurrentCaseWrite):
        review_store.save_turn(stale_turn)


def test_review_turn_cannot_be_confirmed_for_another_case(tmp_path):
    path = tmp_path / "cross-case-review.db"
    initialize_chargeback_schema(path)
    case_store = SqliteChargebackCaseStore(path)
    review_store = SqliteCaseReviewStore(path)
    case_a = case_store.create()
    case_b = case_store.create()
    revision = review_store.current_revision(case_a)
    review_store.save_turn(
        AgentTurnRecord(
            turn_id="turn-a",
            case_id=case_a,
            case_revision=revision,
            trigger="USER_MESSAGE",
            response_json='{"turn_kind":"CASE_ANALYZED"}',
            proposal_json=_proposal(),
            created_at=datetime(2026, 8, 16, tzinfo=UTC),
        )
    )

    with pytest.raises(ValueError):
        review_store.confirm_review(
            case_id=case_b,
            source_turn_id="turn-a",
            expected_revision=review_store.current_revision(case_b),
            confirmed_by="judge_reviewer_01",
        )
