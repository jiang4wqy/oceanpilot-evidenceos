"""Source-explicit, synthetic V2 rule snapshots and deterministic case planning.

The existing evidence catalog is reused. None of these fixture policies are
card-scheme advice or production rules; exact channel/stage matching fails closed.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from oceanpilot.domain.chargeback import (
    ChargebackEvidenceCode,
    DisputeReasonCode,
    assess_chargeback,
)
from oceanpilot.domain.evidence_catalog import (
    EVIDENCE_CONTENT_FIELDS,
    MATERIAL_REGISTRATION_BOUNDARY,
    describe,
    expected_source_of,
)

RULE_VERSION = "synthetic-v2-2026-09-08"
_MAPPINGS = (
    ("VISA", "10.4", DisputeReasonCode.FRAUD_CARD_NOT_PRESENT),
    ("VISA", "13.1", DisputeReasonCode.PRODUCT_NOT_RECEIVED),
    ("MASTERCARD", "4853", DisputeReasonCode.PRODUCT_NOT_AS_DESCRIBED),
)


def _time(value: str | datetime) -> datetime:
    result = (
        datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    )
    if result.tzinfo is None:
        raise ValueError("timestamp requires a timezone")
    return result.astimezone(UTC)


def rule_catalog() -> list[dict[str, Any]]:
    rules = []
    for scheme, reason, internal in _MAPPINGS:
        assessment = assess_chargeback(internal, ())
        for stage in ("FORMAL_DISPUTE", "REPRESENTMENT"):
            rules.append(
                {
                    "rule_id": f"DEMO-{scheme}-{reason}-{stage}",
                    "scheme": scheme,
                    "channel": "MOCK",
                    "reason_code": reason,
                    "stage": stage,
                    "rule_version": RULE_VERSION,
                    "effective_date": "2026-01-01",
                    "expiry_date": "2030-01-01",
                    "source_id": "oceanpilot-synthetic-evidence-policy",
                    "source_locator": f"domain/chargeback.py:_POLICIES.{internal.value}",
                    "source_type": "SYNTHETIC_DEMO",
                    "conflict_status": "VERIFIED",
                    "verification_scope": "SYNTHETIC_FIXTURE_ONLY",
                    "production_eligible": False,
                    "confidence": "FIXTURE_VALIDATED",
                    "required_evidence": [
                        item.code.value for item in assessment.evidence_breakdown
                    ],
                    "critical_evidence": [
                        item.code.value for item in assessment.evidence_breakdown if item.critical
                    ],
                    "recommended_evidence": [],
                    "allowed_actions": ["ACCEPT", "CONTEST"],
                    "deadline_policy": {
                        "merchant_hours": 72,
                        "internal_hours": 96,
                        "external_hours": 120,
                        "anchor_field": "received_at",
                        "basis": "Synthetic elapsed UTC hours; not a scheme deadline",
                    },
                    "limitation": "合成演示规则，仅验证工作流；正式规则、授权与期限待企业确认。",
                }
            )
    return rules


def match_rule(
    scheme: str, channel: str, reason_code: str, stage: str, received_at: str | datetime
) -> dict[str, Any]:
    received = _time(received_at)
    for rule in rule_catalog():
        if (scheme, channel, reason_code, stage) == (
            rule["scheme"],
            rule["channel"],
            rule["reason_code"],
            rule["stage"],
        ) and rule["effective_date"] <= received.date().isoformat() < rule["expiry_date"]:
            rule["deadlines"] = {
                name: (
                    received + timedelta(hours=rule["deadline_policy"][f"{name}_hours"])
                ).isoformat()
                for name in ("merchant", "internal", "external")
            }
            rule["deadlines"].update(status="CONFIRMED", source=rule["rule_id"])
            return rule
    return {
        "rule_id": None,
        "scheme": scheme,
        "channel": channel,
        "reason_code": reason_code,
        "stage": stage,
        "rule_version": None,
        "source_id": None,
        "source_locator": None,
        "source_type": "SYNTHETIC_DEMO",
        "effective_date": None,
        "expiry_date": None,
        "production_eligible": False,
        "confidence": "UNKNOWN",
        "conflict_status": "NEEDS_CONFIRMATION",
        "required_evidence": [],
        "critical_evidence": [],
        "recommended_evidence": [],
        "allowed_actions": [],
        "deadline_policy": {},
        "deadlines": {
            "merchant": None,
            "internal": None,
            "external": None,
            "status": "NEEDS_CONFIRMATION",
            "source": None,
        },
        "limitation": "没有匹配渠道、阶段及有效期的规则；需要 OP 确认来源、证据清单与期限。",
    }


_NEXT = {
    "RECEIVED": ("CONFIRM_RULE", "OPERATOR", "确认适用规则和时限"),
    "TRIAGED": ("PUBLISH_TASK", "OPERATOR", "复核案件计划并发布商户任务"),
    "MERCHANT_ACTION_REQUIRED": ("MERCHANT_DECISION", "MERCHANT", "明确接受争议或继续抗辩"),
    "EVIDENCE_COLLECTING": ("REGISTER_EVIDENCE", "MERCHANT", "按清单补充合成材料登记"),
    "MERCHANT_REVISION_REQUIRED": ("REGISTER_EVIDENCE", "MERCHANT", "根据 OP 反馈补证后重新送审"),
    "EVIDENCE_SUBMITTED": ("REVIEW", "OPERATOR", "人工审核本次材料版本"),
    "OP_REVIEW": ("REVIEW", "OPERATOR", "人工审核本次材料版本"),
    "READY_TO_SUBMIT": ("BUILD_PACKAGE", "OPERATOR", "起草证据包并安排最终人工确认"),
    "SUBMISSION_PENDING_CONFIRMATION": (
        "APPROVE_PACKAGE",
        "SUPERVISOR",
        "核对草稿、来源与脱敏检查",
    ),
    "SUBMITTED": ("RECORD_OUTCOME", "OPERATOR", "保存上游正式结果，技术回执不等于业务结果"),
    "WAITING_UPSTREAM": ("RECORD_OUTCOME", "OPERATOR", "等待上游结果与终局确认"),
    "FINANCIAL_RECONCILIATION": ("RECONCILE", "SUPERVISOR", "核对资金事件及差异"),
    "RESPONSE_REVIEW_REQUIRED": (
        "RESOLVE_RESPONSE",
        "OPERATOR",
        "核实剩余权利并恢复决定、材料或确认失权",
    ),
    "ACCEPT_RECOMMENDATION": (
        "MERCHANT_DECISION",
        "MERCHANT",
        "查看人工建议后明确接受责任或继续抗辩",
    ),
    "ACCEPT_PROCESSING": ("PROCESS_ACCEPT", "OPERATOR", "核查授权与已有资金事件，完成渠道接受处理"),
    "DOCUMENT_REVISION_REQUIRED": (
        "BUILD_PACKAGE",
        "OPERATOR",
        "依据风控经理意见修改文书并重新送终审",
    ),
    "ON_HOLD": ("FINAL_REVIEW", "SUPERVISOR", "解决暂缓事项并明确退回或升级方向"),
    "OUTCOME_VERIFICATION": (
        "VERIFY_OUTCOME",
        "OPERATOR",
        "核实上游事件来源、阶段、终局依据和更正范围",
    ),
    "UPSTREAM_ACTION_REQUIRED": (
        "RESOLVE_RESPONSE",
        "OPERATOR",
        "确认本阶段需要的处理动作与剩余权利",
    ),
    "SUBMISSION_UNCERTAIN": (
        "QUERY_SUBMISSION",
        "OPERATOR",
        "先查询原业务请求回执，受理未明时不得重复发送",
    ),
    "CLOSED": ("KNOWLEDGE_CANDIDATE", "OPERATOR", "提取脱敏案例模式，交由IT 管理员审核"),
}

_SLA_DEADLINE_BY_OWNER = {
    "MERCHANT": "merchant",
    "SUPERVISOR": "internal",
    "OPERATOR": "external",
}
_SLA_REMINDER_BANDS = (
    ("T_MINUS_7D", timedelta(days=7)),
    ("T_MINUS_3D", timedelta(days=3)),
    ("T_MINUS_24H", timedelta(hours=24)),
)


def current_sla(
    case: dict[str, Any],
    *,
    owner: str,
    action: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Describe deadline risk for the current stage's open responsibility.

    The result is advisory only. In particular, an overdue deadline does not
    change the case, accept a dispute, or establish that any right was lost.
    """
    current = (now or datetime.now(UTC)).astimezone(UTC)
    stage_number = case.get("stage_number", 1)
    tasks = [
        task
        for task in case.get("tasks", [])
        if task.get("status") in {"OPEN", "IN_PROGRESS"}
        and task.get("stage_number", 1) == stage_number
        and task.get("owner") == owner
    ]
    # Accepted submissions wait on an upstream result without creating a
    # business task. Represent that read-only responsibility explicitly so the
    # external clock remains monitorable without mutating the case revision.
    if not tasks and case.get("work_status") == "WAITING_UPSTREAM" and owner == "OPERATOR":
        tasks = [
            {
                "id": f"workflow:{stage_number}:{action}",
                "type": action,
                "status": "OPEN",
                "owner": owner,
                "assignee": case.get("assigned_op_user_id"),
                "stage_number": stage_number,
                "created_at": case.get("updated_at") or case.get("received_at"),
            }
        ]
    deadline_kind = _SLA_DEADLINE_BY_OWNER.get(owner) if tasks else None
    if (
        tasks
        and owner == "OPERATOR"
        and action
        in {
            "CONFIRM_RULE",
            "REVIEW",
            "REVIEW_EVIDENCE_CONTENT",
            "RESOLVE_RESPONSE",
            "VERIFY_OUTCOME",
            "REUSE_EVIDENCE",
        }
    ):
        deadline_kind = "internal"
    deadlines = case.get("deadlines") or case.get("rule_snapshot", {}).get("deadlines") or {}
    deadline_value = deadlines.get(deadline_kind) if deadline_kind else None
    deadline = _time(deadline_value) if deadline_value else None
    remaining_hours = (deadline - current).total_seconds() / 3600 if deadline is not None else None
    risk = "NEEDS_CONFIRMATION"
    reminder_band = None
    if tasks and deadline is not None and deadlines.get("status") == "CONFIRMED":
        if remaining_hours <= 0:
            risk, reminder_band = "OVERDUE", "DUE"
        else:
            risk = "AT_RISK" if remaining_hours <= 24 else "ON_TRACK"
            created_values = [
                _time(task["created_at"]) for task in tasks if task.get("created_at") is not None
            ]
            available = deadline - min(created_values) if created_values else deadline - current
            crossed = [
                (name, window)
                for name, window in _SLA_REMINDER_BANDS
                if window < available and deadline - current <= window
            ]
            if crossed:
                reminder_band = crossed[-1][0]
    assignee_ids = sorted(
        {
            assignee
            for task in tasks
            if (assignee := task.get("assignee_id") or task.get("assignee"))
        }
    )
    if not assignee_ids:
        fallback = (
            case.get("merchant_id")
            if owner == "MERCHANT"
            else case.get("assigned_op_user_id")
            if owner == "OPERATOR"
            else None
        )
        if fallback:
            assignee_ids = [fallback]
    return {
        "risk": risk,
        "deadline_kind": deadline_kind,
        "deadline": deadline_value,
        "remaining_hours": remaining_hours,
        "reminder_band": reminder_band,
        "stage_number": stage_number,
        "task_ids": [task["id"] for task in tasks],
        "task_types": [task.get("type") for task in tasks],
        "owner": owner if tasks else None,
        "assignee_ids": assignee_ids,
        "boundary": "SLA 仅用于提醒与人工升级；逾期不代表接受争议或正式失权。",
    }


def case_plan(case: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    rule = case.get("rule_snapshot") or {}
    required = rule.get("required_evidence", [])
    critical = set(rule.get("critical_evidence", required))
    from oceanpilot.domain.dispute import evidence_codes

    present = evidence_codes(case)
    checklist = []
    for code in required:
        current_evidence = next(
            (
                item
                for item in reversed(case.get("evidence", []))
                if item.get("code") == code and item.get("active") is not False
            ),
            None,
        )
        content_status = (current_evidence or {}).get("content_check", {}).get("status")
        try:
            detail = describe(ChargebackEvidenceCode(code))
            label, why = detail.label, detail.why
            description, examples = detail.description, list(detail.examples)
        except ValueError:
            label, why = code, "OP 人工确认的材料项；内容仍需人工核验。"
            description, examples = "由 OceanPayment 人工确认本项材料内容。", []
        checklist.append(
            {
                "code": code,
                "label": label,
                "description": description,
                "why": why,
                "expected_fields": list(EVIDENCE_CONTENT_FIELDS.get(code, ())),
                "examples": examples,
                "expected_source": expected_source_of(code),
                "required": True,
                "critical": code in critical,
                "present": code in present,
                "upload_status": content_status
                or ("REGISTERED" if current_evidence else "MISSING"),
            }
        )
    missing = [code for code in required if code not in present]
    missing_critical = [code for code in missing if code in critical]
    action, owner, reason = _NEXT.get(
        case.get("work_status", "RECEIVED"),
        ("MONITOR_SLA", "OPERATOR", "检查阶段、剩余权利和未完成任务"),
    )
    blockers = []
    rule_status = rule.get("conflict_status", "NEEDS_CONFIRMATION")
    if rule_status not in ("VERIFIED", "HUMAN_CONFIRMED"):
        blockers.append("规则或时限待 OP 确认，不能猜测适用依据。")
        action, owner, reason = "CONFIRM_RULE", "OPERATOR", blockers[-1]
    elif missing_critical and case.get("merchant_decision") == "CONTEST":
        blockers.append("关键材料缺失，不能通过审核或提交。")
    if case.get("merchant_decision") == "NO_RESPONSE":
        blockers.append("商户未响应不代表接受；需要人工检查剩余权利与授权。")
    if case.get("financial_status") == "DISCREPANCY":
        blockers.append("资金存在差异，不能结案。")
    if case.get("finality") != "FINAL_CONFIRMED":
        blockers.append("终局尚未确认，不能结案。")
    if case.get("merchant_decision") in {"ACCEPT", "AUTHORIZED_WAIVER"}:
        checklist, missing, missing_critical = [], [], []
    if case.get("work_status") == "READY_TO_SUBMIT":
        package = next(
            (
                p
                for p in reversed(case.get("packages", []))
                if p.get("status") in ("APPROVED", "FROZEN")
            ),
            None,
        )
        if package:
            action, owner, reason = "SUBMIT", "OPERATOR", "提交已获最终人工批准的冻结包（Mock）"
    if (
        case.get("financial_status") in ("RECONCILED", "NOT_APPLICABLE")
        and case.get("work_status") != "CLOSED"
    ):
        if case.get("merchant_notification_completed"):
            action, owner, reason = "CLOSE", "SUPERVISOR", "核查所有结案条件并人工结案"
        else:
            action, owner, reason = (
                "NOTIFY_MERCHANT",
                "OPERATOR",
                "在 Portal 发布已确认的结果与资金摘要",
            )
    if not missing and case.get("work_status") in (
        "EVIDENCE_COLLECTING",
        "MERCHANT_REVISION_REQUIRED",
    ):
        action, owner, reason = "SUBMIT_EVIDENCE", "MERCHANT", "登记清单齐全，提交 OP 人工复核"
    if (
        rule_status in {"VERIFIED", "HUMAN_CONFIRMED"}
        and case.get("work_status")
        in {
            "EVIDENCE_COLLECTING",
            "MERCHANT_REVISION_REQUIRED",
            "OP_REVIEW",
            "READY_TO_SUBMIT",
            "SUBMISSION_PENDING_CONFIRMATION",
            "DOCUMENT_REVISION_REQUIRED",
        }
        and any(
            item.get("active")
            and item.get("object_id")
            and item.get("content_check", {}).get("status") == "NEEDS_MANUAL"
            and case.get("stage_number", 1)
            in item.get("applicable_stages", [item.get("stage_number", 1)])
            for item in case.get("evidence", [])
        )
    ):
        action, owner, reason = (
            "REVIEW_EVIDENCE_CONTENT",
            "OPERATOR",
            "核对已保存文件的正文位置和本案适用事实",
        )
    if case.get("pending_next_stage"):
        action, owner, reason = (
            "NEXT_STAGE",
            "OPERATOR",
            "非终局结果：确认后续争议阶段并重新匹配规则",
        )
    if case.get("eligibility_status") in {"REQUIRES_RECONFIRMATION", "RIGHTS_LOST"}:
        blockers.append("当前抗辩资格需重新核实；旧决定不代表仍有提交权利。")
        action, owner, reason = "RESOLVE_RESPONSE", "OPERATOR", "核实当前规则与剩余处理权利"
    if case.get("outcome_verification_required"):
        action, owner, reason = (
            "VERIFY_OUTCOME",
            "OPERATOR",
            "核实上游来源与终局依据后再处理结果",
        )
    deadlines = deepcopy(case.get("deadlines") or rule.get("deadlines") or {})
    sla = current_sla(case, owner=owner, action=action, now=now)
    sla_risk = sla["risk"]
    citations = [{k: rule.get(k) for k in ("source_id", "source_locator", "rule_version")}]
    if not rule.get("source_id"):
        citations = []
    return {
        "case_id": case["id"],
        "revision": case["revision"],
        "context": {k: case.get(k) for k in ("owner", "scheme", "channel", "reason_code", "stage")},
        "rule_status": rule_status,
        "source_citations": citations,
        "checklist": checklist,
        "missing_required": missing,
        "missing_critical": missing_critical,
        "readiness": {
            "submitted": len(checklist) - len(missing),
            "required": len(checklist),
            "percent": round(100 * (len(checklist) - len(missing)) / len(checklist))
            if checklist
            else 0,
            "boundary": MATERIAL_REGISTRATION_BOUNDARY,
        },
        "next_action": {"action": action, "owner": owner, "reason": reason},
        "blockers": blockers,
        "deadlines": deadlines,
        "sla": sla,
        "sla_risk": sla_risk,
        "escalation_required": rule_status not in ("VERIFIED", "HUMAN_CONFIRMED")
        or sla_risk in ("OVERDUE", "AT_RISK")
        or bool(missing_critical),
        "summary": (
            f"{case.get('scheme')} {case.get('reason_code')} · {case.get('stage')}。"
            f"下一步：{reason}。"
        ),
        "proposal": {
            "case_id": case["id"],
            "expected_revision": case["revision"],
            "action": action,
            "requires_confirmation": True,
        },
        "agent": {
            "provider": "DETERMINISTIC",
            "model": "case-planner-v2",
            "prompt_version": "2026-09-08",
        },
        "similar_cases": [],
    }
