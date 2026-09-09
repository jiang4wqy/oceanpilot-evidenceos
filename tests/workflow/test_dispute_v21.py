"""V2.1 business regressions; baseline 759e3b3 rejects/misroutes these cases."""

from datetime import timedelta
from uuid import uuid4

import pytest

from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.disputes import DisputeError, DisputeService
from oceanpilot.domain.dispute_rules import case_plan
from tests.workflow.test_dispute_engine import (
    MERCHANT,
    NOW,
    OP,
    RISK,
    SUPERVISOR,
    contest,
    frozen,
    intake,
    reconciled,
    reviewed,
    run,
    submitted,
)


@pytest.fixture
def service(tmp_path):
    return DisputeService(SQLiteDisputeStore(tmp_path / "v21.db"), clock=lambda: NOW)


def rule_data(**changes):
    return (
        dict(
            source_id="manual-synthetic",
            source_locator="section one",
            rule_version="v21",
            merchant_deadline=(NOW + timedelta(days=3)).isoformat(),
            external_deadline=(NOW + timedelta(days=5)).isoformat(),
            required_evidence=["receipt"],
            allowed_actions=["ACCEPT", "CONTEST"],
            reason="Reviewed source and action rights",
        )
        | changes
    )


def fill(service, case):
    for code in case["rule_snapshot"]["required_evidence"]:
        case = run(
            service,
            case,
            "REGISTER_EVIDENCE",
            {"code": code, "title": code, "reference": "synthetic://proof"},
            MERCHANT,
        )
    return run(service, case, "SUBMIT_EVIDENCE", identity=MERCHANT)


def outcome_data(**changes):
    return dict(event_id=uuid4().hex, outcome="LOST", final=False, source="mock-upstream") | changes


def test_w02_contest_lateness_never_becomes_no_response(service):
    case = contest(service)
    service.clock = lambda: NOW + timedelta(days=4)
    with pytest.raises(DisputeError) as error:
        run(
            service,
            case,
            "MERCHANT_DECISION",
            {"decision": "NO_RESPONSE", "reason": "Late materials"},
        )
    assert error.value.code == "ALREADY_RESPONDED"
    case = run(service, case, "MONITOR_SLA")
    assert case["merchant_decision"] == "CONTEST"
    assert case["evidence_task_status"] == "OVERDUE"
    assert any(t["type"] == "EVIDENCE_OVERDUE" for t in case["tasks"])


def test_w01_authorized_same_stage_restore(service):
    case = run(service, intake(service), "PUBLISH_TASK")
    service.clock = lambda: NOW + timedelta(days=4)
    case = run(
        service,
        case,
        "MERCHANT_DECISION",
        {"decision": "NO_RESPONSE", "reason": "No decision received"},
    )
    case = run(
        service,
        case,
        "RESOLVE_RESPONSE",
        {
            "resolution": "RESTORE_DECISION",
            "reason": "External window remains open",
            "authorization_reference": "rights-source",
            "external_deadline": (NOW + timedelta(days=5)).isoformat(),
        },
        RISK,
    )
    case = run(
        service,
        case,
        "MERCHANT_DECISION",
        {"decision": "CONTEST", "reason": "Proof available"},
        MERCHANT,
    )
    assert case["stage_number"] == 1 and case["merchant_decision"] == "CONTEST"
    assert not any(e["type"] == "OUTCOME" for e in case["upstream_events"])


def test_w03_review_accept_is_recommendation_not_revision(service):
    case = run(
        service,
        fill(service, contest(service)),
        "REVIEW",
        {"decision": "ACCEPT", "reason": "Consider accepting liability"},
        RISK,
    )
    assert case["work_status"] == "ACCEPT_RECOMMENDATION"
    assert case["merchant_decision"] == "CONTEST"
    assert any(t["type"] == "ACCEPT_DECISION" and t["status"] == "OPEN" for t in case["tasks"])
    assert not any(t["type"] == "REVISION" and t["status"] == "OPEN" for t in case["tasks"])
    case = run(
        service,
        case,
        "MERCHANT_DECISION",
        {"decision": "ACCEPT", "reason": "I confirm responsibility"},
        MERCHANT,
    )
    assert case["work_status"] == "ACCEPT_PROCESSING"


@pytest.mark.parametrize(
    "decision,status",
    [
        ("RETURN_MATERIALS", "MERCHANT_REVISION_REQUIRED"),
        ("RETURN_DOCUMENT", "DOCUMENT_REVISION_REQUIRED"),
        ("RECOMMEND_ACCEPT", "ACCEPT_RECOMMENDATION"),
        ("HOLD", "ON_HOLD"),
    ],
)
def test_w04_final_review_has_specific_rejection_routes(service, decision, status):
    case = run(service, reviewed(service), "BUILD_PACKAGE")
    case = run(
        service,
        case,
        "FINAL_REVIEW",
        {"decision": decision, "reason": "Specific supervisor finding"},
        SUPERVISOR,
    )
    assert case["work_status"] == status
    assert case["packages"][-1]["status"] == "INVALIDATED"
    if decision == "RETURN_DOCUMENT":
        case = run(service, case, "BUILD_PACKAGE", {"draft": "Corrected synthetic response"})
        assert case["work_status"] == "SUBMISSION_PENDING_CONFIRMATION"
        assert case["packages"][-1]["status"] == "DRAFT"


def test_w05_known_nonterminal_can_wait_in_same_stage(service):
    case = run(service, submitted(service), "RECORD_OUTCOME", outcome_data(disposition="WAIT"))
    assert case["work_status"] == "WAITING_UPSTREAM" and not case["pending_next_stage"]
    assert case["current_stage_outcome"] == "LOST"


def test_w06_unmapped_other_cannot_be_terminal(service):
    with pytest.raises(DisputeError) as error:
        run(
            service, submitted(service), "RECORD_OUTCOME", outcome_data(outcome="OTHER", final=True)
        )
    assert error.value.code == "OUTCOME_MAPPING_REQUIRED"


def test_w07_async_withdrawal_enters_human_verification(service):
    case = contest(service)
    case = run(
        service,
        case,
        "RECORD_OUTCOME",
        outcome_data(
            outcome="WITHDRAWN",
            final=True,
            occurred_at=NOW.isoformat(),
            stage_number=1,
            basis_reference="withdrawal-source",
        ),
    )
    assert case["finality"] == "NOT_FINAL" and case["work_status"] == "OUTCOME_VERIFICATION"
    case = run(
        service,
        case,
        "VERIFY_OUTCOME",
        {
            "event_id": case["upstream_events"][-1]["event_id"],
            "decision": "CONFIRM",
            "reason": "Source and stage verified",
            "authorization_reference": "risk-check",
        },
        RISK,
    )
    assert case["finality"] == "FINAL_CONFIRMED" and case["business_outcome"] == "WITHDRAWN"
    assert not case["submissions"]
    assert any(t["type"] == "EVIDENCE" and t["status"] == "CANCELLED" for t in case["tasks"])


def test_w08_close_requires_explicit_reopen_then_correction(service):
    case = run(
        service, run(service, reconciled(service), "NOTIFY_MERCHANT"), "CLOSE", identity=SUPERVISOR
    )
    old_event = case["upstream_events"][-1]["event_id"]
    case = run(
        service,
        case,
        "REOPEN_CASE",
        {
            "reason": "Verified correction received",
            "authorization_reference": "supervisor-authority",
            "event_reference": "corrected-channel-event",
        },
        SUPERVISOR,
    )
    case = run(
        service,
        case,
        "RECORD_OUTCOME",
        outcome_data(
            outcome="LOST",
            final=True,
            corrects_event_id=old_event,
            basis_reference="correction-source",
            stage_number=1,
        ),
    )
    case = run(
        service,
        case,
        "VERIFY_OUTCOME",
        {
            "event_id": case["upstream_events"][-1]["event_id"],
            "decision": "CONFIRM",
            "reason": "Correction verified",
            "authorization_reference": "risk-authority",
        },
        RISK,
    )
    assert case["business_outcome"] == "LOST" and not case["merchant_notification_completed"]
    assert case["closure_history"] and case["outcome_history"]
    assert case["financial_status"] == "PENDING"


def test_w09_rule_change_revokes_contest_for_all_risky_commands(service):
    case = contest(service)
    case = run(
        service,
        case,
        "CONFIRM_RULE",
        rule_data(allowed_actions=["ACCEPT"], required_evidence=[]),
        RISK,
    )
    assert case["eligibility_status"] == "REQUIRES_RECONFIRMATION"
    for action, identity in [
        ("SUBMIT_EVIDENCE", MERCHANT),
        ("REVIEW", RISK),
        ("BUILD_PACKAGE", OP),
        ("APPROVE_PACKAGE", SUPERVISOR),
        ("SUBMIT", OP),
    ]:
        with pytest.raises(DisputeError) as error:
            run(
                service,
                case,
                action,
                {"decision": "PASS", "reason": "Try stale authority", "pii_checked": True},
                identity,
            )
        assert error.value.code == "CONTEST_NOT_ELIGIBLE"


def test_w10_w11_stage_uses_source_time_and_isolates_evidence_outcome(service):
    case = run(
        service, submitted(service), "RECORD_OUTCOME", outcome_data(disposition="NEXT_STAGE")
    )
    old_ids = [e["id"] for e in case["evidence"]]
    source = NOW + timedelta(days=1)
    service.clock = lambda: NOW + timedelta(days=3)
    case = run(
        service,
        case,
        "NEXT_STAGE",
        {
            "stage": "REPRESENTMENT",
            "event_id": uuid4().hex,
            "source": "mock-upstream",
            "occurred_at": source.isoformat(),
            "received_at": source.isoformat(),
        },
    )
    assert case["deadlines"]["external"] == (source + timedelta(days=5)).isoformat()
    assert case["business_outcome"] == "UNKNOWN" and case["last_known_outcome"] == "LOST"
    assert case_plan(case)["missing_required"]
    case = run(
        service,
        case,
        "REUSE_EVIDENCE",
        {"evidence_ids": old_ids, "reason": "Content remains applicable"},
        RISK,
    )
    assert not case_plan(case)["missing_required"]


def test_w10_missing_source_time_requires_confirmation(service):
    case = run(
        service, submitted(service), "RECORD_OUTCOME", outcome_data(disposition="NEXT_STAGE")
    )
    case = run(
        service,
        case,
        "NEXT_STAGE",
        {"stage": "REPRESENTMENT", "event_id": uuid4().hex, "source": "mock-upstream"},
    )
    assert case["deadlines"]["status"] == "NEEDS_CONFIRMATION"


def test_w12_accept_requires_mock_channel_processing(service):
    case = run(
        service,
        run(service, intake(service), "PUBLISH_TASK"),
        "MERCHANT_DECISION",
        {"decision": "ACCEPT", "reason": "Accept responsibility"},
        MERCHANT,
    )
    assert case["work_status"] == "ACCEPT_PROCESSING" and case["finality"] == "NOT_FINAL"
    case = run(
        service,
        case,
        "PROCESS_ACCEPT",
        {
            "mode": "MOCK",
            "reason": "Checked ledger and authorization",
            "reference": "channel-accept",
        },
    )
    assert case["acceptances"][-1]["business_acceptance"] == "MOCK_ACCEPTED"
    assert case["work_status"] == "WAITING_UPSTREAM" and not case["financial_events"]


def test_w13_terminal_cancels_evidence_not_independent_required_tasks(service):
    case = contest(service)
    case = run(
        service,
        case,
        "RECORD_OUTCOME",
        outcome_data(outcome="WITHDRAWN", final=True, basis_reference="source"),
    )
    case = run(
        service,
        case,
        "VERIFY_OUTCOME",
        {
            "event_id": case["upstream_events"][-1]["event_id"],
            "decision": "CONFIRM",
            "reason": "Verified withdrawal",
            "authorization_reference": "risk-check",
        },
        RISK,
    )
    task = next(t for t in case["tasks"] if t["type"] == "EVIDENCE")
    assert task["status"] == "CANCELLED" and task["resolution"]["actor_id"] == RISK["actor_id"]
    assert task["resolution"]["revision"] == case["revision"]


def test_w14_accept_only_rule_does_not_require_contest_materials(service):
    case = run(
        service,
        intake(service, channel="CUSTOM"),
        "CONFIRM_RULE",
        rule_data(allowed_actions=["ACCEPT"], required_evidence=[]),
        RISK,
    )
    assert case["rule_snapshot"]["required_evidence"] == []
    assert run(service, case, "PUBLISH_TASK")["work_status"] == "MERCHANT_ACTION_REQUIRED"


@pytest.mark.parametrize(
    "scenario", ["TIMEOUT", "RESPONSE_LOST", "TECHNICAL_FAILURE", "BUSINESS_REJECTED"]
)
def test_x03_uncertain_submission_queries_before_any_resend(service, scenario):
    case = run(service, frozen(service), "SUBMIT", {"mock_scenario": scenario})
    request = case["submissions"][-1]["request_id"]
    with pytest.raises(DisputeError):
        run(service, case, "SUBMIT")
    result = "ACCEPTED" if scenario == "RESPONSE_LOST" else "NOT_ACCEPTED"
    case = run(
        service,
        case,
        "QUERY_SUBMISSION",
        {"request_id": request, "result": result, "reason": "Queried channel request identity"},
    )
    if result == "ACCEPTED":
        assert case["work_status"] == "WAITING_UPSTREAM" and len(case["submissions"]) == 1
    else:
        case = run(service, case, "SUBMIT")
        assert case["submissions"][-1]["request_id"] == request and len(case["submissions"]) == 1
        assert len(case["submissions"][-1]["attempts"]) == 2


def test_f01_partial_amounts_and_notification_versions(service):
    case = run(
        service,
        submitted(service),
        "RECORD_OUTCOME",
        outcome_data(
            outcome="PARTIAL", final=True, supported_minor=7500, liable_minor=5000, currency="USD"
        ),
    )
    assert case["financial_summary"]["disputed_minor"] == 12500
    assert case["financial_summary"]["liable_minor"] == 5000
    with pytest.raises(DisputeError):
        run(
            service,
            submitted(service),
            "RECORD_OUTCOME",
            outcome_data(
                outcome="PARTIAL",
                final=True,
                supported_minor=7500,
                liable_minor=4000,
                currency="USD",
            ),
        )


def test_w01_restoration_rejects_expired_rights_and_preserves_decision(service):
    case = run(service, intake(service), "PUBLISH_TASK")
    service.clock = lambda: NOW + timedelta(days=6)
    case = run(
        service,
        case,
        "MERCHANT_DECISION",
        {"decision": "NO_RESPONSE", "reason": "No valid response"},
    )
    before = service.get_case(case["id"], OP)
    with pytest.raises(DisputeError) as error:
        run(
            service,
            case,
            "RESOLVE_RESPONSE",
            {
                "resolution": "RESTORE_DECISION",
                "reason": "Attempt expired rights",
                "authorization_reference": "source",
                "external_deadline": (NOW + timedelta(days=5)).isoformat(),
            },
            RISK,
        )
    assert error.value.code == "EXTERNAL_DEADLINE_EXPIRED"
    assert service.get_case(case["id"], OP) == before
    case = run(
        service,
        case,
        "RESOLVE_RESPONSE",
        {
            "resolution": "CONFIRM_LOSS",
            "reason": "Channel confirms rights expired",
            "authorization_reference": "source",
        },
        RISK,
    )
    assert case["eligibility_status"] == "RIGHTS_LOST" and case["finality"] == "NOT_FINAL"


def test_w04_document_return_preserves_evidence_review_but_requires_new_final_review(service):
    case = run(service, reviewed(service), "BUILD_PACKAGE")
    first = case["packages"][-1]["id"]
    case = run(
        service,
        case,
        "FINAL_REVIEW",
        {"decision": "RETURN_DOCUMENT", "reason": "Correct document prose"},
        SUPERVISOR,
    )
    assert any(r["type"] == "EVIDENCE" and r["valid"] for r in case["reviews"])
    case = run(service, case, "BUILD_PACKAGE", {"draft": "Corrected response"})
    assert case["packages"][-1]["id"] != first
    with pytest.raises(DisputeError):
        run(service, case, "SUBMIT")
    case = run(
        service,
        case,
        "FINAL_REVIEW",
        {"decision": "APPROVE", "pii_checked": True, "reason": "Rechecked corrected package"},
        SUPERVISOR,
    )
    assert run(service, case, "SUBMIT")["work_status"] == "WAITING_UPSTREAM"


def test_w04_hold_can_return_document_but_cannot_directly_approve_invalidated_package(service):
    case = run(service, reviewed(service), "BUILD_PACKAGE")
    case = run(
        service,
        case,
        "FINAL_REVIEW",
        {"decision": "HOLD", "reason": "Need supervisor clarification"},
        SUPERVISOR,
    )
    with pytest.raises(DisputeError):
        run(
            service,
            case,
            "FINAL_REVIEW",
            {"decision": "APPROVE", "pii_checked": True, "reason": "Try direct held approval"},
            SUPERVISOR,
        )
    case = run(
        service,
        case,
        "FINAL_REVIEW",
        {"decision": "RETURN_DOCUMENT", "reason": "Clarified required correction"},
        SUPERVISOR,
    )
    assert case["work_status"] == "DOCUMENT_REVISION_REQUIRED"


def test_w05_action_disposition_stays_same_stage_and_has_followup_exit(service):
    case = run(service, submitted(service), "RECORD_OUTCOME", outcome_data(disposition="ACTION"))
    assert case["work_status"] == "UPSTREAM_ACTION_REQUIRED" and case["stage_number"] == 1
    case = run(
        service,
        case,
        "RESOLVE_RESPONSE",
        {
            "resolution": "FOLLOW_UP",
            "reason": "Source action requires follow-up",
            "authorization_reference": "source-confirmation",
        },
        RISK,
    )
    assert case["work_status"] == "WAITING_UPSTREAM"


def test_w06_mapped_custom_outcome_requires_risk_verification(service):
    case = run(
        service,
        submitted(service),
        "RECORD_OUTCOME",
        outcome_data(
            outcome="OTHER",
            final=True,
            mapped_outcome="WITHDRAWN",
            basis_reference="custom-source-mapping",
            authorization_reference="authorized-source",
        ),
    )
    assert case["work_status"] == "OUTCOME_VERIFICATION" and case["finality"] == "NOT_FINAL"
    case = run(
        service,
        case,
        "VERIFY_OUTCOME",
        {
            "event_id": case["upstream_events"][-1]["id"],
            "decision": "CONFIRM",
            "reason": "Verified custom mapping",
            "authorization_reference": "risk-source",
        },
        RISK,
    )
    assert (
        case["business_outcome"] == "OTHER"
        and case["outcome_mapping"]["mapped_outcome"] == "WITHDRAWN"
    )
    assert case["finality"] == "FINAL_CONFIRMED"


def test_w07_wrong_stage_event_can_be_rejected_but_never_decides_current_stage(service):
    case = contest(service)
    case = run(
        service,
        case,
        "RECORD_OUTCOME",
        outcome_data(outcome="WITHDRAWN", final=True, stage_number=2, basis_reference="source"),
    )
    event = case["upstream_events"][-1]["id"]
    with pytest.raises(DisputeError) as error:
        run(
            service,
            case,
            "VERIFY_OUTCOME",
            {
                "event_id": event,
                "decision": "CONFIRM",
                "reason": "Check current stage",
                "authorization_reference": "risk-source",
            },
            RISK,
        )
    assert error.value.code == "EVENT_STAGE_MISMATCH"
    case = run(
        service,
        case,
        "VERIFY_OUTCOME",
        {
            "event_id": event,
            "decision": "REJECT",
            "reason": "Source event belongs to another stage",
            "authorization_reference": "risk-source",
        },
        RISK,
    )
    assert case["work_status"] == "EVIDENCE_COLLECTING" and case["business_outcome"] == "UNKNOWN"


def test_w07_multiple_pending_events_do_not_restore_preterminal_state_after_confirmation(service):
    case = contest(service)
    case = run(service, case, "RECORD_OUTCOME", outcome_data(outcome="WITHDRAWN", final=True))
    event = case["upstream_events"][-1]["id"]
    case = run(service, case, "RECORD_OUTCOME", outcome_data(outcome="UNKNOWN", final=False))
    other = case["upstream_events"][-1]["id"]
    case = run(
        service,
        case,
        "VERIFY_OUTCOME",
        {
            "event_id": event,
            "decision": "CONFIRM",
            "reason": "Verify withdrawal",
            "authorization_reference": "risk-source",
        },
        RISK,
    )
    assert case["work_status"] == "OUTCOME_VERIFICATION"
    case = run(
        service,
        case,
        "VERIFY_OUTCOME",
        {
            "event_id": other,
            "decision": "REJECT",
            "reason": "Reject outdated unknown notice",
            "authorization_reference": "risk-source",
        },
        RISK,
    )
    assert (
        case["work_status"] == "FINANCIAL_RECONCILIATION" and case["finality"] == "FINAL_CONFIRMED"
    )


def test_w09_rule_change_invalidates_frozen_package_even_when_contest_remains_allowed(service):
    case = frozen(service)
    case = run(service, case, "CONFIRM_RULE", rule_data(), RISK)
    assert case["packages"][-1]["status"] == "INVALIDATED" and not any(
        r["valid"] for r in case["reviews"]
    )
    assert case["rule_history"][-1]["snapshot"]["rule_version"] != "v21"
    with pytest.raises(DisputeError):
        run(service, case, "SUBMIT")


def test_w12_mock_disabled_and_no_action_basis_are_explicit(service):
    case = run(
        service,
        run(service, intake(service), "PUBLISH_TASK"),
        "MERCHANT_DECISION",
        {"decision": "ACCEPT", "reason": "Accept responsibility"},
        MERCHANT,
    )
    service.upstream_mode = "disabled"
    with pytest.raises(DisputeError) as error:
        run(
            service,
            case,
            "PROCESS_ACCEPT",
            {"mode": "MOCK", "reason": "Confirm channel action", "reference": "channel-source"},
        )
    assert error.value.code == "UPSTREAM_DISABLED"
    case = run(
        service,
        case,
        "PROCESS_ACCEPT",
        {
            "mode": "NO_ACTION_REQUIRED",
            "reason": "Confirmed guideline requires no channel call",
            "reference": "manual-no-action-guideline",
        },
    )
    assert (
        case["acceptances"][-1]["mode"] == "NO_ACTION_REQUIRED" and case["finality"] == "NOT_FINAL"
    )


def test_w12_accept_lost_response_queries_same_request_without_financial_event(service):
    case = run(
        service,
        run(service, intake(service), "PUBLISH_TASK"),
        "MERCHANT_DECISION",
        {"decision": "ACCEPT", "reason": "Accept responsibility"},
        MERCHANT,
    )
    case = run(
        service,
        case,
        "PROCESS_ACCEPT",
        {
            "mode": "MOCK",
            "mock_scenario": "RESPONSE_LOST",
            "reason": "Check authorization and channel",
            "reference": "channel-source",
        },
    )
    request = case["acceptances"][-1]["request_id"]
    with pytest.raises(DisputeError):
        run(
            service,
            case,
            "PROCESS_ACCEPT",
            {"mode": "MOCK", "reason": "Try sending again", "reference": "channel-source"},
        )
    case = run(
        service,
        case,
        "QUERY_SUBMISSION",
        {"request_id": request, "result": "ACCEPTED", "reason": "Query original channel identity"},
    )
    assert len(case["acceptances"]) == 1 and not case["financial_events"]


@pytest.mark.parametrize("resolution", ["CANCELLED", "WAIVED", "SUPERSEDED"])
def test_w13_task_resolution_is_truthful_and_cannot_waive_review_authority(service, resolution):
    case = contest(service)
    task = next(t for t in case["tasks"] if t["status"] == "OPEN")
    if resolution == "SUPERSEDED":
        service.clock = lambda: NOW + timedelta(days=4)
        case = run(service, case, "MONITOR_SLA")
        replacement = next(t["id"] for t in case["tasks"] if t["type"] == "EVIDENCE_OVERDUE")
    else:
        replacement = None
    data = {
        "task_id": task["id"],
        "resolution": resolution,
        "reason": "Supervisor documented exception",
    }
    if replacement:
        data["replacement_task_id"] = replacement
    case = run(service, case, "RESOLVE_TASK", data, SUPERVISOR)
    resolved = next(t for t in case["tasks"] if t["id"] == task["id"])
    assert (
        resolved["status"] == resolution
        and resolved["resolution"]["actor_id"] == SUPERVISOR["actor_id"]
    )
    # A waived task is not evidence, and does not satisfy the evidence submission gate.
    with pytest.raises(DisputeError):
        run(service, case, "SUBMIT_EVIDENCE", identity=MERCHANT)


def test_task_real_assignee_is_selected_from_case_participants(service):
    case = intake(service)
    current = service.store.get_case(case["id"])

    class Policy:
        def case_participants(self, case):
            return [{"user_id": "real-op", "role": "OPERATOR", "display_name": "Assigned operator"}]

        def can_access(self, case, identity):
            return True

        def require_case(self, case, identity):
            pass

    service.access_policy = Policy()
    with pytest.raises(DisputeError):
        run(
            service,
            case,
            "ASSIGN_CASE",
            {"user_id": "invented-user", "reason": "Try arbitrary assignment"},
            SUPERVISOR,
        )
    assert service.store.get_case(case["id"]) == current
    case = run(
        service,
        case,
        "ASSIGN_CASE",
        {"user_id": "real-op", "reason": "Assign accountable operator"},
        SUPERVISOR,
    )
    assert case["assigned_op_user_id"] == "real-op"


def test_f01_ledger_summary_preserves_separate_refund_fee_and_net(service):
    case = run(
        service,
        submitted(service),
        "RECORD_OUTCOME",
        outcome_data(
            outcome="PARTIAL", final=True, supported_minor=7500, liable_minor=5000, currency="USD"
        ),
    )
    for kind, amount in [("DEBIT", 5000), ("FEE", 100), ("REFUND", 200), ("CREDIT", 50)]:
        case = run(
            service,
            case,
            "RECORD_FINANCIAL",
            {
                "event_id": uuid4().hex,
                "source": "mock-ledger",
                "kind": kind,
                "amount_minor": amount,
                "currency": "USD",
                "reference": "source-row",
            },
        )
    summary = case["financial_summary"]
    assert summary["net_minor"] == -5250
    assert (
        summary["liable_minor"] == 5000
        and summary["refund_minor"] == 200
        and summary["fee_minor"] == 100
    )
    case = run(
        service,
        case,
        "RECONCILE",
        {
            "status": "RECONCILED",
            "expected_net_minor": -5250,
            "reason": "Match synthetic ledger",
            "reference": "synthetic-ledger-report",
        },
        SUPERVISOR,
    )
    case = run(service, case, "NOTIFY_MERCHANT")
    assert case["merchant_notification"]["outcome_version"] == case["outcome_version"]
    case = run(
        service,
        case,
        "RECORD_FINANCIAL",
        {
            "event_id": uuid4().hex,
            "source": "mock-ledger",
            "kind": "FEE",
            "amount_minor": 10,
            "currency": "USD",
            "reference": "new-source-row",
        },
    )
    assert not case["merchant_notification_completed"]
    with pytest.raises(DisputeError):
        run(service, case, "CLOSE", identity=SUPERVISOR)


def test_v21_commands_have_same_cas_confirmation_and_replay_boundary(service):
    from tests.workflow.test_dispute_engine import command

    case = run(service, reviewed(service), "BUILD_PACKAGE")
    cmd = command(
        case, "FINAL_REVIEW", {"decision": "RETURN_DOCUMENT", "reason": "Document needs correction"}
    )
    with pytest.raises(DisputeError):
        service.execute(cmd | {"confirmed": False}, SUPERVISOR)
    applied = service.execute(cmd, SUPERVISOR)
    replay = service.execute(cmd, SUPERVISOR)
    assert replay["replayed"] and replay["receipt"] == applied["receipt"]
    with pytest.raises(DisputeError) as reused:
        service.execute(
            cmd | {"data": cmd["data"] | {"reason": "Changed review instruction"}}, SUPERVISOR
        )
    assert reused.value.code == "COMMAND_CONFLICT"
    with pytest.raises(DisputeError) as stale:
        service.execute(cmd | {"command_id": uuid4().hex}, SUPERVISOR)
    assert stale.value.code == "REVISION_CONFLICT"


@pytest.mark.parametrize(
    "field,value",
    [
        ("disposition", []),
        ("mapped_outcome", {}),
        ("reason", []),
        ("next_stage", []),
        ("stage_number", True),
        ("occurred_at", "not-date"),
        ("supported_minor", True),
    ],
)
def test_v21_outcome_invalid_input_never_partially_mutates(service, field, value):
    case = submitted(service)
    before = service.get_case(case["id"], OP)
    with pytest.raises(DisputeError) as error:
        run(service, case, "RECORD_OUTCOME", outcome_data(**{field: value}))
    assert error.value.status == 422
    assert service.get_case(case["id"], OP) == before


def test_legacy_http_submit_dto_does_not_add_fields_to_old_command_fingerprint():
    from oceanpilot.api.dispute_commands_v21 import DATA_MODELS

    assert DATA_MODELS["SUBMIT"].model_validate({}).model_dump(exclude_none=True) == {}


def test_file_object_is_bound_to_case_and_checklist_code(service):
    case = contest(service)
    oid = uuid4().hex
    code = case["rule_snapshot"]["required_evidence"][0]

    class Objects:
        def get_evidence_object(self, case_id, object_id):
            return {
                "object_id": oid,
                "case_id": case_id,
                "code": code,
                "sha256": "synthetic-digest",
                "content_check": {"status": "SUPPORTED", "findings": [], "locators": ["line 1"]},
            }

    service.evidence_objects = Objects()
    payload = {"code": code, "title": "Actual file", "reference": f"object:{oid}"}
    with pytest.raises(DisputeError) as mismatch:
        run(service, case, "REGISTER_EVIDENCE", payload | {"code": "different-code"}, MERCHANT)
    assert mismatch.value.code == "EVIDENCE_OBJECT_CODE_MISMATCH"
    case = run(service, case, "REGISTER_EVIDENCE", payload, MERCHANT)
    assert (
        case["evidence"][-1]["object_id"] == oid
        and case["evidence"][-1]["sha256"] == "synthetic-digest"
    )


def test_supported_code_does_not_hide_an_insufficient_active_file(service):
    case = contest(service)
    code = case["rule_snapshot"]["required_evidence"][0]

    # Historical metadata can remain readable after file enforcement is enabled;
    # it must never conceal a newly registered, insufficient actual file.
    for required in case["rule_snapshot"]["required_evidence"]:
        case = run(
            service,
            case,
            "REGISTER_EVIDENCE",
            {"code": required, "title": "Legacy metadata", "reference": "synthetic://metadata"},
            MERCHANT,
        )

    class Objects:
        def get_evidence_object(self, case_id, object_id):
            return {
                "object_id": object_id,
                "case_id": case_id,
                "code": code,
                "sha256": "digest",
                "content_check": {
                    "status": "INSUFFICIENT",
                    "findings": ["Missing delivery confirmation"],
                    "locators": ["line 2"],
                },
            }

    service.evidence_objects = Objects()
    case = run(
        service,
        case,
        "REGISTER_EVIDENCE",
        {"code": code, "title": "Insufficient file", "reference": f"object:{uuid4().hex}"},
        MERCHANT,
    )
    with pytest.raises(DisputeError) as error:
        run(service, case, "SUBMIT_EVIDENCE", identity=MERCHANT)
    assert error.value.code == "CONTENT_CHECK_REQUIRED"


def test_evidence_change_supersedes_review_task_without_claiming_it_completed(service):
    case = fill(service, contest(service))
    old = next(t["id"] for t in case["tasks"] if t["type"] == "OP_REVIEW" and t["status"] == "OPEN")
    evidence = case["evidence"][0]
    case = run(
        service,
        case,
        "REGISTER_EVIDENCE",
        {
            "code": evidence["code"],
            "title": "Revised source",
            "reference": "synthetic://revised",
            "evidence_id": evidence["id"],
        },
        MERCHANT,
    )
    assert next(t for t in case["tasks"] if t["id"] == old)["status"] == "SUPERSEDED"
    case = run(service, case, "SUBMIT_EVIDENCE", identity=MERCHANT)
    assert any(
        t["type"] == "OP_REVIEW" and t["status"] == "OPEN" and t["id"] != old for t in case["tasks"]
    )


def test_ui_gate_and_execution_reject_the_same_stale_rule_authority(service):
    from oceanpilot.domain.dispute_actions import action_gate

    case = contest(service)
    case = run(
        service,
        case,
        "CONFIRM_RULE",
        rule_data(allowed_actions=["ACCEPT"], required_evidence=[]),
        RISK,
    )
    for action, identity in [
        ("REGISTER_EVIDENCE", MERCHANT),
        ("SUBMIT_EVIDENCE", MERCHANT),
        ("REVIEW", RISK),
        ("BUILD_PACKAGE", OP),
        ("APPROVE_PACKAGE", SUPERVISOR),
        ("SUBMIT", OP),
    ]:
        gate = action_gate(case, action, identity, NOW)
        assert not gate["enabled"]
        with pytest.raises(DisputeError) as error:
            run(service, case, action, {}, identity)
        assert error.value.code == gate["code"]
    choices = action_gate(case, "MERCHANT_DECISION", MERCHANT, NOW)["choices"]
    assert choices == ["ACCEPT"]


def test_submission_unknown_then_expired_window_prevents_retry(service):
    case = run(service, frozen(service), "SUBMIT", {"mock_scenario": "TIMEOUT"})
    request = case["submissions"][-1]["request_id"]
    case = run(
        service,
        case,
        "QUERY_SUBMISSION",
        {"request_id": request, "result": "UNKNOWN", "reason": "No channel answer yet"},
    )
    assert case["work_status"] == "SUBMISSION_UNCERTAIN"
    case = run(
        service,
        case,
        "QUERY_SUBMISSION",
        {"request_id": request, "result": "NOT_ACCEPTED", "reason": "Confirmed request absent"},
    )
    service.clock = lambda: NOW + timedelta(days=6)
    with pytest.raises(DisputeError) as error:
        run(service, case, "SUBMIT")
    assert error.value.code == "EXTERNAL_DEADLINE_EXPIRED"
    assert len(case["submissions"][0]["attempts"]) == 1


def test_concurrent_new_workflow_commands_have_one_winner(service):
    from concurrent.futures import ThreadPoolExecutor

    from tests.workflow.test_dispute_engine import command

    case = run(service, reviewed(service), "BUILD_PACKAGE")
    commands = [
        command(case, "FINAL_REVIEW", {"decision": decision, "reason": "Supervisor decision"})
        for decision in ["RETURN_DOCUMENT", "HOLD"]
    ]

    def apply(cmd):
        try:
            return service.execute(cmd, SUPERVISOR)
        except DisputeError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply, commands))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert "REVISION_CONFLICT" in results
    assert service.get_case(case["id"], OP)["revision"] == case["revision"] + 1


def test_reopened_case_cannot_skip_correction_relationship(service):
    case = run(
        service, run(service, reconciled(service), "NOTIFY_MERCHANT"), "CLOSE", identity=SUPERVISOR
    )
    case = run(
        service,
        case,
        "REOPEN_CASE",
        {
            "reason": "Source correction needs verification",
            "authorization_reference": "supervisor-source",
            "event_reference": "replacement-event",
        },
        SUPERVISOR,
    )
    with pytest.raises(DisputeError) as error:
        run(service, case, "RECORD_OUTCOME", outcome_data(outcome="LOST", final=True))
    assert error.value.code == "CORRECTION_BASIS_REQUIRED"


def test_stage_deadline_anchor_comes_from_new_stage_rule_not_previous_stage(service):
    from oceanpilot.domain.dispute_rules import match_rule

    case = run(
        service, submitted(service), "RECORD_OUTCOME", outcome_data(disposition="NEXT_STAGE")
    )

    def matcher(scheme, channel, reason, stage, at):
        rule = match_rule(scheme, channel, reason, stage, at)
        if stage == "REPRESENTMENT":
            rule["deadline_policy"]["anchor_field"] = "occurred_at"
        return rule

    service.rule_matcher = matcher
    occurred = NOW + timedelta(days=1)
    received = NOW + timedelta(days=2)
    service.clock = lambda: NOW + timedelta(days=3)
    case = run(
        service,
        case,
        "NEXT_STAGE",
        {
            "stage": "REPRESENTMENT",
            "event_id": uuid4().hex,
            "source": "mock-upstream",
            "occurred_at": occurred.isoformat(),
            "received_at": received.isoformat(),
        },
    )
    assert case["stage_time_basis"]["basis"] == "occurred_at"
    assert case["deadlines"]["external"] == (occurred + timedelta(days=5)).isoformat()


def test_stage_missing_rule_required_received_time_does_not_substitute_occurred_time(service):
    case = run(
        service, submitted(service), "RECORD_OUTCOME", outcome_data(disposition="NEXT_STAGE")
    )
    case = run(
        service,
        case,
        "NEXT_STAGE",
        {
            "stage": "REPRESENTMENT",
            "event_id": uuid4().hex,
            "source": "mock-upstream",
            "occurred_at": NOW.isoformat(),
        },
    )
    assert case["stage_time_basis"]["anchor"] is None
    assert case["deadlines"]["status"] == "NEEDS_CONFIRMATION"
