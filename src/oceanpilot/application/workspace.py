"""Shared deterministic case workspace and explicit, versioned human commands."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from oceanpilot.application.case_review import AgentTurnRecord
from oceanpilot.application.chargeback_packager import has_exact_rule
from oceanpilot.application.chargeback_supervisor import ChargebackSupervisor
from oceanpilot.application.errors import ConcurrentCaseWrite
from oceanpilot.application.knowledge_base import RuleCatalog
from oceanpilot.application.workspace_ports import (
    WorkspaceBundle,
    WorkspaceError,
    WorkspaceStore,
    WorkspaceUnit,
)
from oceanpilot.application.workspace_summary import render_summary
from oceanpilot.domain.chargeback import (
    CardNetwork,
    ChargebackEvidenceCode,
    DisputeReasonCode,
    assess_chargeback,
    required_evidence_for,
)
from oceanpilot.domain.evidence_catalog import describe, label_of
from oceanpilot.domain.reason_catalog import reason_label
from oceanpilot.domain.security import assert_no_sensitive_data

SUMMARY_TITLE = "案件复核摘要（合成示例）"
UNVERIFIED_ITEMS = [
    "真实文件正文未读取；仅登记合成材料元数据。",
    "材料真实性及跨材料内容一致性尚未核验。",
    "卡组织规则的地区、时效及正式适用性尚待企业专家复核。",
    "材料就绪度仅表示内部清单完成度，不代表胜诉率或业务准确率。",
]
BASE_ACTIONS = [
    "CONFIRM_REASON",
    "SET_NETWORK",
    "REGISTER_MATERIAL",
    "WITHDRAW_MATERIAL",
    "FINALIZE",
    "ADD_CONCERN",
]
SAMPLES = {
    "A": (
        "A · Visa 10.4 主案例",
        "VISA",
        "FRAUD_CARD_NOT_PRESENT",
        "合成正式争议：持卡人提出 Visa 10.4 无卡未授权交易争议。"
        "假定已进入正式争议流程，金额 USD 120。初始预置时保留 3DS 登记缺口。",
    ),
    "B": (
        "B · 撤回关键材料后阻断",
        "VISA",
        "FRAUD_CARD_NOT_PRESENT",
        "合成正式争议：初始样例曾完成材料登记复核，之后撤回关键 3DS 材料。"
        "初始状态的旧审核仅作为历史，后续状态以当前登记和复核记录为准。",
    ),
    "C": (
        "C · Visa 13.1 跨场景",
        "VISA",
        "PRODUCT_NOT_RECEIVED",
        "合成正式争议：持卡人提出 Visa 13.1 商品未收到争议。"
        "假定已进入正式争议流程，初始预置缺签收证明。",
    ),
}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


class WorkspaceService:
    def __init__(
        self,
        store: WorkspaceStore,
        catalog: RuleCatalog,
        supervisor: ChargebackSupervisor,
        runtime: dict[str, Any],
    ) -> None:
        self.store = store
        self.catalog = catalog
        self.supervisor = supervisor
        self.runtime = runtime

    def rule_fingerprint(self, bundle: WorkspaceBundle) -> str:
        state = bundle.state
        if state.reason_code is None or state.card_network is None:
            return _digest(self.rule(bundle))
        entry = self.catalog.lookup(state.reason_code, card_network=state.card_network.value)
        detail = self.catalog.get_rule(entry.rule_version_id) if entry.rule_version_id else None
        return _digest({"entry": asdict(entry), "detail": asdict(detail) if detail else None})

    def rule(self, bundle: WorkspaceBundle) -> dict[str, Any]:
        state = bundle.state
        base = {
            "match_status": "NO_EXACT_MAPPING",
            "rule_version_id": None,
            "scheme_reason_code": None,
            "scheme": state.card_network.value if state.card_network else None,
            "display_name": "无精确匹配，仅使用内部材料清单",
            "rule_version": None,
            "source_document": None,
            "source_section": None,
            "source_url": None,
            "verification_status": "UNVERIFIED_SUMMARY",
            "limitation": "未匹配到当前卡组织及原因的具体规则；内部演示清单不能作为正式依据。",
        }
        if state.reason_code is None or state.card_network is None:
            return base
        entry = self.catalog.lookup(state.reason_code, card_network=state.card_network.value)
        if not has_exact_rule(entry):
            return base
        detail = self.catalog.get_rule(entry.rule_version_id)
        if detail is None:
            return base
        return base | {
            "match_status": "EXACT_MATCH",
            "rule_version_id": detail.rule_version_id,
            "scheme_reason_code": detail.scheme_reason_code,
            "scheme": detail.scheme,
            "display_name": detail.display_name,
            "rule_version": detail.version_label,
            "source_document": detail.document.title,
            "source_section": detail.source_section,
            "source_url": detail.document.source_url,
            "verification_status": detail.verification_status,
            "limitation": detail.limitation,
        }

    def view(
        self, case_id: str, role: str, bundle: WorkspaceBundle | None = None
    ) -> dict[str, Any]:
        bundle = bundle or self.store.read(case_id)
        state, info = bundle.state, bundle.info
        assessment = (
            assess_chargeback(state.reason_code, state.collected) if state.reason_code else None
        )
        rule_digest = self.rule_fingerprint(bundle)
        rule = self.rule(bundle)
        if self.rule_fingerprint(bundle) != rule_digest:
            raise WorkspaceError("RULE_CHANGED", "规则读取期间变化，请刷新案件。")
        missing = []
        for item in assessment.evidence_breakdown if assessment else ():
            if not item.present:
                missing.append(
                    {
                        "code": item.code.value,
                        "label": label_of(item.code),
                        "critical": item.critical,
                        "why": describe(item.code).why,
                        "what_changes": "补齐此关键登记项；其他缺口与疑点仍需处理，正文仍待核验。"
                        if item.critical
                        else "提高材料清单就绪度；内容仍待核验。",
                    }
                )
        open_concerns = [item for item in bundle.concerns if item["status"] == "OPEN"]
        unknown_sources = [
            item for item in bundle.materials if item["active"] and item["source"] == "UNKNOWN"
        ]
        current = next(
            (
                item
                for item in reversed(bundle.reviews)
                if item["case_revision"] == state.revision
                and item.get("rule_fingerprint") == rule_digest
            ),
            None,
        )
        review_status = current["status"] if current else "UNREVIEWED"
        if not state.reason_code or not state.reason_confirmed:
            phase, reason, owner = "REASON_PROPOSED", "需要人工确认案件原因。", "MERCHANT"
        elif open_concerns or unknown_sources:
            phase, reason, owner = (
                "NEEDS_REVIEW",
                "存在未解决的人工登记疑点或来源不明材料，暂停自动推进。",
                "BUSINESS",
            )
        elif assessment and assessment.missing_critical:
            phase, reason, owner = (
                "CRITICAL_MISSING",
                "关键材料缺失，不能进入正式评估。",
                "MERCHANT",
            )
        elif missing:
            phase, reason, owner = (
                "LIMITED_ANALYSIS",
                "普通材料仍有缺口，仅允许有限分析。",
                "MERCHANT",
            )
        elif rule["match_status"] != "EXACT_MATCH":
            phase, reason, owner = "NO_EXACT_RULE", rule["limitation"], "BUSINESS"
        elif review_status == "APPROVED":
            phase, reason, owner = (
                "HUMAN_APPROVED",
                "当前版本材料登记复核已通过；正文与正式规则适用性仍未核验。",
                "BUSINESS",
            )
        elif review_status in ("NEEDS_MORE_INFO", "REJECTED"):
            phase, reason, owner = review_status, current["summary"], "MERCHANT"
        else:
            phase, reason, owner = (
                "READY_FOR_REVIEW",
                "内部登记清单齐全，等待业务人员复核当前版本。",
                "BUSINESS",
            )
        can_approve = bool(
            assessment
            and not missing
            and not open_concerns
            and not unknown_sources
            and state.reason_confirmed
            and rule["match_status"] == "EXACT_MATCH"
        )
        labels = {
            "REASON_PROPOSED": "待确认原因",
            "NEEDS_REVIEW": "疑点待复核",
            "CRITICAL_MISSING": "关键材料阻断",
            "LIMITED_ANALYSIS": "有限分析",
            "NO_EXACT_RULE": "无精确规则",
            "HUMAN_APPROVED": "登记复核通过",
            "NEEDS_MORE_INFO": "已退回补证",
            "REJECTED": "复核驳回",
            "READY_FOR_REVIEW": "待登记复核",
        }
        actions = list(BASE_ACTIONS)
        if role == "BUSINESS":
            actions += ["REVIEW", "RESOLVE_CONCERN", "GENERATE_SUMMARY"]
        materials = [
            item | {"label": label_of(ChargebackEvidenceCode(item["code"]))}
            for item in bundle.materials
        ]
        total = len(assessment.required_evidence) if assessment else 0
        present = len(assessment.present_evidence) if assessment else 0
        summary_items = [self.summary_metadata(item) for item in bundle.summaries]
        latest = next(
            (
                turn
                for turn in bundle.turns
                if turn.get("case_id") == case_id
                and turn.get("case_revision") == state.revision
                and turn.get("card_network")
                == (state.card_network.value if state.card_network else None)
                and turn.get("turn_kind") in ("CASE_CREATED", "CASE_ANALYZED")
                and turn.get("rule_fingerprint") == rule_digest
            ),
            None,
        )
        return {
            "case_id": case_id,
            "title": info.get("title", f"合成案件 {case_id[:8]}"),
            "description": info.get("description", "旧版合成案件；原说明未持久化。"),
            "revision": state.revision,
            "phase": phase,
            "phase_label": labels[phase],
            "missing_count": len(missing),
            "next_actor": owner,
            "created_at": info["created_at"],
            "updated_at": info["updated_at"],
            "review_status": review_status,
            "synthetic": True,
            "scenario": info.get("scenario"),
            "formal_dispute": info.get("formal_dispute", True),
            "card_network": state.card_network.value if state.card_network else None,
            "reason_code": state.reason_code.value if state.reason_code else None,
            "reason_label": reason_label(state.reason_code) if state.reason_code else "待确认",
            "reason_confirmed": state.reason_confirmed,
            "readiness": {
                "present": present,
                "total": total,
                "ratio": str(assessment.completeness) if assessment else "0",
                "meaning": "内部材料登记清单完成度；不代表胜诉率、真实性或正文核验。",
            },
            "materials": materials,
            "missing": missing,
            "rule_reference": rule,
            "rule_fingerprint": rule_digest,
            "review": {
                "status": review_status,
                "current_record": current,
                "history": bundle.reviews,
                "stale": bool(bundle.reviews and current is None),
            },
            "concerns": bundle.concerns,
            "timeline": bundle.timeline,
            "gate": {
                "status": phase,
                "reason": reason,
                "can_review": can_approve,
                "can_package": can_approve,
                "requires_human": True,
            },
            "next_action": {
                "label": "补充材料"
                if owner == "MERCHANT"
                else "复核疑点"
                if open_concerns
                else "生成复核摘要"
                if current
                else "复核当前登记清单",
                "reason": reason,
                "owner": owner,
                "required_materials": [item["code"] for item in missing],
                "expected_state": "更新登记状态并使旧审核失效"
                if owner == "MERCHANT"
                else "留下当前版本人工复核记录或摘要",
                "approval_required": True,
            },
            "allowed_actions": actions,
            "runtime": self.runtime,
            "latest_analysis": latest,
            "summaries": summary_items,
            "unverified_items": list(UNVERIFIED_ITEMS),
        }

    @staticmethod
    def summary_metadata(item: dict[str, Any]) -> dict[str, Any]:
        sid = item["summary_id"]
        return {key: item[key] for key in ("summary_id", "case_id", "revision", "generated_at")} | {
            "title": SUMMARY_TITLE,
            "html_url": f"/api/v1/workspace/summaries/{sid}?format=html",
            "json_url": f"/api/v1/workspace/summaries/{sid}?format=json",
        }

    def execute(self, command: dict[str, Any], role: str, actor: str) -> dict[str, Any]:
        # Server identifiers are not material text; digit runs inside UUIDs are
        # not phone/card data. Scan the user-authored operation fields instead.
        assert_no_sensitive_data(
            {
                key: value
                for key, value in command["data"].items()
                if key not in ("concern_id", "expected_rule_fingerprint")
            }
        )
        assert_no_sensitive_data({"actor": actor})
        if not command["confirmed"]:
            raise WorkspaceError("CONFIRMATION_REQUIRED", "需要操作人员明确确认。", 422)
        action, data = command["action"], command["data"]
        if action in ("REVIEW", "RESOLVE_CONCERN") and role != "BUSINESS":
            raise WorkspaceError("BUSINESS_ROLE_REQUIRED", "此操作需要业务复核演示角色。", 403)
        prepared = None
        if action == "CREATE_CASE":
            if not data.get("formal_dispute"):
                raise WorkspaceError(
                    "FORMAL_DISPUTE_REQUIRED", "请先确认这是已进入正式争议流程的合成案件。", 422
                )
            # Classification is performed before opening the write transaction. A
            # repeated command may repeat a model read, but cannot create a second case.
            from oceanpilot.application.chargeback_supervisor import ChargebackCaseState

            prepared = ChargebackCaseState()
            self.supervisor.intake(prepared, data["description"])

        def apply(unit: WorkspaceUnit) -> dict[str, Any]:
            if action in ("CREATE_CASE", "COPY_SAMPLE"):
                case_id = self._create(unit, action, data, prepared, actor)
            else:
                case_id = command["case_id"]
                bundle = unit.bundle(case_id)
                if bundle.state.revision != command["expected_revision"]:
                    raise ConcurrentCaseWrite()
                self._mutate(unit, case_id, action, data, role, actor, bundle)
            state = unit.cases.load(case_id)
            assert state is not None
            event_id = unit.record(case_id, action, "已明确确认并执行合成案件操作。", actor)
            return {
                "status": "APPLIED",
                "receipt": {
                    "command_id": command["command_id"],
                    "case_id": case_id,
                    "revision": state.revision,
                    "audit_event_id": event_id,
                    "applied_at": _now(),
                    "result": action,
                },
            }

        result = self.store.run(command, role, actor, apply)
        return result | {"case": self.view(result["receipt"]["case_id"], role)}

    def _create(self, unit, action, data, prepared, actor) -> str:
        case_id = unit.cases.create()
        state = unit.cases.load(case_id)
        assert state is not None
        sample = data.get("sample") if action == "COPY_SAMPLE" else None
        if sample:
            title, network, reason, description = SAMPLES[sample]
            state.reason_code, state.reason_confirmed = DisputeReasonCode(reason), True
            info = {
                "title": title,
                "description": description,
                "scenario": sample,
                "formal_dispute": True,
            }
        else:
            state.reason_code, state.reason_confirmed = (
                prepared.reason_code,
                prepared.reason_confirmed,
            )
            network = data.get("card_network")
            info = {
                "title": data.get("title") or data["description"][:60],
                "description": data["description"],
                "scenario": None,
                "formal_dispute": True,
            }
        unit.cases.save(case_id, state)
        if network:
            state = unit.cases.set_card_network(case_id, CardNetwork(network), state.revision)
        unit.set_info(case_id, info)
        if sample:
            required = list(required_evidence_for(state.reason_code))
            critical = (
                ChargebackEvidenceCode.THREEDS_AUTHENTICATION
                if sample in ("A", "B")
                else ChargebackEvidenceCode.PROOF_OF_DELIVERY
            )
            order = [item for item in required if item != critical] + (
                [critical] if sample == "B" else []
            )
            for code in order:
                self._register(
                    unit,
                    case_id,
                    {
                        "evidence_code": code.value,
                        "file_name": f"synthetic-{code.value}.txt",
                        "source": "SYNTHETIC_TEMPLATE",
                    },
                    actor,
                )
            if sample == "B":
                self._review(
                    unit,
                    case_id,
                    {
                        "decision": "APPROVED",
                        "summary": "合成样例：已复核登记清单；正文未读取。",
                        "scope": ["材料登记清单", "内部处理门槛"],
                    },
                    "样例业务复核员",
                )
                unit.cases.withdraw_latest_evidence(case_id, critical)
                unit.withdraw_material(case_id, critical.value)
        return case_id

    def _register(self, unit, case_id, data, actor) -> None:
        state = unit.cases.load(case_id)
        code = ChargebackEvidenceCode(data["evidence_code"])
        if code in state.collected:
            raise WorkspaceError("MATERIAL_ALREADY_REGISTERED", "该材料已登记，请查看当前案件。")
        state.collected.add(code)
        state.collection_finalized = False
        unit.cases.save(case_id, state)
        unit.register_material(
            case_id,
            {
                "code": code.value,
                "file_name": data["file_name"],
                "source": data["source"],
                "registered_at": _now(),
                "registered_by": actor,
                "registered_revision": state.revision,
                "content_verification": "NOT_READ",
                "active": True,
                "withdrawn_at": None,
            },
        )
        if data["source"] == "UNKNOWN":
            self._concern(
                unit,
                case_id,
                {
                    "kind": "SOURCE_ISSUE",
                    "field": code.value,
                    "original_value": "UNKNOWN",
                    "proposed_value": "待人工说明来源",
                    "original_source": "材料登记",
                    "proposed_source": actor,
                    "summary": "提交方未说明材料来源，暂停推进。",
                },
                actor,
            )

    def _concern(self, unit, case_id, data, actor) -> None:
        unit.touch(case_id)
        state = unit.cases.load(case_id)
        unit.add_concern(
            case_id,
            data
            | {
                "reported_by": actor,
                "reported_at": _now(),
                "case_revision": state.revision,
                "resolution": None,
                "resolved_by": None,
                "resolved_at": None,
                "resolution_summary": None,
            },
        )

    def _mutate(self, unit, case_id, action, data, role, actor, bundle) -> None:
        state = bundle.state
        if action == "REGISTER_MATERIAL":
            self._register(unit, case_id, data, actor)
        elif action == "WITHDRAW_MATERIAL":
            code = ChargebackEvidenceCode(data["evidence_code"])
            unit.cases.withdraw_evidence(case_id, code)
            unit.withdraw_material(case_id, code.value)
        elif action in ("CONFIRM_REASON", "SET_NETWORK"):
            field = "reason_code" if action == "CONFIRM_REASON" else "card_network"
            old = getattr(state, field)
            value = data.get(field) or (old.value if old else None)
            if not value:
                raise WorkspaceError("REASON_REQUIRED", "请选择实际争议原因。", 422)
            if old and old.value != value:
                self._concern(
                    unit,
                    case_id,
                    {
                        "kind": "FACT_CONFLICT",
                        "field": field,
                        "original_value": old.value,
                        "proposed_value": value,
                        "original_source": "当前案件版本",
                        "proposed_source": actor,
                        "summary": "新选择与当前记录不同，须业务人员明确复核。",
                    },
                    actor,
                )
            elif field == "card_network":
                unit.cases.set_card_network(case_id, CardNetwork(value), state.revision)
            else:
                state.reason_code, state.reason_confirmed = DisputeReasonCode(value), True
                unit.cases.save(case_id, state)
        elif action == "FINALIZE":
            state.collection_finalized = True
            unit.cases.save(case_id, state)
        elif action == "ADD_CONCERN":
            self._concern(unit, case_id, data, actor)
        elif action == "RESOLVE_CONCERN":
            concern = next(
                (
                    item
                    for item in bundle.concerns
                    if item["concern_id"] == data["concern_id"] and item["status"] == "OPEN"
                ),
                None,
            )
            if concern is None:
                raise WorkspaceError("CONCERN_NOT_OPEN", "疑点已变化，请刷新案件。")
            if concern["kind"] == "SOURCE_ISSUE" and any(
                item["active"] and item["code"] == concern["field"] and item["source"] == "UNKNOWN"
                for item in bundle.materials
            ):
                raise WorkspaceError(
                    "SOURCE_STILL_UNKNOWN",
                    "该材料来源仍不明。请先撤回并说明来源后重新登记，再由业务人员复核此疑点。",
                )
            resolution_summary = data["summary"]
            resolved_fact = None
            if concern["field"] in ("reason_code", "card_network"):
                current_fact = getattr(state, concern["field"])
                current_value = current_fact.value if current_fact else None
                resolved_fact = {
                    "field": concern["field"],
                    "value_before": current_value,
                    "case_revision_before": state.revision,
                }
                if current_value != concern["original_value"]:
                    if data["resolution"] != "ACKNOWLEDGE":
                        raise WorkspaceError(
                            "CONCERN_STALE",
                            "该字段已在其他处理后变化；旧对照不能用于保留或采纳。"
                            "可明确知悉并关闭旧疑点，或按当前事实重新登记分歧。",
                        )
                    resolution_summary = (
                        "当前事实已变化，仅关闭旧疑点，不采纳旧建议。 " + resolution_summary
                    )
            if data["resolution"] == "ACCEPT_PROPOSED":
                if concern["field"] in ("reason_code", "card_network"):
                    enum_type = (
                        DisputeReasonCode if concern["field"] == "reason_code" else CardNetwork
                    )
                    try:
                        enum_type(concern["proposed_value"])
                    except (ValueError, TypeError):
                        raise WorkspaceError(
                            "INVALID_PROPOSED_FACT",
                            "建议值不属于允许的原因或卡组织，请重新登记。",
                            422,
                        ) from None
                unit.correct_fact(case_id, concern["field"], concern["proposed_value"])
            if resolved_fact is not None:
                resolved_fact["value_after"] = (
                    concern["proposed_value"]
                    if data["resolution"] == "ACCEPT_PROPOSED"
                    else resolved_fact["value_before"]
                )
            unit.touch(case_id)
            unit.resolve_concern(
                case_id,
                concern["concern_id"],
                {
                    "resolution": data["resolution"],
                    "resolved_by": actor,
                    "resolved_at": _now(),
                    "resolution_summary": resolution_summary,
                    "resolved_fact": resolved_fact,
                },
            )
        elif action == "REVIEW":
            expected_rules = data.get("expected_rule_fingerprint")
            if not expected_rules:
                raise WorkspaceError(
                    "RULE_SNAPSHOT_REQUIRED", "请先读取当前规则并预览本版本复核范围。", 422
                )
            if expected_rules != self.rule_fingerprint(bundle):
                raise WorkspaceError("RULE_CHANGED", "规则在预览后变化，请刷新并重新确认复核范围。")
            view = self.view(case_id, role, bundle)
            if data["decision"] == "APPROVED" and not view["gate"]["can_review"]:
                raise WorkspaceError("REVIEW_BLOCKED", view["gate"]["reason"])
            self._review(unit, case_id, data, actor)
        else:
            raise WorkspaceError("UNKNOWN_ACTION", "不支持此操作。", 422)

    def _review(self, unit, case_id, data, actor) -> None:
        state = unit.cases.load(case_id)
        bundle = unit.bundle(case_id)
        rule_digest = self.rule_fingerprint(bundle)
        expected_rules = data.get("expected_rule_fingerprint")
        if expected_rules is not None and expected_rules != rule_digest:
            raise WorkspaceError("RULE_CHANGED", "规则在预览后变化，请重新确认本次复核范围。")
        rule = self.rule(bundle)
        if data["decision"] == "APPROVED" and rule["match_status"] != "EXACT_MATCH":
            raise WorkspaceError("REVIEW_BLOCKED", rule["limitation"])
        if self.rule_fingerprint(bundle) != rule_digest:
            raise WorkspaceError("RULE_CHANGED", "规则在复核期间变化，请刷新后重新确认。")
        turn_id = str(uuid4())
        proposal = {
            "status": data["decision"],
            "summary": data["summary"],
            "confirmed_materials": data["scope"],
            "citation_ids": [rule["rule_version_id"]] if rule["rule_version_id"] else [],
            "rule_fingerprint": rule_digest,
        }
        unit.reviews.save_turn(
            AgentTurnRecord(
                turn_id,
                case_id,
                state.revision,
                "HUMAN_REVIEW_FORM",
                json.dumps(
                    {
                        "kind": "HUMAN_REVIEW_FORM",
                        "case_id": case_id,
                        "case_revision": state.revision,
                        "proposal": proposal,
                    },
                    ensure_ascii=False,
                ),
                json.dumps(proposal, ensure_ascii=False),
                datetime.now(UTC),
            )
        )
        unit.reviews.confirm_review(
            case_id=case_id,
            source_turn_id=turn_id,
            expected_revision=state.revision,
            confirmed_by=actor,
        )
        if self.rule_fingerprint(bundle) != rule_digest:
            raise WorkspaceError("RULE_CHANGED", "规则在复核期间变化，请刷新后重新确认。")

    def generate_summary(
        self, case_id: str, expected_revision: int, role: str, actor: str
    ) -> dict[str, Any]:
        if role != "BUSINESS":
            raise WorkspaceError("BUSINESS_ROLE_REQUIRED", "请由业务人员生成复核摘要。", 403)
        bundle = self.store.read(case_id)
        if bundle.state.revision != expected_revision:
            raise ConcurrentCaseWrite()
        rule_digest = self.rule_fingerprint(bundle)

        def validate() -> None:
            if self.rule_fingerprint(bundle) != rule_digest:
                raise WorkspaceError("RULE_CHANGED", "规则在生成期间变化，请重新生成摘要。")

        view = self.view(case_id, role, bundle)
        validate()
        snapshot = {
            "summary_id": str(uuid4()),
            "title": SUMMARY_TITLE,
            "case_id": case_id,
            "revision": expected_revision,
            "generated_at": _now(),
            "generated_by": actor,
            "case": view,
            "synthetic": True,
            "rule_fingerprint": rule_digest,
            "notice": "材料登记与人工复核摘要；不是官方可提交证据包。假定已进入正式争议流程。",
        }
        rendered = render_summary(snapshot)

        self.store.save_summary(case_id, expected_revision, snapshot, rendered, validate)
        return self.summary_metadata(snapshot)
