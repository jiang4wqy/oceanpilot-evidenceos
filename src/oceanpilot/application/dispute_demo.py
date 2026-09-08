"""Golden demo fixtures created through the same authorized domain commands.

Fixture identities are intentionally explicit: this module is a synthetic demo
builder, never a production intake or a route for arbitrary role elevation.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from oceanpilot.domain.dispute_rules import case_plan


def demo_identity(role: str, merchant_id: str = "synthetic-merchant-001") -> dict:
    return {"role": role, "actor_id": f"synthetic-{role.lower()}", "merchant_id": merchant_id}


def issue(
    service, case: dict | None, action: str, data: dict, role: str, *, command_id=None
) -> dict:
    return service.execute(
        {
            "command_id": command_id or str(uuid4()),
            "action": action,
            "case_id": case["id"] if case else None,
            "expected_revision": case["revision"] if case else None,
            "confirmed": True,
            "data": data,
        },
        demo_identity(
            role, case["merchant_id"] if case else data.get("merchant_id", "synthetic-merchant-001")
        ),
    )


def complete_contest(service, case: dict) -> dict:
    if case["merchant_decision"] != "CONTEST":
        case = issue(
            service,
            case,
            "MERCHANT_DECISION",
            {"decision": "CONTEST", "reason": "合成商户确认继续抗辩"},
            "MERCHANT",
        )["case"]
    for item in case_plan(case)["checklist"]:
        if not item["present"]:
            case = issue(
                service,
                case,
                "REGISTER_EVIDENCE",
                {
                    "code": item["code"],
                    "title": item["label"] + "（合成示例）",
                    "source_channel": "PORTAL",
                    "reference": "synthetic://" + item["code"],
                },
                "MERCHANT",
            )["case"]
    case = issue(service, case, "SUBMIT_EVIDENCE", {}, "MERCHANT")["case"]
    case = issue(
        service,
        case,
        "REVIEW",
        {"decision": "PASS", "reason": "已人工核对本版合成登记清单和规则来源"},
        "RISK_OFFICER",
    )["case"]
    case = issue(service, case, "BUILD_PACKAGE", {}, "OPERATOR")["case"]
    case = issue(
        service,
        case,
        "APPROVE_PACKAGE",
        {"reason": "最终人工确认合成证据索引、草稿及脱敏范围", "pii_checked": True},
        "SUPERVISOR",
    )["case"]
    return issue(service, case, "SUBMIT", {}, "OPERATOR")["case"]


def record_terminal_financial(service, case: dict, *, discrepancy: bool = False) -> dict:
    case = issue(
        service,
        case,
        "RECORD_OUTCOME",
        {
            "event_id": str(uuid4()),
            "outcome": "WON",
            "final": True,
            "source": "MOCK_UPSTREAM",
            "reason": "合成上游终局通知",
        },
        "OPERATOR",
    )["case"]
    case = issue(
        service,
        case,
        "RECORD_FINANCIAL",
        {
            "event_id": str(uuid4()),
            "kind": "CREDIT",
            "amount_minor": case["amount_minor"],
            "currency": case["currency"],
            "source": "MOCK_LEDGER",
            "reference": "synthetic://ledger-return",
        },
        "OPERATOR",
    )["case"]
    return issue(
        service,
        case,
        "RECONCILE",
        {
            "status": "DISCREPANCY" if discrepancy else "RECONCILED",
            "expected_net_minor": case["amount_minor"] + (100 if discrepancy else 0),
            "reason": "合成账本差异待核对" if discrepancy else "人工核对合成账本金额一致",
            "reference": "synthetic://reconciliation",
        },
        "SUPERVISOR",
    )["case"]


def close_demo(service, case: dict) -> dict:
    case = issue(
        service,
        case,
        "NOTIFY_MERCHANT",
        {"message": "合成案件结果与资金摘要已发布到 Portal。", "channel": "PORTAL"},
        "OPERATOR",
    )["case"]
    return issue(service, case, "CLOSE", {}, "SUPERVISOR")["case"]


def create_demo(service, scenario: str, identity: dict, event_id: str) -> dict:
    received = datetime.now(UTC) - timedelta(days=4 if scenario == "C" else 0)
    result = service.execute(
        {
            "command_id": str(uuid4()),
            "action": "INTAKE",
            "confirmed": True,
            "data": {
                "merchant_id": identity["merchant_id"],
                "transaction_id": f"synthetic-{event_id}",
                "scheme": "VISA",
                "channel": "MOCK",
                "reason_code": "13.1" if scenario == "B" else "10.4",
                "amount_minor": 12800,
                "currency": "USD",
                "event_id": event_id,
                "received_at": received.isoformat(),
            },
        },
        identity,
    )
    case = result["case"]
    result = issue(
        service,
        case,
        "PUBLISH_TASK",
        {"message": f"Golden Demo {scenario}：请选择接受或抗辩。"},
        "OPERATOR",
    )
    case = result["case"]
    if scenario in ("B", "D"):
        result = issue(
            service,
            case,
            "MERCHANT_DECISION",
            {"decision": "CONTEST", "reason": "合成商户选择继续抗辩"},
            "MERCHANT",
        )
        case = result["case"]
    if scenario == "B":
        result = issue(
            service,
            case,
            "REGISTER_EVIDENCE",
            {
                "code": "transaction.receipt",
                "title": "合成交易收据",
                "source_channel": "PORTAL",
                "reference": "synthetic://receipt",
            },
            "MERCHANT",
        )
    elif scenario == "C":
        result = issue(service, case, "MONITOR_SLA", {}, "OPERATOR")
    elif scenario == "D":
        case = complete_contest(service, case)
        case = record_terminal_financial(service, case, discrepancy=True)
        result = {"case": case, "receipt": {"scenario": scenario}, "replayed": False}
    return result | {"scenario": scenario, "synthetic": True}
