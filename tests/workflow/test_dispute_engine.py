import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.disputes import DisputeError, DisputeService

OP = {"role": "OPERATOR", "actor_id": "operator-1"}
RISK = {"role": "RISK_OFFICER", "actor_id": "risk-1"}
SUPERVISOR = {"role": "SUPERVISOR", "actor_id": "supervisor-1"}
ADMIN = {"role": "ADMIN", "actor_id": "admin-1"}
AGENT = {"role": "AGENT", "actor_id": "agent-1"}
MERCHANT = {"role": "MERCHANT", "actor_id": "merchant-user", "merchant_id": "merchant-a"}
OTHER_MERCHANT = {"role": "MERCHANT", "actor_id": "other-user", "merchant_id": "merchant-b"}
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


@pytest.fixture
def service(tmp_path):
    return DisputeService(SQLiteDisputeStore(tmp_path / "shared.db"), clock=lambda: NOW)


def command(case, action, data=None, *, command_id=None, confirmed=True):
    return {
        "command_id": command_id or uuid4().hex,
        "action": action,
        "case_id": case["id"],
        "expected_revision": case["revision"],
        "confirmed": confirmed,
        "data": data or {},
    }


def run(service, case, action, data=None, identity=OP, **kwargs):
    return service.execute(command(case, action, data, **kwargs), identity)["case"]


def intake_command(**overrides):
    data = {
        "merchant_id": "merchant-a",
        "transaction_id": "transaction-1",
        "scheme": "VISA",
        "channel": "MOCK",
        "reason_code": "13.1",
        "amount_minor": 12500,
        "currency": "USD",
        "event_id": uuid4().hex,
    }
    data.update(overrides)
    return {"command_id": uuid4().hex, "action": "INTAKE", "confirmed": True, "data": data}


def intake(service, **overrides):
    return service.execute(intake_command(**overrides), OP)["case"]


def contest(service):
    case = intake(service)
    case = run(service, case, "PUBLISH_TASK")
    return run(
        service,
        case,
        "MERCHANT_DECISION",
        {"decision": "CONTEST", "reason": "Have proof"},
        MERCHANT,
    )


def reviewed(service):
    case = contest(service)
    for code in case["rule_snapshot"]["required_evidence"]:
        case = run(
            service,
            case,
            "REGISTER_EVIDENCE",
            {
                "code": code,
                "title": code,
                "reference": "synthetic://evidence/example",
            },
            MERCHANT,
        )
    case = run(service, case, "SUBMIT_EVIDENCE", identity=MERCHANT)
    return run(service, case, "REVIEW", {"decision": "PASS", "reason": "Content checked"}, RISK)


def frozen(service):
    case = reviewed(service)
    case = run(service, case, "BUILD_PACKAGE", identity=AGENT)
    return run(
        service,
        case,
        "APPROVE_PACKAGE",
        {"reason": "Final checked", "pii_checked": True},
        SUPERVISOR,
    )


def submitted(service):
    return run(service, frozen(service), "SUBMIT")


def terminal(service):
    return run(
        service,
        submitted(service),
        "RECORD_OUTCOME",
        {
            "event_id": uuid4().hex,
            "outcome": "WON",
            "final": True,
            "source": "mock-upstream",
        },
    )


def reconciled(service):
    case = terminal(service)
    case = run(
        service,
        case,
        "RECORD_FINANCIAL",
        {
            "event_id": uuid4().hex,
            "kind": "CREDIT",
            "amount_minor": 12500,
            "currency": "USD",
            "source": "mock-ledger",
            "reference": "L-1",
        },
    )
    return run(
        service,
        case,
        "RECONCILE",
        {
            "status": "RECONCILED",
            "expected_net_minor": 12500,
            "reason": "Matched settlement report",
            "reference": "reconciliation-1",
        },
        SUPERVISOR,
    )


def test_golden_contest_closes_only_after_reconciled_and_notified(service):
    case = reconciled(service)
    assert case["merchant_notification_completed"] is False
    with pytest.raises(DisputeError) as missing_notification:
        run(service, case, "CLOSE", identity=SUPERVISOR)
    assert missing_notification.value.code == "CLOSE_BLOCKED"
    case = run(service, case, "NOTIFY_MERCHANT")
    case = run(service, case, "CLOSE", identity=SUPERVISOR)
    assert case["owner"] == "OCEANPAYMENT"
    assert case["work_status"] == "CLOSED"
    assert case["merchant_decision"] == "CONTEST"
    assert case["business_outcome"] == "WON"
    assert case["finality"] == "FINAL_CONFIRMED"
    assert case["financial_status"] == "RECONCILED"
    assert case["submissions"][0]["mode"] == "MOCK"
    assert case["submissions"][0]["business_acceptance"] == "MOCK_ACCEPTED"
    assert len(case["audit"]) == case["revision"]
    assert [a["revision"] for a in case["audit"]] == list(range(1, case["revision"] + 1))


@pytest.mark.parametrize("identity", [MERCHANT, AGENT, ADMIN, RISK, SUPERVISOR])
def test_only_operator_can_intake(service, identity):
    with pytest.raises(DisputeError) as error:
        service.execute(intake_command(), identity)
    assert error.value.status == 403
    assert service.list_cases(OP) == []


def test_merchant_scope_is_enforced_for_reads_and_mutations(service):
    case = intake(service)
    assert service.list_cases(OTHER_MERCHANT) == []
    with pytest.raises(DisputeError) as error:
        service.get_case(case["id"], OTHER_MERCHANT)
    assert error.value.status == 404
    with pytest.raises(DisputeError) as error:
        run(service, case, "COMMENT", {"message": "probe"}, OTHER_MERCHANT)
    assert error.value.status == 404
    assert service.get_case(case["id"], OP)["revision"] == 1


@pytest.mark.parametrize(
    "action,identity",
    [
        ("REVIEW", OP),
        ("APPROVE_PACKAGE", RISK),
        ("APPROVE_PACKAGE", MERCHANT),
        ("SUBMIT", MERCHANT),
        ("SUBMIT", AGENT),
        ("RECONCILE", OP),
        ("CLOSE", ADMIN),
        ("CONFIRM_RULE", ADMIN),
        ("PUBLISH_TASK", AGENT),
    ],
)
def test_business_roles_do_not_inherit_each_others_privileges(service, action, identity):
    case = intake(service)
    with pytest.raises(DisputeError) as error:
        run(service, case, action, identity=identity)
    assert error.value.status == 403


def test_unknown_rule_requires_explicit_source_version_deadline_and_evidence(service):
    case = intake(service, channel="UNKNOWN_ACQUIRER")
    assert case["rule_snapshot"]["conflict_status"] == "NEEDS_CONFIRMATION"
    with pytest.raises(DisputeError) as error:
        run(service, case, "PUBLISH_TASK")
    assert error.value.code == "RULE_CONFIRMATION_REQUIRED"
    with pytest.raises(DisputeError):
        run(service, case, "CONFIRM_RULE", {"reason": "Looks right"}, RISK)
    case = run(
        service,
        case,
        "CONFIRM_RULE",
        {
            "source_id": "confirmed-demo-sop",
            "source_locator": "manual-demo-section-1",
            "rule_version": "demo-v1",
            "external_deadline": "2026-09-13T12:00:00Z",
            "merchant_deadline": "2026-09-11T12:00:00Z",
            "required_evidence": ["transaction.receipt"],
            "allowed_actions": ["ACCEPT", "CONTEST"],
            "reason": "Reviewed demo source",
        },
        RISK,
    )
    assert case["rule_snapshot"]["production_eligible"] is False
    assert run(service, case, "PUBLISH_TASK")["work_status"] == "MERCHANT_ACTION_REQUIRED"


def test_missing_evidence_cannot_pass_review_or_build_package(service):
    case = contest(service)
    for action, identity in [
        ("SUBMIT_EVIDENCE", MERCHANT),
        ("REVIEW", RISK),
        ("BUILD_PACKAGE", AGENT),
    ]:
        with pytest.raises(DisputeError):
            run(service, case, action, {"decision": "PASS", "reason": "approve"}, identity)
    assert service.get_case(case["id"], OP)["revision"] == case["revision"]


def test_evidence_edit_invalidates_both_reviews_and_preserves_frozen_content(service):
    case = frozen(service)
    old_package = deepcopy(case["packages"][0])
    evidence = case["evidence"][0]
    case = run(
        service,
        case,
        "REGISTER_EVIDENCE",
        {
            "evidence_id": evidence["id"],
            "code": evidence["code"],
            "title": "Corrected evidence",
            "reference": "synthetic://replacement",
        },
        MERCHANT,
    )
    assert all(not review["valid"] for review in case["reviews"])
    assert case["packages"][0]["status"] == "INVALIDATED"
    assert case["packages"][0]["digest"] == old_package["digest"]
    assert case["packages"][0]["evidence_index"] == old_package["evidence_index"]
    with pytest.raises(DisputeError):
        run(service, case, "SUBMIT")


def test_withdrawn_evidence_cannot_satisfy_the_checklist(service):
    case = reviewed(service)
    case = run(
        service,
        case,
        "WITHDRAW_EVIDENCE",
        {
            "evidence_id": case["evidence"][0]["id"],
            "reason": "Incorrect record",
        },
        MERCHANT,
    )
    with pytest.raises(DisputeError) as error:
        run(service, case, "SUBMIT_EVIDENCE", identity=MERCHANT)
    assert error.value.code == "MISSING_EVIDENCE"


def test_two_distinct_humans_required_and_pii_gate(service):
    case = run(service, reviewed(service), "BUILD_PACKAGE")
    with pytest.raises(DisputeError) as error:
        run(
            service,
            case,
            "APPROVE_PACKAGE",
            {"reason": "approve", "pii_checked": True},
            {"role": "SUPERVISOR", "actor_id": RISK["actor_id"]},
        )
    assert error.value.code == "REVIEWER_SEPARATION_REQUIRED"
    with pytest.raises(DisputeError) as error:
        run(service, case, "APPROVE_PACKAGE", {"reason": "approve"}, SUPERVISOR)
    assert error.value.code == "PII_REVIEW_REQUIRED"


def test_command_confirmation_and_cas_are_required(service):
    case = intake(service)
    with pytest.raises(DisputeError) as error:
        run(service, case, "PUBLISH_TASK", confirmed=False)
    assert error.value.code == "CONFIRMATION_REQUIRED"
    new = run(service, case, "PUBLISH_TASK")
    with pytest.raises(DisputeError) as error:
        run(service, case, "COMMENT", {"message": "stale plan"})
    assert error.value.code == "REVISION_CONFLICT"
    assert service.get_case(case["id"], OP)["revision"] == new["revision"]


def test_concurrent_commands_only_one_cas_succeeds(service):
    case = intake(service)
    commands = [command(case, "COMMENT", {"message": f"comment {i}"}) for i in range(8)]

    def execute(item):
        try:
            return service.execute(item, OP)
        except DisputeError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(execute, commands))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count("REVISION_CONFLICT") == 7
    assert service.get_case(case["id"], OP)["revision"] == 2


def test_concurrent_identical_command_replays_one_atomic_receipt(service):
    cmd = intake_command()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: service.execute(cmd, OP), range(6)))
    assert sum(not result["replayed"] for result in results) == 1
    assert len(service.list_cases(OP)) == 1
    assert len({result["receipt"]["audit_id"] for result in results}) == 1


def test_changed_command_id_payload_rejected_and_no_cross_actor_receipt(service):
    cmd = intake_command()
    service.execute(cmd, OP)
    altered = deepcopy(cmd)
    altered["data"]["amount_minor"] += 1
    with pytest.raises(DisputeError) as error:
        service.execute(altered, OP)
    assert error.value.code == "COMMAND_CONFLICT"
    with pytest.raises(DisputeError):
        service.execute(cmd, {"role": "OPERATOR", "actor_id": "another-operator"})


def test_duplicate_intake_event_does_not_create_duplicate_case(service):
    cmd = intake_command()
    first = service.execute(cmd, OP)
    duplicate = deepcopy(cmd)
    duplicate["command_id"] = uuid4().hex
    second = service.execute(duplicate, OP)
    assert second["replayed"] is True
    assert second["case"]["id"] == first["case"]["id"]
    assert len(service.list_cases(OP)) == 1


def test_submission_retry_preserves_receipt_and_rejects_evidence_changes(service):
    case = frozen(service)
    cmd = command(case, "SUBMIT")
    first = service.execute(cmd, OP)
    second = service.execute(cmd, OP)
    assert second["replayed"] is True
    assert first["receipt"] == second["receipt"]
    assert len(second["case"]["submissions"]) == 1
    with pytest.raises(DisputeError):
        run(
            service,
            first["case"],
            "REGISTER_EVIDENCE",
            {
                "code": "transaction.receipt",
                "title": "late",
                "reference": "synthetic://late",
            },
            MERCHANT,
        )


def test_disabled_upstream_cannot_submit(service):
    case = frozen(service)
    disabled = DisputeService(service.store, clock=lambda: NOW, upstream_mode="disabled")
    with pytest.raises(DisputeError) as error:
        run(disabled, case, "SUBMIT")
    assert error.value.code == "UPSTREAM_DISABLED"


def test_accept_is_authorized_but_neither_final_nor_financially_closed(service):
    case = run(service, intake(service), "PUBLISH_TASK")
    case = run(
        service,
        case,
        "MERCHANT_DECISION",
        {"decision": "ACCEPT", "reason": "Accept debit"},
        MERCHANT,
    )
    assert case["merchant_decision"] == "ACCEPT"
    assert case["business_outcome"] == "UNKNOWN"
    assert case["finality"] == "NOT_FINAL"
    with pytest.raises(DisputeError):
        run(service, case, "CLOSE", identity=SUPERVISOR)
    case = run(
        service,
        case,
        "PROCESS_ACCEPT",
        {"mode": "MOCK", "reason": "Reviewed authority and ledger", "reference": "mock-accept"},
    )
    case = run(
        service,
        case,
        "RECORD_OUTCOME",
        {
            "event_id": uuid4().hex,
            "source": "mock-upstream",
            "outcome": "ACCEPTED_RESPONSIBILITY",
            "final": True,
        },
    )
    assert case["work_status"] == "FINANCIAL_RECONCILIATION"


def test_no_response_requires_expired_deadline_and_never_means_accept(service):
    case = run(service, intake(service), "PUBLISH_TASK")
    data = {"decision": "NO_RESPONSE", "reason": "Remaining rights checked"}
    with pytest.raises(DisputeError) as error:
        run(service, case, "MERCHANT_DECISION", data)
    assert error.value.code == "DEADLINE_NOT_EXPIRED"
    late = DisputeService(service.store, clock=lambda: NOW + timedelta(days=4))
    case = run(late, case, "MONITOR_SLA", identity=AGENT)
    assert case["merchant_decision"] == "NONE"
    assert any(t["type"] == "SLA_ESCALATION" for t in case["tasks"])
    case = run(late, case, "MERCHANT_DECISION", data)
    assert case["merchant_decision"] == "NO_RESPONSE"
    assert case["business_outcome"] == "UNKNOWN"


def test_nonterminal_outcome_advances_stage_and_resets_reviews_and_rule(service):
    case = submitted(service)
    first_deadline = case["deadlines"]["external"]
    later = DisputeService(service.store, clock=lambda: NOW + timedelta(days=2))
    case = run(
        later,
        case,
        "RECORD_OUTCOME",
        {
            "event_id": uuid4().hex,
            "source": "mock-upstream",
            "outcome": "LOST",
            "final": False,
            "next_stage": "REPRESENTMENT",
            "received_at": (NOW + timedelta(days=2)).isoformat(),
        },
    )
    assert case["stage"] == "REPRESENTMENT"
    assert case["stage_number"] == 2
    assert case["finality"] == "NOT_FINAL"
    assert case["merchant_decision"] == "NONE"
    assert case["deadlines"]["external"] != first_deadline
    assert all(not r["valid"] for r in case["reviews"])
    assert case["packages"][0]["status"] == "INVALIDATED"


def test_confirmed_next_stage_disposition_blocks_continuation_until_stage_created(service):
    case = run(
        service,
        submitted(service),
        "RECORD_OUTCOME",
        {
            "event_id": uuid4().hex,
            "source": "mock-upstream",
            "outcome": "LOST",
            "final": False,
            "disposition": "NEXT_STAGE",
        },
    )
    with pytest.raises(DisputeError) as error:
        run(service, case, "PUBLISH_TASK")
    assert error.value.code == "NEXT_STAGE_REQUIRED"
    case = run(
        service,
        case,
        "NEXT_STAGE",
        {"event_id": uuid4().hex, "source": "mock-upstream", "stage": "PRE_ARBITRATION"},
    )
    assert case["rule_snapshot"]["conflict_status"] == "NEEDS_CONFIRMATION"


@pytest.mark.parametrize("amount", [12.50, "12500", True, -1, 10**15])
def test_amounts_require_bounded_integer_minor_units(service, amount):
    with pytest.raises(DisputeError) as error:
        intake(service, amount_minor=amount)
    assert error.value.code == "INVALID_AMOUNT"


def test_financial_events_deduplicate_and_cross_currency_or_mismatch_cannot_reconcile(service):
    case = terminal(service)
    data = {
        "event_id": "ledger-event-1",
        "kind": "DEBIT",
        "amount_minor": 12500,
        "currency": "EUR",
        "source": "mock-ledger",
        "reference": "ledger-1",
    }
    with pytest.raises(DisputeError) as error:
        run(service, case, "RECORD_FINANCIAL", data)
    assert error.value.code == "CURRENCY_MISMATCH"
    data["currency"] = "USD"
    case = run(service, case, "RECORD_FINANCIAL", data)
    replay = service.execute(command(case, "RECORD_FINANCIAL", data), OP)
    assert replay["replayed"] is True
    assert len(replay["case"]["financial_events"]) == 1
    with pytest.raises(DisputeError) as error:
        run(
            service,
            case,
            "RECONCILE",
            {
                "status": "RECONCILED",
                "expected_net_minor": 12500,
                "reason": "wrong sign",
                "reference": "recon",
            },
            SUPERVISOR,
        )
    assert error.value.code == "FINANCIAL_MISMATCH"
    case = run(
        service,
        case,
        "RECONCILE",
        {
            "status": "DISCREPANCY",
            "expected_net_minor": 0,
            "reason": "return missing",
            "reference": "recon",
        },
        SUPERVISOR,
    )
    case = run(service, case, "NOTIFY_MERCHANT")
    with pytest.raises(DisputeError) as error:
        run(service, case, "CLOSE", identity=SUPERVISOR)
    assert error.value.code == "CLOSE_BLOCKED"


def test_new_financial_event_invalidates_reconciliation_and_notification(service):
    case = run(service, reconciled(service), "NOTIFY_MERCHANT")
    case = run(
        service,
        case,
        "RECORD_FINANCIAL",
        {
            "event_id": uuid4().hex,
            "kind": "FEE",
            "amount_minor": 100,
            "currency": "USD",
            "source": "mock-ledger",
            "reference": "fee",
        },
    )
    assert case["financial_status"] == "PENDING"
    assert case["merchant_notification_completed"] is False
    with pytest.raises(DisputeError):
        run(service, case, "CLOSE", identity=SUPERVISOR)


def test_case_audit_receipt_are_atomic_and_v1_tables_untouched(service):
    with sqlite3.connect(service.store.db_path) as connection:
        connection.execute("CREATE TABLE old_v1(value TEXT)")
        connection.execute("INSERT INTO old_v1 VALUES ('preserve')")
    case = intake(service)
    with pytest.raises(DisputeError):
        run(
            service,
            case,
            "MERCHANT_DECISION",
            {"decision": "CONTEST", "reason": "invalid state"},
            MERCHANT,
        )
    with sqlite3.connect(service.store.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM v2_dispute_audit").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM v2_dispute_commands").fetchone()[0] == 1
        assert connection.execute("SELECT value FROM old_v1").fetchone()[0] == "preserve"


def test_closed_knowledge_requires_redaction_and_independent_admin_review(service):
    case = run(
        service, run(service, reconciled(service), "NOTIFY_MERCHANT"), "CLOSE", identity=SUPERVISOR
    )
    case = run(
        service,
        case,
        "KNOWLEDGE_CANDIDATE",
        {
            "summary": "merchant-a jane@example.com card 4111 1111 1111 1111",
            "pattern": "transaction-1 confirms delivery",
        },
        AGENT,
    )
    candidate = case["knowledge_candidates"][0]
    assert "jane@example.com" not in candidate["summary"]
    assert "4111" not in candidate["summary"]
    assert "merchant-a" not in candidate["summary"]
    assert candidate["status"] == "PENDING_REVIEW"
    case = run(
        service,
        case,
        "APPROVE_KNOWLEDGE",
        {
            "candidate_id": candidate["id"],
            "decision": "APPROVE",
            "reason": "Human verified no PII remains",
        },
        ADMIN,
    )
    assert case["knowledge_candidates"][0]["status"] == "APPROVED"
    assert case["knowledge_candidates"][0]["production_eligible"] is False


def test_external_notification_requires_delivery_reference(service):
    case = intake(service)
    with pytest.raises(DisputeError):
        run(service, case, "NOTIFY_MERCHANT", {"channel": "FEISHU", "message": "notify"})
    assert service.get_case(case["id"], OP)["collaboration"] == []


def test_normalized_feishu_decision_is_one_atomic_case_audit_event(service):
    case = run(service, intake(service), "PUBLISH_TASK")
    case = run(
        service,
        case,
        "MERCHANT_DECISION",
        {
            "decision": "CONTEST",
            "reason": "Have proof",
            "channel": "FEISHU",
            "external_event_id": "hashed-event",
            "thread_id": "hashed-chat",
        },
        MERCHANT,
    )
    assert case["revision"] == 3
    assert case["collaboration"][-1]["channel"] == "FEISHU"
    assert case["collaboration"][-1]["external_event_id"] == "hashed-event"
    assert case["audit"][-1]["action"] == "MERCHANT_DECISION"


def test_new_event_for_same_upstream_case_links_and_audits_without_duplicate_task(service):
    cmd = intake_command(upstream_case_id="upstream-case-1")
    case = service.execute(cmd, OP)["case"]
    case = run(service, case, "PUBLISH_TASK")
    notification = deepcopy(cmd)
    notification["command_id"] = uuid4().hex
    notification["data"]["event_id"] = uuid4().hex
    linked = service.execute(notification, OP)["case"]
    assert linked["id"] == case["id"]
    assert linked["revision"] == case["revision"] + 1
    assert len(linked["tasks"]) == 1
    assert linked["upstream_events"][-1]["type"] == "DUPLICATE_NOTIFICATION"
    assert len(service.list_cases(OP)) == 1
    notification["command_id"] = uuid4().hex
    notification["data"]["event_id"] = uuid4().hex
    notification["data"]["merchant_id"] = "merchant-b"
    with pytest.raises(DisputeError) as error:
        service.execute(notification, OP)
    assert error.value.code == "UPSTREAM_CASE_CONFLICT"


def test_concurrent_notifications_link_same_upstream_case_atomically(service):
    commands = [intake_command(upstream_case_id="one-upstream-case") for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda cmd: service.execute(cmd, OP), commands))
    assert len({result["case"]["id"] for result in results}) == 1
    case = service.list_cases(OP)[0]
    assert case["revision"] == 6
    assert len(case["upstream_events"]) == 6
    assert len(case["audit"]) == 6


def test_stage_history_keeps_the_exact_original_frozen_snapshot(service):
    case = submitted(service)
    old_rule = deepcopy(case["rule_snapshot"])
    old_packages = deepcopy(case["packages"])
    case = run(
        service,
        case,
        "RECORD_OUTCOME",
        {
            "event_id": uuid4().hex,
            "source": "mock-upstream",
            "outcome": "LOST",
            "final": False,
            "next_stage": "REPRESENTMENT",
            "received_at": NOW.isoformat(),
        },
    )
    history = case["stage_history"][0]
    assert history["rule_snapshot"] == old_rule
    assert history["packages"] == old_packages
    assert history["packages"][0]["status"] == "FROZEN"
    assert case["packages"][0]["status"] == "INVALIDATED"
    assert history["business_outcome"] == "LOST"


def test_refund_reduces_merchant_net_and_requires_matching_human_reconciliation(service):
    case = terminal(service)
    case = run(
        service,
        case,
        "RECORD_FINANCIAL",
        {
            "event_id": uuid4().hex,
            "kind": "REFUND",
            "amount_minor": 12500,
            "currency": "USD",
            "source": "mock-ledger",
            "reference": "refund-report-1",
        },
    )
    assert case["financial_events"][0]["net_minor"] == -12500
    case = run(
        service,
        case,
        "RECONCILE",
        {
            "status": "RECONCILED",
            "expected_net_minor": -12500,
            "reason": "Merchant refund debited",
            "reference": "confirmed-report",
        },
        SUPERVISOR,
    )
    assert case["reconciliation"]["actual_net_minor"] == -12500


def test_unknown_outcome_is_preserved_but_cannot_become_final(service):
    case = submitted(service)
    data = {"event_id": uuid4().hex, "source": "mock-upstream", "outcome": "UNKNOWN", "final": True}
    with pytest.raises(DisputeError) as error:
        run(service, case, "RECORD_OUTCOME", data)
    assert error.value.code == "UNKNOWN_FINAL_OUTCOME"
    data["final"] = False
    case = run(service, case, "RECORD_OUTCOME", data)
    assert case["business_outcome"] == "UNKNOWN"
    assert case["work_status"] == "OUTCOME_VERIFICATION"
    assert case["pending_next_stage"] is False
    assert any(t["type"] == "OUTCOME_CONFIRMATION" for t in case["tasks"])
    with pytest.raises(DisputeError):
        run(service, case, "CLOSE", identity=SUPERVISOR)


@pytest.mark.parametrize(
    "message",
    [
        "card 4111 1111 1111 1111",
        "authorization: bearer-secret",
        "password=do-not-store",
        "cvv: 123",
    ],
)
def test_sensitive_payment_values_never_reach_case_or_audit_storage(service, message):
    case = intake(service)
    with pytest.raises(DisputeError) as error:
        run(service, case, "COMMENT", {"message": message})
    assert error.value.code == "SENSITIVE_DATA_REJECTED"
    with sqlite3.connect(service.store.db_path) as connection:
        snapshot = connection.execute("SELECT snapshot FROM v2_dispute_cases").fetchone()[0]
        assert message not in snapshot
        assert connection.execute("SELECT COUNT(*) FROM v2_dispute_commands").fetchone()[0] == 1


def test_legitimate_authorization_reference_metadata_is_not_mistaken_for_credentials(service):
    case = run(service, intake(service), "PUBLISH_TASK")
    case = run(
        service,
        case,
        "MERCHANT_DECISION",
        {
            "decision": "ACCEPT",
            "reason": "Merchant signed acceptance",
            "authorization_reference": "signed-letter-2026-1",
        },
    )
    assert case["merchant_authorization"]["reference"] == "signed-letter-2026-1"


@pytest.mark.parametrize(
    "field,value",
    [
        ("code", []),
        ("title", {}),
        ("reference", []),
        ("source_channel", {}),
        ("notes", {"nested": "invalid"}),
        ("evidence_id", []),
    ],
)
def test_malformed_evidence_metadata_returns_domain_error_without_writing(service, field, value):
    case = contest(service)
    data = {"code": "transaction.receipt", "title": "Receipt", "reference": "synthetic://receipt"}
    data[field] = value
    with pytest.raises(DisputeError) as error:
        run(service, case, "REGISTER_EVIDENCE", data, MERCHANT)
    assert error.value.status == 422
    assert service.get_case(case["id"], OP)["revision"] == case["revision"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", {}),
        ("event_id", []),
        ("outcome", []),
        ("final", "true"),
        ("reason", {}),
        ("next_stage", []),
    ],
)
def test_malformed_upstream_outcomes_fail_without_partial_mutation(service, field, value):
    case = submitted(service)
    data = {"event_id": uuid4().hex, "source": "mock-upstream", "outcome": "OTHER", "final": False}
    data[field] = value
    with pytest.raises(DisputeError) as error:
        run(service, case, "RECORD_OUTCOME", data)
    assert error.value.status == 422
    assert service.get_case(case["id"], OP)["revision"] == case["revision"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", []),
        ("reference", {}),
        ("kind", []),
        ("amount_minor", {}),
        ("currency", []),
    ],
)
def test_malformed_financial_fields_are_rejected_in_service(service, field, value):
    case = terminal(service)
    data = {
        "event_id": uuid4().hex,
        "source": "ledger",
        "reference": "report",
        "kind": "CREDIT",
        "amount_minor": 12500,
        "currency": "USD",
    }
    data[field] = value
    with pytest.raises(DisputeError) as error:
        run(service, case, "RECORD_FINANCIAL", data)
    assert error.value.status == 422
    assert service.get_case(case["id"], OP)["financial_events"] == []


def test_uuid_identifiers_with_luhn_like_digit_runs_do_not_trigger_false_payment_alert(service):
    cmd = intake_command(event_id="60e9be38f5184ec1b372162378151649")
    assert service.execute(cmd, OP)["case"]["upstream_events"][0]["id"] == cmd["data"]["event_id"]


def test_nested_or_cyclic_non_json_payload_fails_as_a_domain_validation_error(service):
    cmd = intake_command()
    cmd["data"]["cycle"] = cmd
    with pytest.raises(DisputeError) as error:
        service.execute(cmd, OP)
    assert error.value.code == "INVALID_INPUT"


def test_unknown_rule_requires_explicit_allowed_actions(service):
    case = intake(service, reason_code="unknown")
    data = {
        "source_id": "manual-demo",
        "source_locator": "demo:section-1",
        "rule_version": "demo-v1",
        "reason": "Reviewed source",
        "external_deadline": "2026-09-13T12:00:00Z",
        "required_evidence": ["transaction.receipt"],
    }
    with pytest.raises(DisputeError) as error:
        run(service, case, "CONFIRM_RULE", data, RISK)
    assert error.value.code == "ACTION_CONFIRMATION_REQUIRED"
    data["allowed_actions"] = ["ACCEPT"]
    case = run(service, case, "CONFIRM_RULE", data, RISK)
    case = run(service, case, "PUBLISH_TASK")
    with pytest.raises(DisputeError) as error:
        run(
            service,
            case,
            "MERCHANT_DECISION",
            {"decision": "CONTEST", "reason": "unsupported"},
            MERCHANT,
        )
    assert error.value.code == "ACTION_NOT_ALLOWED"
    assert "CONTEST" not in case["tasks"][0]["message"]
