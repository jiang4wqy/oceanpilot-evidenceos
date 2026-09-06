"""Durable workspace acceptance tests against real temporary SQLite databases."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest

import oceanpilot.application.workspace as workspace_module
from oceanpilot.adapters.knowledge.rule_repository import (
    SqliteRuleRepository,
    initialize_rule_database,
)
from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.adapters.persistence.chargeback_sqlite import initialize_chargeback_schema
from oceanpilot.adapters.persistence.workspace_sqlite import (
    SqliteWorkspaceStore,
    initialize_workspace_schema,
)
from oceanpilot.application.chargeback_agents import (
    ChargebackAssessAgent,
    EvidenceAgent,
    IntakeAgent,
)
from oceanpilot.application.chargeback_supervisor import ChargebackSupervisor
from oceanpilot.application.errors import ConcurrentCaseWrite, PersistenceInvariantViolation
from oceanpilot.application.workspace import SUMMARY_TITLE, WorkspaceService
from oceanpilot.application.workspace_ports import WorkspaceError
from oceanpilot.domain.chargeback import ChargebackEvidenceCode as Code
from oceanpilot.domain.chargeback import DisputeReasonCode

MERCHANT = "synthetic-merchant"
BUSINESS = "synthetic-business-reviewer"


@dataclass
class WorkspaceHarness:
    path: Path
    rule_path: Path
    service: WorkspaceService
    model: ScriptedModelProvider

    def restart(self):
        return build_service(self.path, self.rule_path)[0]


def build_service(path, rule_path):
    model = ScriptedModelProvider(default_text="not-json")
    supervisor = ChargebackSupervisor(
        intake=IntakeAgent(model),
        evidence=EvidenceAgent(model),
        assess=ChargebackAssessAgent(model),
    )
    service = WorkspaceService(
        SqliteWorkspaceStore(path),
        SqliteRuleRepository(rule_path),
        supervisor,
        {"mode": "OFFLINE_FALLBACK", "provider": "SCRIPTED", "model": "synthetic"},
    )
    return service, model


@pytest.fixture
def workspace(tmp_path):
    path, rule_path = tmp_path / "cases.db", tmp_path / "rules.db"
    initialize_chargeback_schema(path)
    initialize_workspace_schema(path)
    initialize_rule_database(rule_path)
    service, model = build_service(path, rule_path)
    return WorkspaceHarness(path, rule_path, service, model)


def command(action, data, case=None, *, command_id=None):
    return {
        "command_id": command_id or str(uuid4()),
        "action": action,
        "confirmed": True,
        "data": data,
        "case_id": case["case_id"] if case else None,
        "expected_revision": case["revision"] if case else None,
    }


def apply(service, action, data, case=None, *, role="MERCHANT"):
    return service.execute(
        command(action, data, case), role, BUSINESS if role == "BUSINESS" else MERCHANT
    )["case"]


def sample(service, name="A"):
    return apply(service, "COPY_SAMPLE", {"sample": name})


def register(service, case, code, *, source="SYNTHETIC_TEMPLATE", file_name="synthetic.txt"):
    return apply(
        service,
        "REGISTER_MATERIAL",
        {"evidence_code": code.value, "source": source, "file_name": file_name},
        case,
    )


def ready_a(service):
    case = sample(service)
    return register(service, case, Code.THREEDS_AUTHENTICATION)


def review_command(case, decision="APPROVED"):
    return command(
        "REVIEW",
        {
            "decision": decision,
            "summary": "合成材料登记清单人工复核；正文真实性未核验。",
            "scope": ["材料登记清单", "当前版本缺口及内部处理门槛"],
            "expected_rule_fingerprint": case["rule_fingerprint"],
        },
        case,
    )


def review(service, case, decision="APPROVED"):
    return service.execute(review_command(case, decision), "BUSINESS", BUSINESS)["case"]


def row_counts(path):
    with sqlite3.connect(path) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }


def test_sample_a_runs_from_one_critical_gap_to_review_and_persisted_summary(workspace):
    service = workspace.service
    case = sample(service)
    assert case["scenario"] == "A"
    assert case["synthetic"] is True and case["formal_dispute"] is True
    assert case["readiness"]["present"] == 5
    assert case["readiness"]["total"] == 6
    assert case["phase"] == "CRITICAL_MISSING"
    assert [item["code"] for item in case["missing"]] == [Code.THREEDS_AUTHENTICATION.value]
    assert case["missing"][0]["critical"] is True
    assert case["rule_reference"]["scheme_reason_code"] == "10.4"

    complete = register(service, case, Code.THREEDS_AUTHENTICATION)
    assert complete["phase"] == "READY_FOR_REVIEW"
    assert complete["review_status"] == "UNREVIEWED"
    assert all(item["content_verification"] == "NOT_READ" for item in complete["materials"])
    approved = review(service, complete)
    assert approved["phase"] == "HUMAN_APPROVED"
    assert approved["review"]["current_record"]["case_revision"] == approved["revision"]
    assert approved["revision"] > complete["revision"]

    calls_before = len(workspace.model.requests)
    metadata = service.generate_summary(
        approved["case_id"], approved["revision"], "BUSINESS", BUSINESS
    )
    restored = workspace.restart().store.summary(metadata["summary_id"])
    snapshot = restored["snapshot"]
    assert snapshot["title"] == SUMMARY_TITLE
    assert snapshot["revision"] == snapshot["case"]["revision"] == approved["revision"]
    assert snapshot["case"]["review"]["current_record"]["case_revision"] == approved["revision"]
    assert snapshot["case"]["missing"] == []
    assert snapshot["synthetic"] is True
    assert "正文未读取" in restored["html"]
    assert snapshot["case"]["rule_reference"]["verification_status"]
    assert snapshot["case"]["unverified_items"]
    assert len(workspace.model.requests) == calls_before


def test_sample_b_preserves_stale_approval_and_blocks_current_version(workspace):
    case = sample(workspace.service, "B")
    assert case["phase"] == "CRITICAL_MISSING"
    assert case["review_status"] == "UNREVIEWED"
    assert case["review"]["stale"] is True
    assert case["review"]["current_record"] is None
    assert case["review"]["history"][-1]["status"] == "APPROVED"
    assert case["review"]["history"][-1]["case_revision"] < case["revision"]
    withdrawn = [
        item for item in case["materials"] if item["code"] == Code.THREEDS_AUTHENTICATION.value
    ]
    assert len(withdrawn) == 1 and withdrawn[0]["active"] is False
    assert case["gate"]["can_review"] is False
    assert workspace.restart().view(case["case_id"], "BUSINESS")["review"] == case["review"]


def test_sample_c_and_export_use_visa_13_1_without_10_4_copy(workspace):
    case = sample(workspace.service, "C")
    assert case["reason_code"] == DisputeReasonCode.PRODUCT_NOT_RECEIVED.value
    assert case["rule_reference"]["scheme_reason_code"] == "13.1"
    assert case["missing"][0]["code"] == Code.PROOF_OF_DELIVERY.value
    meta = workspace.service.generate_summary(
        case["case_id"], case["revision"], "BUSINESS", BUSINESS
    )
    summary = workspace.service.store.summary(meta["summary_id"])
    assert "13.1" in summary["html"]
    assert "10.4" not in summary["html"]
    assert summary["snapshot"]["case"]["review_status"] == "UNREVIEWED"


@pytest.mark.parametrize("blocker", ["critical", "ordinary", "concern", "unknown_source"])
def test_blockers_never_approve_but_allow_an_explicit_return_for_more_information(
    workspace, blocker
):
    service = workspace.service
    case = sample(service)
    if blocker == "ordinary":
        # Withdraw the latest preloaded ordinary item, then register the critical
        # item. This proves the remaining non-critical gap alone still blocks approval.
        latest = max(
            (item for item in case["materials"] if item["active"]),
            key=lambda item: item["registered_revision"],
        )
        case = apply(service, "WITHDRAW_MATERIAL", {"evidence_code": latest["code"]}, case)
        case = register(service, case, Code.THREEDS_AUTHENTICATION)
        assert all(not item["critical"] for item in case["missing"])
        assert case["phase"] == "LIMITED_ANALYSIS"
    elif blocker == "unknown_source":
        case = register(service, case, Code.THREEDS_AUTHENTICATION, source="UNKNOWN")
        assert case["missing"] == []
        assert case["concerns"][-1]["kind"] == "SOURCE_ISSUE"
    elif blocker == "concern":
        case = register(service, case, Code.THREEDS_AUTHENTICATION)
        case = apply(
            service,
            "ADD_CONCERN",
            {
                "kind": "FACT_CONFLICT",
                "field": "reason_code",
                "original_value": "FRAUD_CARD_NOT_PRESENT",
                "proposed_value": "PRODUCT_NOT_RECEIVED",
                "original_source": "合成案件",
                "proposed_source": "人工记录",
                "summary": "人工记录的原因冲突；未声称读取文件正文。",
            },
            case,
        )
        assert case["missing"] == []
    assert case["gate"]["can_review"] is False
    failed = review_command(case)
    before = row_counts(workspace.path)
    with pytest.raises(WorkspaceError) as blocked:
        service.execute(failed, "BUSINESS", BUSINESS)
    assert blocked.value.code == "REVIEW_BLOCKED"
    assert blocked.value.status == 409
    assert service.store.command(failed["command_id"], "BUSINESS", BUSINESS)["status"] == "UNKNOWN"
    assert row_counts(workspace.path) == before
    returned = review(service, case, "NEEDS_MORE_INFO")
    assert returned["review_status"] == "NEEDS_MORE_INFO"
    assert returned["gate"]["can_review"] is False


def test_merchant_cannot_confirm_business_review(workspace):
    case = ready_a(workspace.service)
    before = row_counts(workspace.path)
    with pytest.raises(WorkspaceError) as forbidden:
        workspace.service.execute(review_command(case), "MERCHANT", MERCHANT)
    assert forbidden.value.status == 403
    assert row_counts(workspace.path) == before


def test_command_replay_survives_restart_without_a_second_case_or_receipt(workspace):
    cmd = command("COPY_SAMPLE", {"sample": "A"})
    first = workspace.service.execute(cmd, "MERCHANT", MERCHANT)
    before = row_counts(workspace.path)
    replayed = workspace.restart().execute(cmd, "MERCHANT", MERCHANT)
    assert replayed["status"] == "REPLAYED"
    assert replayed["receipt"] == first["receipt"]
    assert replayed["case"]["case_id"] == first["case"]["case_id"]
    assert row_counts(workspace.path) == before
    assert (
        workspace.restart().store.command(cmd["command_id"], "MERCHANT", MERCHANT)["receipt"]
        == first["receipt"]
    )


@pytest.mark.parametrize("change", ["payload", "role", "actor"])
def test_reused_command_id_cannot_apply_other_content_or_identity(workspace, change):
    cmd = command("COPY_SAMPLE", {"sample": "A"})
    workspace.service.execute(cmd, "MERCHANT", MERCHANT)
    before = row_counts(workspace.path)
    changed = cmd | {"data": {"sample": "C"}} if change == "payload" else cmd
    with pytest.raises(WorkspaceError) as error:
        workspace.service.execute(
            changed,
            "BUSINESS" if change == "role" else "MERCHANT",
            BUSINESS if change == "actor" else MERCHANT,
        )
    assert error.value.code == "COMMAND_REUSED"
    assert error.value.status == 409
    assert row_counts(workspace.path) == before


@pytest.mark.parametrize(
    "table",
    [
        "chargeback_audit",
        "workspace_case_info",
        "workspace_materials",
        "chargeback_review_decisions",
        "workspace_audit",
        "workspace_commands",
    ],
)
def test_sample_creation_failure_at_each_persistence_stage_rolls_back_every_record(
    workspace, table
):
    # Fail the actual database write after earlier stages may have already run.
    with sqlite3.connect(workspace.path) as connection:
        connection.execute(
            f"CREATE TRIGGER reject_synthetic_write BEFORE INSERT ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'synthetic injected failure'); END"
        )
    cmd = command("COPY_SAMPLE", {"sample": "B"})
    with pytest.raises((sqlite3.Error, PersistenceInvariantViolation)):
        workspace.service.execute(cmd, "MERCHANT", MERCHANT)
    assert not any(row_counts(workspace.path).values())
    assert (
        workspace.service.store.command(cmd["command_id"], "MERCHANT", MERCHANT)["status"]
        == "UNKNOWN"
    )
    with sqlite3.connect(workspace.path) as connection:
        connection.execute("DROP TRIGGER reject_synthetic_write")
    retried = workspace.service.execute(cmd, "MERCHANT", MERCHANT)
    assert retried["status"] == "APPLIED"
    assert len(workspace.service.store.case_ids()) == 1


@pytest.mark.parametrize("action", ["register", "review"])
def test_receipt_failure_rolls_back_material_or_review_and_version_together(workspace, action):
    case = sample(workspace.service) if action == "register" else ready_a(workspace.service)
    before = row_counts(workspace.path)
    cmd = (
        command(
            "REGISTER_MATERIAL",
            {
                "evidence_code": Code.THREEDS_AUTHENTICATION.value,
                "source": "SYNTHETIC_TEMPLATE",
                "file_name": "synthetic.txt",
            },
            case,
        )
        if action == "register"
        else review_command(case)
    )
    with sqlite3.connect(workspace.path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_receipt BEFORE INSERT ON workspace_commands "
            "BEGIN SELECT RAISE(ABORT, 'synthetic injected failure'); END"
        )
    role, actor = ("MERCHANT", MERCHANT) if action == "register" else ("BUSINESS", BUSINESS)
    with pytest.raises(sqlite3.Error):
        workspace.service.execute(cmd, role, actor)
    assert row_counts(workspace.path) == before
    restored = workspace.restart().view(case["case_id"], role)
    assert restored["revision"] == case["revision"]
    assert restored["materials"] == case["materials"]
    assert restored["review"] == case["review"]
    assert workspace.service.store.command(cmd["command_id"], role, actor)["status"] == "UNKNOWN"


def test_export_escapes_user_content_and_does_not_request_a_model(workspace):
    injected = '<script>alert("synthetic")</script>'
    case = apply(
        workspace.service,
        "CREATE_CASE",
        {
            "title": injected,
            "description": "Synthetic 正式争议，客户没有收到商品。 " + injected,
            "formal_dispute": True,
            "card_network": "VISA",
        },
    )
    case = register(
        workspace.service,
        case,
        Code.TRANSACTION_RECEIPT,
        file_name="<img src=x onerror=alert(1)>.txt",
    )
    calls_before = len(workspace.model.requests)
    meta = workspace.service.generate_summary(
        case["case_id"], case["revision"], "BUSINESS", BUSINESS
    )
    saved = workspace.service.store.summary(meta["summary_id"])
    assert saved["snapshot"]["case"]["title"] == injected
    assert injected not in saved["html"]
    assert "&lt;script&gt;" in saved["html"]
    assert "<img " not in saved["html"]
    assert "&lt;img " in saved["html"]
    assert "default-src 'none'" in saved["html"]
    assert len(workspace.model.requests) == calls_before


def test_case_change_during_export_rejects_mixed_version_and_keeps_no_summary(
    workspace, monkeypatch
):
    service = workspace.service
    case = sample(service)
    original_render = workspace_module.render_summary

    def render_and_change(snapshot):
        rendered = original_render(snapshot)
        register(service, case, Code.THREEDS_AUTHENTICATION)
        return rendered

    monkeypatch.setattr(workspace_module, "render_summary", render_and_change)
    with pytest.raises(ConcurrentCaseWrite):
        service.generate_summary(case["case_id"], case["revision"], "BUSINESS", BUSINESS)
    assert service.store.read(case["case_id"]).summaries == []
    assert service.view(case["case_id"], "BUSINESS")["revision"] > case["revision"]


@pytest.mark.parametrize("changed_part", ["version_label", "requirement_content"])
def test_rule_change_during_export_rejects_generation_with_409(
    workspace, monkeypatch, changed_part
):
    service = workspace.service
    case = sample(service)
    original_render = workspace_module.render_summary

    def render_and_change_rule(snapshot):
        rendered = original_render(snapshot)
        with sqlite3.connect(workspace.rule_path) as connection:
            if changed_part == "version_label":
                connection.execute(
                    "UPDATE rule_versions SET version_label='synthetic changed version' "
                    "WHERE rule_version_id=?",
                    (case["rule_reference"]["rule_version_id"],),
                )
            else:
                connection.execute(
                    "UPDATE rule_requirements SET description_zh='合成规则要求在生成期间变化' "
                    "WHERE rule_version_id=?",
                    (case["rule_reference"]["rule_version_id"],),
                )
        return rendered

    monkeypatch.setattr(workspace_module, "render_summary", render_and_change_rule)
    with pytest.raises(WorkspaceError) as conflict:
        service.generate_summary(case["case_id"], case["revision"], "BUSINESS", BUSINESS)
    assert conflict.value.status == 409
    assert conflict.value.code == "RULE_CHANGED"
    assert service.store.read(case["case_id"]).summaries == []


def test_failed_post_insert_summary_validation_rolls_back_the_export(workspace):
    case = sample(workspace.service)
    checks = []

    def validate():
        checks.append(True)
        if len(checks) == 2:
            raise WorkspaceError("RULE_CHANGED", "合成验证期间规则变化。")

    with pytest.raises(WorkspaceError):
        workspace.service.store.save_summary(
            case["case_id"],
            case["revision"],
            {
                "summary_id": str(uuid4()),
                "generated_at": "2026-09-06T00:00:00.000000Z",
                "case_id": case["case_id"],
                "revision": case["revision"],
            },
            "<p>Synthetic</p>",
            validate,
        )
    assert len(checks) == 2
    assert workspace.service.store.read(case["case_id"]).summaries == []


def test_simultaneous_duplicate_commands_apply_once_and_share_the_receipt(workspace):
    cmd = command("COPY_SAMPLE", {"sample": "A"})
    start = Barrier(2)

    def submit():
        start.wait(timeout=2)
        return workspace.service.execute(cmd, "MERCHANT", MERCHANT)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        results = [future.result(timeout=5) for future in futures]
    assert {item["status"] for item in results} == {"APPLIED", "REPLAYED"}
    assert results[0]["receipt"] == results[1]["receipt"]
    assert len(workspace.service.store.case_ids()) == 1
    assert row_counts(workspace.path)["workspace_commands"] == 1


def test_old_summary_remains_immutable_after_material_withdrawal_invalidates_review(workspace):
    service = workspace.service
    case = review(service, ready_a(service))
    metadata = service.generate_summary(case["case_id"], case["revision"], "BUSINESS", BUSINESS)
    saved = service.store.summary(metadata["summary_id"])
    changed = apply(
        service,
        "WITHDRAW_MATERIAL",
        {
            "evidence_code": Code.THREEDS_AUTHENTICATION.value,
        },
        case,
    )
    assert changed["review"]["stale"] is True
    assert changed["review_status"] == "UNREVIEWED"
    assert changed["revision"] > saved["snapshot"]["revision"]
    assert workspace.restart().store.summary(metadata["summary_id"]) == saved
    assert saved["snapshot"]["case"]["review_status"] == "APPROVED"


def test_network_without_exact_rule_blocks_approval_and_exports_explicit_limitation(workspace):
    service = workspace.service
    case = ready_a(service)
    conflicted = apply(service, "SET_NETWORK", {"card_network": "AMEX"}, case)
    assert conflicted["card_network"] == "VISA"
    assert conflicted["phase"] == "NEEDS_REVIEW"
    corrected = apply(
        service,
        "RESOLVE_CONCERN",
        {
            "concern_id": conflicted["concerns"][-1]["concern_id"],
            "resolution": "ACCEPT_PROPOSED",
            "summary": "人工确认合成案件卡组织更正。",
        },
        conflicted,
        role="BUSINESS",
    )
    assert corrected["card_network"] == "AMEX"
    assert corrected["phase"] == "NO_EXACT_RULE"
    assert corrected["rule_reference"]["match_status"] == "NO_EXACT_MAPPING"
    assert corrected["rule_reference"]["rule_version_id"] is None
    with pytest.raises(WorkspaceError) as error:
        review(service, corrected)
    assert error.value.code == "REVIEW_BLOCKED"
    meta = service.generate_summary(
        corrected["case_id"], corrected["revision"], "BUSINESS", BUSINESS
    )
    exported = service.store.summary(meta["summary_id"])["snapshot"]["case"]
    assert exported["rule_reference"]["match_status"] == "NO_EXACT_MAPPING"
    assert "不能作为正式依据" in exported["rule_reference"]["limitation"]


def change_rule_label(workspace, case, label="changed synthetic rule"):
    with sqlite3.connect(workspace.rule_path) as connection:
        connection.execute(
            "UPDATE rule_versions SET version_label=? WHERE rule_version_id=?",
            (label, case["rule_reference"]["rule_version_id"]),
        )


def saved_case_agent(workspace):
    from oceanpilot.adapters.persistence.chargeback_review_sqlite import SqliteCaseReviewStore
    from oceanpilot.adapters.persistence.chargeback_sqlite import SqliteChargebackCaseStore
    from oceanpilot.api.agent_schemas import StrictAgentTurnCodec
    from oceanpilot.application.case_agent import CaseAgentService
    from oceanpilot.application.case_copilot import CaseCopilotAgent
    from oceanpilot.application.chargeback_channel_service import ChargebackChannelService

    service = workspace.service
    return CaseAgentService(
        ChargebackChannelService(service.supervisor, SqliteChargebackCaseStore(workspace.path)),
        CaseCopilotAgent(workspace.model, offline=True),
        SqliteCaseReviewStore(workspace.path),
        service.catalog,
        service.catalog,
        turn_codec=StrictAgentTurnCodec(),
        workspace=service,
        role="BUSINESS",
        actor=BUSINESS,
    )


def analyze_case(agent, case, *, trigger="USER_MESSAGE"):
    from oceanpilot.application.agent_views import AgentRuntime
    from oceanpilot.application.case_agent import AgentTurnCommand

    return agent.create_turn(
        AgentTurnCommand(message="请解释当前材料缺口", case_id=case["case_id"], trigger=trigger),
        AgentRuntime(mode="OFFLINE_FALLBACK", provider="DETERMINISTIC", model="synthetic"),
    )


def test_rule_change_between_view_and_fingerprint_cannot_seal_a_stale_summary(
    workspace, monkeypatch
):
    service = workspace.service
    case = sample(service)
    original_view = service.view

    def view_then_change(*args, **kwargs):
        snapshot = original_view(*args, **kwargs)
        change_rule_label(workspace, case)
        return snapshot

    monkeypatch.setattr(service, "view", view_then_change)
    with pytest.raises(WorkspaceError) as failure:
        service.generate_summary(case["case_id"], case["revision"], "BUSINESS", BUSINESS)
    assert failure.value.code == "RULE_CHANGED"
    assert service.store.read(case["case_id"]).summaries == []


@pytest.mark.parametrize("stale_kind", ["rule_changed", "legacy_missing_fingerprint"])
def test_summary_excludes_same_case_version_analysis_with_stale_or_unknown_rules(
    workspace, stale_kind
):
    import json

    service = workspace.service
    case = sample(service)
    turn = analyze_case(saved_case_agent(workspace), case)
    assert turn.rule_fingerprint == service.rule_fingerprint(service.store.read(case["case_id"]))
    assert (
        service.view(case["case_id"], "BUSINESS")["latest_analysis"]["source_turn_id"]
        == turn.source_turn_id
    )
    if stale_kind == "rule_changed":
        change_rule_label(workspace, case)
    else:
        with sqlite3.connect(workspace.path) as connection:
            row = connection.execute(
                "SELECT response_json FROM chargeback_agent_turns WHERE turn_id=?",
                (turn.source_turn_id,),
            ).fetchone()
            payload = json.loads(row[0])
            payload.pop("rule_fingerprint")
            connection.execute(
                "UPDATE chargeback_agent_turns SET response_json=? WHERE turn_id=?",
                (json.dumps(payload), turn.source_turn_id),
            )
    metadata = service.generate_summary(case["case_id"], case["revision"], "BUSINESS", BUSINESS)
    stored = workspace.restart().store.summary(metadata["summary_id"])
    assert stored["snapshot"]["case"]["revision"] == case["revision"]
    assert stored["snapshot"]["case"]["latest_analysis"] is None
    assert "本摘要使用确定性快照" in stored["html"]


def test_rule_change_during_agent_analysis_prevents_saving_a_current_result(workspace, monkeypatch):
    case = sample(workspace.service)
    agent = saved_case_agent(workspace)
    original = agent._copilot.respond

    def respond_then_change(*args, **kwargs):
        response = original(*args, **kwargs)
        change_rule_label(workspace, case)
        return response

    monkeypatch.setattr(agent._copilot, "respond", respond_then_change)
    before = row_counts(workspace.path)["chargeback_agent_turns"]
    with pytest.raises(WorkspaceError) as failure:
        analyze_case(agent, case)
    assert failure.value.code == "RULE_CHANGED"
    assert row_counts(workspace.path)["chargeback_agent_turns"] == before


def test_reopen_does_not_replay_analysis_after_rules_change_at_same_case_revision(workspace):
    case = sample(workspace.service)
    agent = saved_case_agent(workspace)
    first = analyze_case(agent, case, trigger="CASE_OPENED")
    replayed = analyze_case(agent, case, trigger="CASE_OPENED")
    assert replayed.source_turn_id == first.source_turn_id
    change_rule_label(workspace, case)
    refreshed = analyze_case(agent, case, trigger="CASE_OPENED")
    assert refreshed.source_turn_id != first.source_turn_id
    assert refreshed.rule_fingerprint != first.rule_fingerprint
    assert refreshed.case_revision == first.case_revision


def resolve(service, case, concern_id, resolution):
    return apply(
        service,
        "RESOLVE_CONCERN",
        {
            "concern_id": concern_id,
            "resolution": resolution,
            "summary": "人工复核当前登记及处理边界。",
        },
        case,
        role="BUSINESS",
    )


@pytest.mark.parametrize("resolution", ["KEEP_ORIGINAL", "ACCEPT_PROPOSED", "ACKNOWLEDGE"])
def test_unknown_material_source_requires_new_registration_before_resolving(workspace, resolution):
    service = workspace.service
    case = register(service, sample(service), Code.THREEDS_AUTHENTICATION, source="UNKNOWN")
    concern_id = case["concerns"][-1]["concern_id"]
    before = row_counts(workspace.path)
    with pytest.raises(WorkspaceError) as failure:
        resolve(service, case, concern_id, resolution)
    assert failure.value.code == "SOURCE_STILL_UNKNOWN"
    assert row_counts(workspace.path) == before
    assert service.view(case["case_id"], "BUSINESS")["gate"]["can_review"] is False


def test_source_resolution_keeps_original_registration_history_and_new_source_fact(workspace):
    service = workspace.service
    case = register(service, sample(service), Code.THREEDS_AUTHENTICATION, source="UNKNOWN")
    concern_id = case["concerns"][-1]["concern_id"]
    case = apply(
        service, "WITHDRAW_MATERIAL", {"evidence_code": Code.THREEDS_AUTHENTICATION.value}, case
    )
    case = register(service, case, Code.THREEDS_AUTHENTICATION, source="SYNTHETIC_USER_METADATA")
    assert case["gate"]["can_review"] is False
    case = resolve(service, case, concern_id, "ACKNOWLEDGE")
    assert case["gate"]["can_review"] is True
    records = [m for m in case["materials"] if m["code"] == Code.THREEDS_AUTHENTICATION.value]
    assert len(records) == 2
    assert records[0]["source"] == "UNKNOWN" and records[0]["active"] is False
    assert records[1]["source"] == "SYNTHETIC_USER_METADATA" and records[1]["active"] is True
    assert all(m["content_verification"] == "NOT_READ" for m in records)
    restored = workspace.restart().view(case["case_id"], "BUSINESS")
    assert restored["materials"] == case["materials"]
    assert restored["concerns"][-1]["status"] == "RESOLVED"


@pytest.mark.parametrize("resolution", ["KEEP_ORIGINAL", "ACCEPT_PROPOSED"])
def test_stale_fact_concern_cannot_override_a_later_confirmed_fact(workspace, resolution):
    service = workspace.service
    case = ready_a(service)
    case = apply(service, "SET_NETWORK", {"card_network": "MASTERCARD"}, case)
    first_id = case["concerns"][-1]["concern_id"]
    case = apply(service, "SET_NETWORK", {"card_network": "AMEX"}, case)
    second_id = case["concerns"][-1]["concern_id"]
    case = resolve(service, case, first_id, "ACCEPT_PROPOSED")
    before = row_counts(workspace.path)
    with pytest.raises(WorkspaceError) as failure:
        resolve(service, case, second_id, resolution)
    assert failure.value.code == "CONCERN_STALE"
    assert row_counts(workspace.path) == before
    current = service.view(case["case_id"], "BUSINESS")
    assert current["card_network"] == "MASTERCARD"
    assert current["concerns"][-1]["status"] == "OPEN"
    closed = resolve(service, current, second_id, "ACKNOWLEDGE")
    assert closed["card_network"] == "MASTERCARD"
    decision = closed["concerns"][-1]
    assert decision["original_value"] == "VISA"
    assert decision["proposed_value"] == "AMEX"
    assert (
        decision["resolved_fact"]["value_before"]
        == decision["resolved_fact"]["value_after"]
        == "MASTERCARD"
    )
    assert "当前事实已变化，仅关闭旧疑点，不采纳旧建议" in decision["resolution_summary"]


@pytest.mark.parametrize(
    "field,original", [("card_network", "VISA"), ("reason_code", "FRAUD_CARD_NOT_PRESENT")]
)
def test_invalid_proposed_fact_is_a_recoverable_422_without_partial_mutation(
    workspace, field, original
):
    service = workspace.service
    case = apply(
        service,
        "ADD_CONCERN",
        {
            "kind": "FACT_CONFLICT",
            "field": field,
            "original_value": original,
            "proposed_value": "INVALID_ENUM",
            "original_source": "当前案件",
            "proposed_source": "人工输入",
            "summary": "录入了不受支持的建议值，仍等待人工修正。",
        },
        ready_a(service),
    )
    before = row_counts(workspace.path)
    with pytest.raises(WorkspaceError) as failure:
        resolve(service, case, case["concerns"][-1]["concern_id"], "ACCEPT_PROPOSED")
    assert failure.value.code == "INVALID_PROPOSED_FACT"
    assert failure.value.status == 422
    assert row_counts(workspace.path) == before
    assert service.view(case["case_id"], "BUSINESS")[field] == original


@pytest.mark.parametrize("stale_kind", ["rule_changed", "legacy_missing_fingerprint"])
def test_rule_change_or_unbound_legacy_review_is_history_not_current_approval(
    workspace, stale_kind
):
    import json

    service = workspace.service
    case = review(service, ready_a(service))
    current = case["review"]["current_record"]
    assert current["rule_fingerprint"]
    if stale_kind == "rule_changed":
        change_rule_label(workspace, case)
    else:
        with sqlite3.connect(workspace.path) as connection:
            row = connection.execute(
                "SELECT proposal_json FROM chargeback_agent_turns WHERE turn_id=?",
                (current["source_turn_id"],),
            ).fetchone()
            proposal = json.loads(row[0])
            proposal.pop("rule_fingerprint")
            connection.execute(
                "UPDATE chargeback_agent_turns SET proposal_json=? WHERE turn_id=?",
                (json.dumps(proposal), current["source_turn_id"]),
            )
    metadata = service.generate_summary(case["case_id"], case["revision"], "BUSINESS", BUSINESS)
    exported = service.store.summary(metadata["summary_id"])["snapshot"]["case"]
    assert exported["revision"] == case["revision"]
    assert exported["review_status"] == "UNREVIEWED"
    assert exported["review"]["current_record"] is None
    assert exported["review"]["stale"] is True
    assert exported["review"]["history"][-1]["status"] == "APPROVED"
    turn = analyze_case(saved_case_agent(workspace), case)
    assert turn.review_status == "UNREVIEWED"
    assert turn.review_decision is None


def test_rule_change_while_confirming_review_rolls_back_decision_and_receipt(
    workspace, monkeypatch
):
    from oceanpilot.adapters.persistence.chargeback_review_sqlite import SqliteCaseReviewStore

    service = workspace.service
    case = ready_a(service)
    original = SqliteCaseReviewStore.confirm_review

    def confirm_then_change(*args, **kwargs):
        result = original(*args, **kwargs)
        change_rule_label(workspace, case)
        return result

    before = row_counts(workspace.path)
    monkeypatch.setattr(SqliteCaseReviewStore, "confirm_review", confirm_then_change)
    with pytest.raises(WorkspaceError) as failure:
        review(service, case)
    assert failure.value.code == "RULE_CHANGED"
    assert row_counts(workspace.path) == before
    assert service.view(case["case_id"], "BUSINESS")["revision"] == case["revision"]


def test_agent_review_proposal_preserves_rule_binding_and_rejects_changed_rules(workspace):
    from oceanpilot.application.agent_views import AgentRuntime
    from oceanpilot.application.case_agent import AgentTurnCommand

    service = workspace.service
    case = ready_a(service)
    agent = saved_case_agent(workspace)
    turn = agent.create_turn(
        AgentTurnCommand(message="审核通过，请生成登记复核提案", case_id=case["case_id"]),
        AgentRuntime(mode="OFFLINE_FALLBACK", provider="DETERMINISTIC", model="synthetic"),
    )
    assert turn.review_proposal.status == "APPROVED"
    change_rule_label(workspace, case)
    before = row_counts(workspace.path)
    with pytest.raises(WorkspaceError) as failure:
        agent.confirm_review(
            case_id=case["case_id"],
            source_turn_id=turn.source_turn_id,
            case_revision=case["revision"],
            confirmed_by=BUSINESS,
        )
    assert failure.value.code == "RULE_CHANGED"
    assert row_counts(workspace.path) == before


def test_active_unknown_material_stays_blocked_even_if_legacy_concern_was_closed(workspace):
    import json

    service = workspace.service
    case = register(service, sample(service), Code.THREEDS_AUTHENTICATION, source="UNKNOWN")
    concern = case["concerns"][-1] | {"status": "RESOLVED", "resolution": "ACKNOWLEDGE"}
    with sqlite3.connect(workspace.path) as connection:
        connection.execute(
            "UPDATE workspace_concerns SET status='RESOLVED',payload=? WHERE concern_id=?",
            (json.dumps(concern), concern["concern_id"]),
        )
    restored = workspace.restart().view(case["case_id"], "BUSINESS")
    assert not any(item["status"] == "OPEN" for item in restored["concerns"])
    assert restored["gate"]["status"] == "NEEDS_REVIEW"
    assert restored["gate"]["can_review"] is False
    with pytest.raises(WorkspaceError) as failure:
        review(service, restored)
    assert failure.value.code == "REVIEW_BLOCKED"


def test_review_requires_the_rule_snapshot_seen_before_human_confirmation(workspace):
    service = workspace.service
    case = ready_a(service)
    missing = review_command(case)
    missing["data"].pop("expected_rule_fingerprint")
    with pytest.raises(WorkspaceError) as failure:
        service.execute(missing, "BUSINESS", BUSINESS)
    assert failure.value.code == "RULE_SNAPSHOT_REQUIRED"
    assert failure.value.status == 422
    change_rule_label(workspace, case)
    before = row_counts(workspace.path)
    with pytest.raises(WorkspaceError) as failure:
        review(service, case)
    assert failure.value.code == "RULE_CHANGED"
    assert row_counts(workspace.path) == before
    refreshed = service.view(case["case_id"], "BUSINESS")
    assert refreshed["revision"] == case["revision"]
    assert refreshed["rule_fingerprint"] != case["rule_fingerprint"]
    approved = review(service, refreshed)
    assert approved["review_status"] == "APPROVED"
    assert approved["review"]["current_record"]["rule_fingerprint"] == refreshed["rule_fingerprint"]


def test_rule_change_after_review_gate_check_cannot_approve_a_different_rule(
    workspace, monkeypatch
):
    service = workspace.service
    case = ready_a(service)
    original = service._review

    def review_then_change(*args, **kwargs):
        change_rule_label(workspace, case)
        return original(*args, **kwargs)

    before = row_counts(workspace.path)
    monkeypatch.setattr(service, "_review", review_then_change)
    with pytest.raises(WorkspaceError) as failure:
        review(service, case)
    assert failure.value.code == "RULE_CHANGED"
    assert row_counts(workspace.path) == before
