"""Reproducible, offline workflow benchmark; all observations are synthetic."""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore  # noqa: E402
from oceanpilot.application.dispute_demo import (  # noqa: E402
    close_demo,
    complete_contest,
    create_demo,
    demo_identity,
    issue,
    record_terminal_financial,
)
from oceanpilot.application.disputes import DisputeService  # noqa: E402
from oceanpilot.domain.dispute import DisputeError  # noqa: E402
from oceanpilot.domain.dispute_rules import case_plan, match_rule, rule_catalog  # noqa: E402


def evaluate() -> dict:
    checks: list[dict] = []

    def observe(metric, passed, detail):
        checks.append({"metric": metric, "passed": bool(passed), "detail": detail})

    now = datetime.now(UTC)
    for rule in rule_catalog():
        found = match_rule(rule["scheme"], rule["channel"], rule["reason_code"], rule["stage"], now)
        observe("rule_retrieval", found["rule_id"] == rule["rule_id"], rule["rule_id"])
        observe(
            "source_citation",
            all(found.get(k) for k in ("source_id", "source_locator", "rule_version")),
            rule["rule_id"],
        )
        for key, hours in (("merchant", 72), ("internal", 96), ("external", 120)):
            actual = datetime.fromisoformat(found["deadlines"][key])
            observe(
                "sla_calculation",
                actual == now + timedelta(hours=hours),
                f"{rule['rule_id']}:{key}",
            )

    unknown = match_rule("VISA", "PRODUCTION_UNKNOWN", "10.4", "FORMAL_DISPUTE", now)
    observe(
        "agent_escalation",
        unknown["conflict_status"] == "NEEDS_CONFIRMATION"
        and unknown["deadlines"]["external"] is None,
        "Unknown channel has no invented rule or deadline",
    )

    with TemporaryDirectory() as directory:
        service = DisputeService(SQLiteDisputeStore(Path(directory) / "benchmark.db"))
        case = create_demo(service, "A", demo_identity("OPERATOR"), str(uuid4()))["case"]
        for role, action in (
            ("MERCHANT", "REVIEW"),
            ("MERCHANT", "SUBMIT"),
            ("AGENT", "SUBMIT"),
            ("ADMIN", "CLOSE"),
        ):
            try:
                issue(
                    service,
                    case,
                    action,
                    {"decision": "PASS", "reason": "synthetic forbidden attempt"},
                    role,
                )
                blocked = False
            except DisputeError as exc:
                blocked = exc.status == 403
            observe("unsafe_action_block", blocked, f"{role}:{action}")

        old = case
        case = issue(
            service,
            case,
            "MERCHANT_DECISION",
            {"decision": "CONTEST", "reason": "synthetic merchant decision"},
            "MERCHANT",
        )["case"]
        try:
            issue(service, old, "COMMENT", {"message": "stale proposal"}, "OPERATOR")
            blocked = False
        except DisputeError as exc:
            blocked = exc.code == "REVISION_CONFLICT"
        observe("revision_safety", blocked, "A stale proposal cannot mutate a newer case")

        plan = case_plan(case)
        observe(
            "required_evidence_recall",
            set(plan["missing_required"]) == set(case["rule_snapshot"]["required_evidence"]),
            "Empty evidence reflects all required items",
        )
        try:
            issue(service, case, "SUBMIT_EVIDENCE", {}, "MERCHANT")
            blocked = False
        except DisputeError as exc:
            blocked = exc.code == "MISSING_EVIDENCE"
        observe(
            "missing_evidence_detection",
            blocked and bool(plan["missing_critical"]),
            "Critical gaps block submission to Risk review",
        )

        case = complete_contest(service, case)
        observe(
            "state_transition",
            case["work_status"] == "WAITING_UPSTREAM" and case["business_outcome"] == "UNKNOWN",
            "Mock receipt does not imply outcome or closure",
        )
        observe(
            "state_transition",
            case["submissions"][0]["mode"] == "MOCK",
            "Submission is explicitly Mock",
        )
        case = record_terminal_financial(service, case, discrepancy=True)
        try:
            issue(service, case, "CLOSE", {}, "SUPERVISOR")
            blocked = False
        except DisputeError as exc:
            blocked = exc.code == "CLOSE_BLOCKED"
        observe(
            "unsafe_action_block", blocked, "Terminal WON plus financial discrepancy cannot close"
        )
        case = issue(
            service,
            case,
            "RECONCILE",
            {
                "status": "RECONCILED",
                "expected_net_minor": case["amount_minor"],
                "reason": "human verified synthetic ledger",
                "reference": "synthetic://confirmed-ledger",
            },
            "SUPERVISOR",
        )["case"]
        case = close_demo(service, case)
        observe(
            "state_transition",
            case["work_status"] == "CLOSED",
            "Contest reaches closed only after finality, reconciliation and notification",
        )
        observe(
            "audit_completeness",
            len(case["audit"]) == case["revision"]
            and [a["revision"] for a in case["audit"]] == list(range(1, case["revision"] + 1)),
            "Every committed revision has an ordered audit event",
        )

        for scenario in "BCD":
            sample = create_demo(service, scenario, demo_identity("OPERATOR"), str(uuid4()))["case"]
            observe(
                "golden_demo",
                sample["source_type"] == "SYNTHETIC_DEMO" and bool(sample["audit"]),
                scenario,
            )
        reopened = DisputeService(SQLiteDisputeStore(Path(directory) / "benchmark.db"))
        observe(
            "persistence",
            reopened.get_case(case["id"], demo_identity("OPERATOR")) == case,
            "Restart preserves terminal case and audit",
        )

    metrics = {}
    for item in checks:
        result = metrics.setdefault(item["metric"], {"passed": 0, "total": 0})
        result["total"] += 1
        result["passed"] += int(item["passed"])
    return {
        "source_type": "SYNTHETIC_DEMO",
        "production_eligible": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "limitation": (
            "Small deterministic fixture benchmark; no production rules, tenants, "
            "real outcomes or win-rate claims."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(
        json.dumps({k: v for k, v in report.items() if k != "checks"}, ensure_ascii=False, indent=2)
    )
    raise SystemExit(0 if report["passed"] else 1)
