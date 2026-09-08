"""Uploaded guideline references enter the workflow only as confirmed rehearsals."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.knowledge.dispute_case_library import DisputeCaseLibrary
from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.dispute_demo import complete_contest
from oceanpilot.config import Settings
from oceanpilot.main import create_app

MERCHANT = "library-api-merchant"
MODEL_ANSWER = "指南案例仅供参考；本案采用风控确认的证据要求与期限。"
_LIBRARY = DisputeCaseLibrary()
_NETWORK_TEMPLATES = [
    preview["reference"]
    for preview in _LIBRARY.list_templates()
    if preview["reference"]["scheme"] in {"VISA", "MASTERCARD"}
]


def headers(role="OPERATOR", merchant=MERCHANT):
    return {
        "X-Demo-Role": role,
        "X-Demo-Actor": "library-api-" + role.lower(),
        "X-Demo-Merchant": merchant,
    }


@pytest.fixture
def stack(tmp_path):
    model = ScriptedModelProvider(default_text=MODEL_ANSWER)
    app = create_app(Settings(db_path=tmp_path / "library.db"), chargeback_model=model)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, model


def intake_payload(template_id="CB-CASE-041", **data_changes):
    return {
        "command_id": str(uuid4()),
        "action": "INTAKE",
        "confirmed": True,
        "data": {
            "case_template_id": template_id,
            "event_id": str(uuid4()),
            "upstream_case_id": str(uuid4()),
            "merchant_id": MERCHANT,
            "transaction_id": "sandbox-library-transaction",
            "scheme": "VISA",
            "channel": "MOCK",
            "reason_code": "13.1",
            "amount_minor": 12800,
            "currency": "USD",
            "received_at": datetime.now(UTC).isoformat(),
            **data_changes,
        },
    }


def post(client, payload, role="OPERATOR"):
    return client.post("/api/v2/commands", headers=headers(role), json=payload)


def execute(client, case, action, data, role="OPERATOR"):
    return post(
        client,
        {
            "command_id": str(uuid4()),
            "action": action,
            "case_id": case["id"],
            "expected_revision": case["revision"],
            "confirmed": True,
            "data": data,
        },
        role,
    )


def all_cases(client):
    result = client.get("/api/v2/cases", headers=headers())
    assert result.status_code == 200, result.text
    return result.json()["cases"]


def get_case(client, case):
    result = client.get(f"/api/v2/cases/{case['id']}", headers=headers())
    assert result.status_code == 200, result.text
    return result.json()


def require_success(response):
    assert response.status_code == 200, response.text
    return response.json()["case"]


def confirmed_rule_data():
    now = datetime.now(UTC)
    return {
        "source_id": "sandbox-risk-confirmation-CB-CASE-041",
        "source_locator": "SRC-01 P40-41; explicit sandbox workflow confirmation",
        "rule_version": "human-reviewed-rehearsal-v1",
        "allowed_actions": ["ACCEPT", "CONTEST"],
        "required_evidence": ["fulfillment.tracking", "fulfillment.proof_of_delivery"],
        "merchant_deadline": (now + timedelta(days=2)).isoformat(),
        "internal_deadline": (now + timedelta(days=3)).isoformat(),
        "external_deadline": (now + timedelta(days=4)).isoformat(),
        "reason": "人工核对来源与演练范围，明确材料清单、可用权利及本次演练期限。",
    }


def assert_unconfirmed_rehearsal(case, template_id):
    assert case["library_reference"]["template_id"] == template_id
    assert case["source_type"] == "SYNTHETIC_DEMO"
    assert case["production_eligible"] is False
    assert case["channel"] == "MOCK"
    assert case["work_status"] == "RECEIVED"
    assert case["merchant_decision"] == "NONE"
    assert case["business_outcome"] == "UNKNOWN"
    assert case["finality"] == "NOT_FINAL"
    assert case["evidence"] == case["submissions"] == case["financial_events"] == []
    rule = case["rule_snapshot"]
    assert rule["conflict_status"] == "NEEDS_CONFIRMATION"
    assert rule["source_id"] == "CASE-LIBRARY:" + template_id
    assert rule["source_type"] == "CURATED_CASE_LIBRARY"
    assert rule["production_eligible"] is False
    assert rule["allowed_actions"] == rule["required_evidence"] == []
    for deadline in (case["deadlines"], rule["deadlines"]):
        assert deadline["status"] == "NEEDS_CONFIRMATION"
        assert all(deadline[key] is None for key in ("merchant", "internal", "external"))


@pytest.mark.parametrize("role", ["OPERATOR", "MERCHANT"])
def test_library_get_reports_actual_uploaded_inventory_without_creating_cases(stack, role):
    client, model = stack
    response = client.get("/api/v2/case-library", headers=headers(role))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["manifest"]["reference_case_count"] == len(data["references"]) == 62
    assert data["manifest"]["template_count"] == len(data["templates"]) == 28
    assert data["manifest"]["rule_group_count"] == 35
    assert data["manifest"]["evidence_levels"] == {
        "SOURCE_EXPLICIT": 34,
        "RULE_DERIVED": 13,
        "SYNTHETIC_DEMO": 15,
    }
    assert data["manifest"]["source_manifest"]["source_commit"] == (
        "250e7d904fce451e6fe72b2192cba393b717c636"
    )
    assert all(r["production_eligible"] is False for r in data["references"])
    assert sum(r["sandbox_template_available"] for r in data["references"]) == 28
    assert all_cases(client) == []
    assert model.requests == []


def test_detail_distinguishes_original_example_from_sandbox_preview_and_unknown_id(stack):
    client, _ = stack
    original = client.get("/api/v2/case-library/CB-CASE-001", headers=headers())
    assert original.status_code == 200, original.text
    assert original.json()["reference"]["evidence_level"] == "SOURCE_EXPLICIT"
    assert original.json()["template"] is None
    response = client.get("/api/v2/case-library/CB-CASE-041", headers=headers())
    assert response.status_code == 200, response.text
    preview = response.json()["template"]
    assert preview["scope"] == "SANDBOX_TEMPLATE_PREVIEW"
    assert preview["template"]["transaction_facts"]["amount"] == "NOT_STATED"
    assert preview["template"]["transaction_facts"]["transaction_id"] == "NOT_STATED"
    assert preview["requires_confirmation"] is True
    missing = client.get("/api/v2/case-library/CB-CASE-035", headers=headers())
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize("role", ["MERCHANT", "AGENT", "ADMIN", "RISK_OFFICER", "SUPERVISOR"])
def test_template_selection_does_not_grant_intake_permission(stack, role):
    client, model = stack
    response = post(client, intake_payload(), role)
    assert response.status_code == 403, response.text
    assert all_cases(client) == []
    assert model.requests == []


def test_intake_requires_human_confirmation_even_for_synthetic_template(stack):
    client, _ = stack
    payload = intake_payload("CB-CASE-060")
    payload["confirmed"] = False
    response = post(client, payload)
    assert response.status_code == 409, response.text
    assert all_cases(client) == []


def test_all_34_source_examples_are_reference_only_and_cannot_create_live_cases(stack):
    client, _ = stack
    source_examples = _LIBRARY.list_references(evidence_level="SOURCE_EXPLICIT")
    assert len(source_examples) == 34
    for reference in source_examples:
        response = post(client, intake_payload(reference["template_id"]))
        assert response.status_code == 404, (reference["template_id"], response.text)
    assert all_cases(client) == []


@pytest.mark.parametrize("reference", _NETWORK_TEMPLATES, ids=lambda r: r["template_id"])
def test_26_network_templates_accept_matching_scheme_reason_only_as_unconfirmed_rehearsal(
    stack, reference
):
    client, model = stack
    assert len(_NETWORK_TEMPLATES) == 26
    payload = intake_payload(
        reference["template_id"],
        scheme=reference["scheme"],
        reason_code=reference["reason_codes"][0],
    )
    case = require_success(post(client, payload))
    assert_unconfirmed_rehearsal(case, reference["template_id"])
    assert case["scheme"] == reference["scheme"]
    assert case["reason_code"] in reference["reason_codes"]
    assert case["library_reference"]["sandbox_inputs"] == {
        "transaction_id": payload["data"]["transaction_id"],
        "amount_minor": 12800,
        "currency": "USD",
        "received_at": payload["data"]["received_at"],
        "origin": "HUMAN_CONFIRMED_REHEARSAL_INPUT",
    }
    assert len(all_cases(client)) == 1
    assert model.requests == []


@pytest.mark.parametrize(
    "data_changes",
    [
        {"scheme": "MASTERCARD"},
        {"reason_code": "10.4"},
        {"reason_code": "13.10"},
        {"channel": "LIVE"},
        {"channel": "CURATED_REFERENCE"},
        {"case_template_id": "CB-CASE-missing"},
    ],
)
def test_wrong_template_scope_is_rejected_without_case_or_agent_writes(stack, data_changes):
    client, model = stack
    payload = intake_payload()
    payload["data"].update(data_changes)
    response = post(client, payload)
    expected = 404 if "case_template_id" in data_changes else 422
    assert response.status_code == expected, response.text
    assert all_cases(client) == []
    assert model.requests == []


@pytest.mark.parametrize(
    "template_id,scheme,reason",
    [
        ("CB-CASE-052", "AMEX", "C08"),
        ("CB-CASE-069", "N/A（产品安全）", "N/A"),
    ],
)
def test_other_scheme_and_product_security_templates_remain_preview_only(
    stack, template_id, scheme, reason
):
    client, _ = stack
    preview = client.get(f"/api/v2/case-library/{template_id}", headers=headers())
    assert preview.status_code == 200
    assert preview.json()["template"] is not None
    response = post(client, intake_payload(template_id, scheme=scheme, reason_code=reason))
    assert response.status_code == 422, response.text
    assert all_cases(client) == []


@pytest.mark.parametrize("missing_field", ["amount_minor", "currency", "transaction_id"])
def test_unknown_template_facts_are_not_silently_filled_into_intake(stack, missing_field):
    client, _ = stack
    payload = intake_payload()
    del payload["data"][missing_field]
    response = post(client, payload)
    assert response.status_code == 422, response.text
    assert all_cases(client) == []
    source = client.get("/api/v2/case-library/CB-CASE-041", headers=headers()).json()
    assert source["template"]["template"]["transaction_facts"]["amount"] == "NOT_STATED"


def test_case_library_snapshot_is_detached_from_provider_and_survives_provider_changes(
    stack, monkeypatch
):
    client, _ = stack
    library = client.app.state.dispute_case_library
    shared_preview = library.get_template("CB-CASE-041")
    monkeypatch.setattr(library, "get_template", lambda _identifier: shared_preview)
    case = require_success(post(client, intake_payload()))
    original = deepcopy(case["library_reference"])
    shared_preview["reference"]["title"] = "Provider changed after intake"
    shared_preview["reference"]["source_locators"].append("DIFFERENT-SOURCE-PAGE")
    shared_preview["reference"]["required_evidence"].clear()
    reread = get_case(client, case)
    assert reread["library_reference"] == original
    later = require_success(post(client, intake_payload()))
    assert later["library_reference"]["title"] == "Provider changed after intake"
    assert get_case(client, case)["library_reference"] == original


def test_same_command_replay_is_atomic_and_cannot_change_selected_template(stack):
    client, _ = stack
    payload = intake_payload()
    first = post(client, payload)
    case = require_success(first)
    replay = post(client, payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["case"] == case
    assert replay.json()["receipt"] == first.json()["receipt"]
    changed = deepcopy(payload)
    changed["data"]["case_template_id"] = "CB-CASE-060"
    assert post(client, changed).status_code == 409
    assert all_cases(client) == [case]


def test_duplicate_source_event_cannot_rebind_to_another_template(stack):
    client, _ = stack
    payload = intake_payload()
    case = require_success(post(client, payload))
    changed = deepcopy(payload)
    changed["command_id"] = str(uuid4())
    changed["data"]["case_template_id"] = "CB-CASE-060"
    assert post(client, changed).status_code == 409
    assert all_cases(client) == [case]


@pytest.mark.parametrize(
    "initial_template,new_template",
    [
        ("CB-CASE-041", "CB-CASE-060"),
        ("CB-CASE-041", None),
        (None, "CB-CASE-041"),
    ],
)
def test_duplicate_upstream_case_cannot_change_or_add_or_remove_template(
    stack, initial_template, new_template
):
    client, _ = stack
    payload = intake_payload(initial_template)
    case = require_success(post(client, payload))
    changed = deepcopy(payload)
    changed["command_id"] = str(uuid4())
    changed["data"]["event_id"] = str(uuid4())
    changed["data"]["case_template_id"] = new_template
    response = post(client, changed)
    assert response.status_code == 409, response.text
    assert all_cases(client) == [case]


def test_duplicate_upstream_notice_retains_original_confirmed_inputs_and_reference(stack):
    client, _ = stack
    payload = intake_payload()
    case = require_success(post(client, payload))
    duplicate = deepcopy(payload)
    duplicate["command_id"] = str(uuid4())
    duplicate["data"]["event_id"] = str(uuid4())
    duplicate["data"]["received_at"] = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    reread = require_success(post(client, duplicate))
    assert reread["id"] == case["id"]
    assert reread["revision"] == case["revision"] + 1
    assert reread["library_reference"] == case["library_reference"]
    assert reread["upstream_events"][-1]["type"] == "DUPLICATE_NOTIFICATION"
    assert len(all_cases(client)) == 1


def test_reference_rehearsal_041_requires_risk_confirmation_before_merchant_handoff(stack):
    client, model = stack
    case = require_success(post(client, intake_payload()))
    assert case["amount_minor"] == 12800
    assert case["currency"] == "USD"
    original_reference = deepcopy(case["library_reference"])
    blocked = execute(client, case, "PUBLISH_TASK", {"message": "请处理此演练案件"})
    assert blocked.status_code == 409, blocked.text
    assert get_case(client, case) == case

    rule = confirmed_rule_data()
    denied = execute(client, case, "CONFIRM_RULE", rule, "OPERATOR")
    assert denied.status_code == 403
    case = require_success(execute(client, case, "CONFIRM_RULE", rule, "RISK_OFFICER"))
    assert case["rule_snapshot"]["required_evidence"] == sorted(rule["required_evidence"])
    assert case["deadlines"]["external"] == rule["external_deadline"]
    case = require_success(execute(client, case, "PUBLISH_TASK", {"message": "请确认接受或抗辩。"}))
    assert case["work_status"] == "MERCHANT_ACTION_REQUIRED"
    assert case["library_reference"] == original_reference
    merchant = client.get(f"/api/v2/cases/{case['id']}", headers=headers("MERCHANT"))
    assert merchant.status_code == 200, merchant.text
    assert merchant.json()["tasks"]
    assert merchant.json()["rule_snapshot"]["source_id"] == rule["source_id"]
    other = client.get(
        f"/api/v2/cases/{case['id']}", headers=headers("MERCHANT", "another-merchant")
    )
    assert other.status_code == 404

    activity = client.get(f"/api/v2/cases/{case['id']}/agent", headers=headers()).json()
    knowledge = activity["run"]["knowledge_retrieval"]
    assert knowledge["status"] == "COMPLETED"
    assert knowledge["manifest"]["reference_case_count"] == 62
    assert knowledge["references"]
    assert all(r["scope"] == "REFERENCE_KNOWLEDGE" for r in knowledge["references"])
    assert model.requests == []

    answer = client.post(
        f"/api/v2/cases/{case['id']}/agent/messages",
        headers=headers(),
        json={
            "message": "参考指南中的相似案例，本案为什么需要签收证明？",
            "expected_revision": case["revision"],
        },
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["source"] == "MODEL"
    assert len(model.requests) == 1
    assert answer.json()["knowledge_retrieval"]["scope"] == "REFERENCE_KNOWLEDGE"
    after_question = get_case(client, case)
    assert after_question == case
    assert after_question["rule_snapshot"]["source_id"] == rule["source_id"]


@pytest.mark.parametrize("advance_inline", [False, True], ids=["NEXT_STAGE", "OUTCOME_NEXT_STAGE"])
def test_next_stage_never_promotes_library_template_to_mock_fixture_rule_or_deadlines(
    stack, advance_inline
):
    client, model = stack
    case = require_success(post(client, intake_payload()))
    case = require_success(
        execute(client, case, "CONFIRM_RULE", confirmed_rule_data(), "RISK_OFFICER")
    )
    case = require_success(
        execute(client, case, "PUBLISH_TASK", {"message": "请确认本案演练立场。"})
    )
    case = complete_contest(client.app.state.disputes, case)
    previous_rule = deepcopy(case["rule_snapshot"])
    previous_deadlines = deepcopy(case["deadlines"])
    previous_submissions = deepcopy(case["submissions"])
    original_reference = deepcopy(case["library_reference"])
    data = {
        "event_id": str(uuid4()),
        "outcome": "LOST",
        "final": False,
        "source": "MOCK_UPSTREAM",
        "reason": "上游非终局结果，允许继续下一阶段演练。",
    }
    if advance_inline:
        data["next_stage"] = "REPRESENTMENT"
    case = require_success(execute(client, case, "RECORD_OUTCOME", data))
    if not advance_inline:
        case = require_success(
            execute(
                client,
                case,
                "NEXT_STAGE",
                {"event_id": str(uuid4()), "stage": "REPRESENTMENT", "source": "MOCK_UPSTREAM"},
            )
        )
    assert case["stage"] == "REPRESENTMENT"
    assert case["stage_number"] == 2
    assert case["library_reference"] == original_reference
    assert case["work_status"] == "RECEIVED"
    assert case["rule_snapshot"]["conflict_status"] == "NEEDS_CONFIRMATION"
    assert case["rule_snapshot"]["production_eligible"] is False
    assert case["rule_snapshot"]["allowed_actions"] == []
    assert case["deadlines"]["status"] == "NEEDS_CONFIRMATION"
    assert all(case["deadlines"][key] is None for key in ("merchant", "internal", "external"))
    assert case["stage_history"][0]["rule_snapshot"] == previous_rule
    assert case["stage_history"][0]["deadlines"] == previous_deadlines
    assert case["stage_history"][0]["submissions"] == previous_submissions
    assert (
        execute(client, case, "PUBLISH_TASK", {"message": "尝试跳过下一阶段人审。"}).status_code
        == 409
    )
    assert get_case(client, case) == case
    assert model.requests == []
