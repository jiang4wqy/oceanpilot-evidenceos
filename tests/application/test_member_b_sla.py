"""Overdue merchant work creates a durable operational follow-up without deciding the case."""

from datetime import timedelta

from oceanpilot.adapters.persistence.dispute_collaboration import SQLiteDisputeCollaborationStore
from oceanpilot.application.dispute_collaboration import DisputeCollaborationService
from tests.application.test_dispute_collaboration import OP, collecting
from tests.application.test_dispute_collaboration import stack as stack


def test_merchant_overdue_creates_one_internal_followup_across_restart(stack):
    disputes, _, collab, _, _, clock = stack
    case = collecting(stack)
    revision = case["revision"]
    clock[0] += timedelta(hours=74)
    collab.tick()
    handoffs = collab.open_handoffs(case["id"])
    assert len(handoffs) == 1
    assert handoffs[0]["scope"] == "OP_INTERNAL"
    assert "商户任务已逾期" in handoffs[0]["reason"]
    restarted = DisputeCollaborationService(
        SQLiteDisputeCollaborationStore(collab.store.db_path), disputes, clock=lambda: clock[0]
    )
    assert restarted.tick()["emitted"] == []
    assert [h["id"] for h in restarted.open_handoffs(case["id"])] == [handoffs[0]["id"]]
    saved = disputes.get_case(case["id"], OP)
    assert saved["revision"] == revision
    assert saved["merchant_decision"] == "CONTEST"
    assert saved["finality"] == "NOT_FINAL"
