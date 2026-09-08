from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from oceanpilot.domain.dispute_rules import case_plan, match_rule, rule_catalog

NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize("rule", rule_catalog())
def test_exact_fixture_rules_have_provenance_and_three_correct_deadlines(rule):
    snapshot = match_rule(rule["scheme"], rule["channel"], rule["reason_code"], rule["stage"], NOW)
    assert snapshot["conflict_status"] == "VERIFIED"
    assert snapshot["source_id"] and snapshot["source_locator"] and snapshot["rule_version"]
    assert snapshot["production_eligible"] is False
    for key, hours in (("merchant", 72), ("internal", 96), ("external", 120)):
        assert datetime.fromisoformat(snapshot["deadlines"][key]) == NOW + timedelta(hours=hours)


@pytest.mark.parametrize(
    "scheme,channel,reason,stage,date",
    [
        ("VISA", "REAL_UPSTREAM", "10.4", "FORMAL_DISPUTE", NOW),
        ("VISA", "MOCK", "10.4", "PRE_ARBITRATION", NOW),
        ("VISA", "MOCK", "4853", "FORMAL_DISPUTE", NOW),
        ("VISA", "MOCK", "10.4", "FORMAL_DISPUTE", datetime(2031, 1, 1, tzinfo=UTC)),
    ],
)
def test_unknown_or_expired_mapping_never_guesses_rules_or_deadlines(
    scheme, channel, reason, stage, date
):
    snapshot = match_rule(scheme, channel, reason, stage, date)
    assert snapshot["conflict_status"] == "NEEDS_CONFIRMATION"
    assert snapshot["allowed_actions"] == []
    assert snapshot["deadlines"]["external"] is None


def test_snapshot_mutation_does_not_change_catalog_and_plan_retains_snapshot():
    snapshot = match_rule("VISA", "MOCK", "10.4", "FORMAL_DISPUTE", NOW)
    saved = deepcopy(snapshot)
    snapshot["required_evidence"].clear()
    assert match_rule("VISA", "MOCK", "10.4", "FORMAL_DISPUTE", NOW) == saved
    case = {
        "id": "case-test",
        "revision": 8,
        "rule_snapshot": saved,
        "evidence": [],
        "merchant_decision": "CONTEST",
        "work_status": "EVIDENCE_COLLECTING",
    }
    plan = case_plan(case, now=NOW)
    assert len(plan["checklist"]) == len(saved["required_evidence"])
    assert set(plan["missing_critical"]) == set(saved["critical_evidence"])
    assert plan["proposal"]["expected_revision"] == 8
    assert plan["readiness"]["percent"] == 0
    assert plan["agent"]["provider"] == "DETERMINISTIC"


def test_accept_removes_contest_checklist_and_next_stage_is_explicit():
    case = {
        "id": "case-test",
        "revision": 9,
        "rule_snapshot": match_rule("VISA", "MOCK", "10.4", "FORMAL_DISPUTE", NOW),
        "evidence": [],
        "merchant_decision": "ACCEPT",
        "work_status": "WAITING_UPSTREAM",
    }
    assert case_plan(case, now=NOW)["checklist"] == []
    case["pending_next_stage"] = True
    assert case_plan(case, now=NOW)["next_action"]["action"] == "NEXT_STAGE"
