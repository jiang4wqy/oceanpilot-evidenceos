"""Public workspace boundaries, durable recovery, and disabled submission gates."""

from dataclasses import dataclass
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.chargeback_appeal import AppealAgent
from oceanpilot.application.chargeback_packager import PackagerAgent
from oceanpilot.config import Settings
from oceanpilot.domain.chargeback import ChargebackEvidenceCode as Code
from oceanpilot.main import create_app

BUSINESS = {"X-Demo-Role": "BUSINESS", "X-Demo-Actor": "synthetic-reviewer"}
MERCHANT = {"X-Demo-Role": "MERCHANT", "X-Demo-Actor": "synthetic-merchant"}
COMMANDS = "/api/v1/workspace/commands"


@dataclass
class ApiHarness:
    app: object
    client: TestClient
    model: ScriptedModelProvider
    settings: Settings


@pytest.fixture
def api(tmp_path):
    settings = Settings(db_path=tmp_path / "api.db")
    model = ScriptedModelProvider(default_text="not-json")
    app = create_app(settings, chargeback_model=model)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield ApiHarness(app, client, model, settings)


def cmd(action, data, case=None, **extra):
    return {
        "command_id": str(uuid4()),
        "action": action,
        "data": data,
        "confirmed": True,
        "case_id": case["case_id"] if case else None,
        "expected_revision": case["revision"] if case else None,
    } | extra


def execute(api, action, data, case=None, headers=MERCHANT):
    response = api.client.post(COMMANDS, headers=headers, json=cmd(action, data, case))
    assert response.status_code == 200, response.text
    return response.json()["case"]


def sample(api, name="A"):
    return execute(api, "COPY_SAMPLE", {"sample": name})


def ready(api):
    return execute(
        api,
        "REGISTER_MATERIAL",
        {
            "evidence_code": Code.THREEDS_AUTHENTICATION.value,
            "file_name": "synthetic-3ds.txt",
            "source": "SYNTHETIC_TEMPLATE",
        },
        sample(api),
    )


def review_data(case, decision="APPROVED"):
    return {
        "decision": decision,
        "summary": "仅复核当前版本材料登记清单，正文仍未核验。",
        "scope": ["材料登记清单", "内部处理门槛"],
        "expected_rule_fingerprint": case["rule_fingerprint"],
    }


def current(api, case):
    return api.client.get(f"/api/v1/workspace/cases/{case['case_id']}", headers=MERCHANT).json()


def test_merchant_cannot_confirm_any_business_review_decision(api):
    case = ready(api)
    before = current(api, case)
    for decision in ("APPROVED", "NEEDS_MORE_INFO", "REJECTED"):
        payload = cmd("REVIEW", review_data(case, decision), case)
        response = api.client.post(COMMANDS, json=payload, headers=MERCHANT)
        assert response.status_code == 403
        receipt = api.client.get(f"{COMMANDS}/{payload['command_id']}", headers=MERCHANT)
        assert receipt.json() == {"status": "UNKNOWN"}
    assert current(api, case) == before


@pytest.mark.parametrize("fingerprint", [None, 123, "0" * 64])
def test_business_review_rejects_missing_invalid_or_stale_rule_fingerprint(api, fingerprint):
    case = ready(api)
    before = current(api, case)
    data = review_data(case)
    if fingerprint is None:
        data.pop("expected_rule_fingerprint")
    else:
        data["expected_rule_fingerprint"] = fingerprint
    payload = cmd("REVIEW", data, case)
    response = api.client.post(COMMANDS, headers=BUSINESS, json=payload)
    assert response.status_code == (409 if isinstance(fingerprint, str) else 422)
    assert current(api, case) == before
    assert api.client.get(f"{COMMANDS}/{payload['command_id']}", headers=BUSINESS).json() == {
        "status": "UNKNOWN"
    }


def test_merchant_cannot_resolve_an_actual_open_concern(api):
    case = execute(api, "SET_NETWORK", {"card_network": "AMEX"}, ready(api))
    payload = cmd(
        "RESOLVE_CONCERN",
        {
            "concern_id": case["concerns"][-1]["concern_id"],
            "resolution": "ACCEPT_PROPOSED",
            "summary": "合成记录人工更正卡组织。",
        },
        case,
    )
    response = api.client.post(COMMANDS, json=payload, headers=MERCHANT)
    assert response.status_code == 403
    assert current(api, case)["card_network"] == "VISA"
    assert current(api, case)["concerns"][-1]["status"] == "OPEN"
    assert current(api, case)["revision"] == case["revision"]


@pytest.mark.parametrize("state", ["unreviewed", "approved", "blocked"])
def test_only_business_generates_summary_but_merchant_can_read_and_download_it(api, state):
    if state == "blocked":
        case = sample(api, "B")
    else:
        case = ready(api)
        if state == "approved":
            case = execute(api, "REVIEW", review_data(case), case, headers=BUSINESS)
    endpoint = f"/api/v1/workspace/cases/{case['case_id']}/summaries"
    before_calls = len(api.model.requests)
    denied = api.client.post(
        endpoint, json={"expected_revision": case["revision"]}, headers=MERCHANT
    )
    assert denied.status_code == 403
    assert current(api, case)["summaries"] == []
    generated = api.client.post(
        endpoint, json={"expected_revision": case["revision"]}, headers=BUSINESS
    )
    assert generated.status_code == 200
    metadata = generated.json()
    document = api.client.get(metadata["html_url"], headers=MERCHANT)
    snapshot = api.client.get(metadata["json_url"], headers=MERCHANT)
    assert document.status_code == snapshot.status_code == 200
    assert document.headers["content-type"].startswith("text/html")
    assert snapshot.headers["content-type"].startswith("application/json")
    assert document.headers["content-disposition"].startswith("attachment;")
    assert document.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in document.headers["content-security-policy"]
    assert snapshot.json()["case"]["review_status"] == case["review_status"]
    assert snapshot.json()["case"]["revision"] == snapshot.json()["revision"] == case["revision"]
    assert snapshot.json()["synthetic"] is True
    assert len(api.model.requests) == before_calls
    assert api.client.get("/api/v1/workspace/cases", headers=MERCHANT).status_code == 200


@pytest.mark.parametrize("confirmed", [False, "true", 1, None])
def test_missing_or_nonexplicit_confirmation_cannot_create_a_case(api, confirmed):
    payload = cmd("COPY_SAMPLE", {"sample": "A"}, confirmed=confirmed)
    response = api.client.post(COMMANDS, json=payload, headers=MERCHANT)
    assert response.status_code == 422
    assert api.app.state.workspace.store.case_ids() == ()
    assert api.client.get(f"{COMMANDS}/{payload['command_id']}", headers=MERCHANT).json() == {
        "status": "UNKNOWN"
    }
    assert api.model.requests == []


@pytest.mark.parametrize("revision", [None, "7", True, -1])
def test_missing_or_invalid_version_cannot_register_material(api, revision):
    case = sample(api)
    payload = cmd(
        "REGISTER_MATERIAL",
        {
            "evidence_code": Code.THREEDS_AUTHENTICATION.value,
            "file_name": "synthetic-3ds.txt",
            "source": "SYNTHETIC_TEMPLATE",
        },
        case,
        expected_revision=revision,
    )
    before = current(api, case)
    response = api.client.post(COMMANDS, headers=MERCHANT, json=payload)
    assert response.status_code == 422
    assert current(api, case) == before


@pytest.mark.parametrize(
    "bad_data",
    [
        {
            "evidence_code": "UNKNOWN_CODE",
            "file_name": "synthetic.txt",
            "source": "SYNTHETIC_TEMPLATE",
        },
        {
            "evidence_code": Code.THREEDS_AUTHENTICATION.value,
            "file_name": "",
            "source": "SYNTHETIC_TEMPLATE",
        },
        {
            "evidence_code": Code.THREEDS_AUTHENTICATION.value,
            "file_name": "synthetic.txt",
            "source": "VERIFIED_REAL_FILE",
        },
        {
            "evidence_code": Code.THREEDS_AUTHENTICATION.value,
            "file_name": "synthetic.txt",
            "source": "SYNTHETIC_TEMPLATE",
            "content_verification": "VERIFIED",
        },
    ],
)
def test_invalid_material_contract_cannot_upgrade_metadata_or_write_case(api, bad_data):
    case = sample(api)
    before = current(api, case)
    response = api.client.post(
        COMMANDS, headers=MERCHANT, json=cmd("REGISTER_MATERIAL", bad_data, case)
    )
    assert response.status_code == 422
    assert current(api, case) == before


def test_stale_command_returns_409_without_registering_a_second_material(api):
    case = sample(api)
    mutation = cmd(
        "REGISTER_MATERIAL",
        {
            "evidence_code": Code.THREEDS_AUTHENTICATION.value,
            "file_name": "synthetic.txt",
            "source": "SYNTHETIC_TEMPLATE",
        },
        case,
    )
    first = api.client.post(COMMANDS, headers=MERCHANT, json=mutation)
    assert first.status_code == 200
    before = current(api, case)
    stale = api.client.post(
        COMMANDS, headers=MERCHANT, json=mutation | {"command_id": str(uuid4())}
    )
    assert stale.status_code == 409
    assert current(api, case) == before


def test_same_command_replays_and_changed_payload_is_rejected(api):
    payload = cmd("COPY_SAMPLE", {"sample": "A"})
    first = api.client.post(COMMANDS, headers=MERCHANT, json=payload)
    again = api.client.post(COMMANDS, headers=MERCHANT, json=payload)
    assert first.status_code == again.status_code == 200
    assert first.json()["receipt"] == again.json()["receipt"]
    assert again.json()["status"] == "REPLAYED"
    changed = api.client.post(COMMANDS, headers=MERCHANT, json=payload | {"data": {"sample": "C"}})
    assert changed.status_code == 409
    assert len(api.app.state.workspace.store.case_ids()) == 1


def test_response_timeout_after_commit_is_recovered_via_receipt_without_recreating_case(
    api, monkeypatch
):
    service = api.app.state.workspace
    original = service.execute
    payload = cmd("COPY_SAMPLE", {"sample": "A"})

    def lose_response(*args, **kwargs):
        original(*args, **kwargs)
        raise TimeoutError("synthetic response lost after commit")

    monkeypatch.setattr(service, "execute", lose_response)
    failed = api.client.post(COMMANDS, headers=MERCHANT, json=payload)
    assert failed.status_code == 500
    recovered = api.client.get(f"{COMMANDS}/{payload['command_id']}", headers=MERCHANT)
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "APPLIED"
    assert recovered.json()["case"]["case_id"] == recovered.json()["receipt"]["case_id"]
    monkeypatch.setattr(service, "execute", original)
    replayed = api.client.post(COMMANDS, headers=MERCHANT, json=payload)
    assert replayed.json()["receipt"] == recovered.json()["receipt"]
    assert replayed.json()["status"] == "REPLAYED"
    assert len(service.store.case_ids()) == 1


def test_receipt_cannot_be_claimed_by_another_demo_identity(api):
    payload = cmd("COPY_SAMPLE", {"sample": "A"})
    assert api.client.post(COMMANDS, headers=MERCHANT, json=payload).status_code == 200
    endpoint = f"{COMMANDS}/{payload['command_id']}"
    assert api.client.get(endpoint, headers=BUSINESS).status_code == 403
    assert (
        api.client.get(
            endpoint, headers=MERCHANT | {"X-Demo-Actor": "another-merchant"}
        ).status_code
        == 403
    )
    assert api.client.get(endpoint, headers=MERCHANT).status_code == 200


def test_invalid_role_and_sensitive_input_are_rejected_without_case_creation(api):
    payload = cmd("COPY_SAMPLE", {"sample": "A"})
    assert (
        api.client.post(COMMANDS, headers={"X-Demo-Role": "ADMIN"}, json=payload).status_code == 403
    )
    sensitive = "4111 1111 1111 1111"
    payload = cmd(
        "CREATE_CASE",
        {
            "description": "Synthetic " + sensitive,
            "formal_dispute": True,
            "card_network": "VISA",
        },
    )
    response = api.client.post(COMMANDS, headers=MERCHANT, json=payload)
    assert response.status_code == 422
    assert sensitive not in response.text
    assert api.app.state.workspace.store.case_ids() == ()
    assert api.model.requests == []


def test_ordinary_payment_failure_cannot_be_created_without_formal_dispute_confirmation(api):
    payload = cmd(
        "CREATE_CASE",
        {
            "description": "Synthetic 支付失败，还未进入正式争议流程。",
            "formal_dispute": False,
            "card_network": "VISA",
        },
    )
    response = api.client.post(COMMANDS, json=payload, headers=MERCHANT)
    assert response.status_code == 422
    assert api.app.state.workspace.store.case_ids() == ()
    assert api.model.requests == []


def test_summary_rejects_stale_revision_and_unrecognized_download_format(api):
    case = sample(api)
    endpoint = f"/api/v1/workspace/cases/{case['case_id']}/summaries"
    stale = api.client.post(
        endpoint, json={"expected_revision": case["revision"] - 1}, headers=BUSINESS
    )
    assert stale.status_code == 409
    assert current(api, case)["summaries"] == []
    generated = api.client.post(
        endpoint, json={"expected_revision": case["revision"]}, headers=BUSINESS
    ).json()
    invalid = api.client.get(
        f"/api/v1/workspace/summaries/{generated['summary_id']}?format=javascript", headers=MERCHANT
    )
    assert invalid.status_code == 422


def test_summary_download_escapes_html_and_survives_application_restart(tmp_path):
    settings = Settings(db_path=tmp_path / "persistent-api.db")
    app = create_app(settings, chargeback_model=ScriptedModelProvider(default_text="not-json"))
    title = '<script>alert("synthetic")</script>'
    with TestClient(app, raise_server_exceptions=False) as client:
        payload = cmd(
            "CREATE_CASE",
            {
                "title": title,
                "description": "Synthetic 正式商品未收到争议。 " + title,
                "formal_dispute": True,
                "card_network": "VISA",
            },
        )
        created = client.post(COMMANDS, headers=MERCHANT, json=payload)
        assert created.status_code == 200
        case = created.json()["case"]
        metadata = client.post(
            f"/api/v1/workspace/cases/{case['case_id']}/summaries",
            headers=BUSINESS,
            json={"expected_revision": case["revision"]},
        ).json()
        before = client.get(metadata["html_url"], headers=MERCHANT)
        assert before.status_code == 200
        assert "<script>" not in before.text
        assert "&lt;script&gt;" in before.text
    restarted = create_app(
        settings, chargeback_model=ScriptedModelProvider(default_text="not-json")
    )
    with TestClient(restarted, raise_server_exceptions=False) as client:
        restored = client.get(metadata["html_url"], headers=MERCHANT)
        assert restored.status_code == 200
        assert restored.text == before.text
        saved = client.get(metadata["json_url"], headers=MERCHANT).json()
        assert saved["case"]["title"] == title
        recovered = client.get(f"{COMMANDS}/{payload['command_id']}", headers=MERCHANT)
        assert recovered.status_code == 200
        assert recovered.json()["receipt"] == created.json()["receipt"]


@pytest.mark.parametrize("enabled,expected", [(False, 503), (True, 501)])
@pytest.mark.parametrize("approved", [False, True])
def test_direct_appeal_never_bypasses_backend_send_gate_or_calls_model_or_upstream(
    tmp_path, enabled, expected, approved
):
    model = ScriptedModelProvider(default_text="not-json")
    app = create_app(
        Settings(db_path=tmp_path / "api.db", mock_send_enabled=enabled), chargeback_model=model
    )
    blocked_appeal = Mock(spec=AppealAgent)
    blocked_packager = Mock(spec=PackagerAgent)
    upstream = app.state.chargeback_appeal._upstream
    app.state.chargeback_appeal = blocked_appeal
    app.state.chargeback_packager = blocked_packager
    with TestClient(app, raise_server_exceptions=False) as client:
        case = client.post(
            COMMANDS, headers=MERCHANT, json=cmd("COPY_SAMPLE", {"sample": "A"})
        ).json()["case"]
        response = client.post(
            f"/api/v1/chargeback/cases/{case['case_id']}/appeal",
            headers=BUSINESS,
            json={
                "human_approved": approved,
                "actor_id": "synthetic-reviewer",
                "card_network": "VISA",
            },
        )
        assert response.status_code == expected
        assert model.requests == []
        assert upstream.submissions == []
        blocked_packager.build.assert_not_called()
        blocked_packager.preview.assert_not_called()
        blocked_appeal.draft.assert_not_called()
        blocked_appeal.submit.assert_not_called()


def test_summary_english_download_preserves_frozen_case_and_original_notes(api):
    case = ready(api)
    case = execute(api, "REVIEW", review_data(case), case, BUSINESS)
    response = api.client.post(
        f"/api/v1/workspace/cases/{case['case_id']}/summaries",
        headers=BUSINESS,
        json={"expected_revision": case["revision"]},
    )
    assert response.status_code == 200
    summary = response.json()
    before = len(api.model.requests)
    english = api.client.get(summary["html_url"] + "&locale=en", headers=BUSINESS)
    chinese = api.client.get(summary["html_url"] + "&locale=zh", headers=BUSINESS)
    assert english.status_code == chinese.status_code == 200
    assert '<html lang="en">' in english.text
    assert '<html lang="zh-CN">' in chinese.text
    assert "Case review summary (synthetic example)" in english.text
    assert "data-no-i18n" in english.text
    assert review_data(case)["summary"] in english.text
    assert case["case_id"] in english.text
    assert len(api.model.requests) == before
    first = api.client.get(summary["json_url"] + "&locale=en", headers=BUSINESS).json()
    second = api.client.get(summary["json_url"] + "&locale=zh", headers=BUSINESS).json()
    assert first == second
    assert first["revision"] == case["revision"]


@pytest.mark.parametrize("scenario", ["A", "B", "C"])
def test_every_synthetic_summary_has_complete_english_presentation(api, scenario):
    import re

    from oceanpilot.web.summary_i18n import _SummaryTranslator

    case = sample(api, scenario)
    result = api.client.post(
        f"/api/v1/workspace/cases/{case['case_id']}/summaries",
        headers=BUSINESS,
        json={"expected_revision": case["revision"]},
    ).json()
    english = api.client.get(result["html_url"] + "&locale=en", headers=BUSINESS).text

    class Audit(_SummaryTranslator):
        def handle_data(self, text):
            if not (self.stack and self.stack[-1][1]):
                assert not re.search(r"[\u3400-\u9fff]", text), text

    Audit().feed(english)
