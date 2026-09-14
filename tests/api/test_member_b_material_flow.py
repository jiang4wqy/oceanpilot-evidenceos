"""Continuous correction through authorized HTTP, not pre-approved fixture storage."""

import base64
from uuid import uuid4

import pytest

from tests.api.test_dispute_collaboration_api import api as api


@pytest.mark.parametrize("variant", ["missing_field", "wrong_transaction"])
def test_invalid_material_replaced_then_submitted_to_current_reviewer(api, variant):
    client, app, headers, case = api

    def command(action, data, role):
        return client.post(
            "/api/v2/commands",
            headers=headers[role],
            json={
                "command_id": str(uuid4()),
                "case_id": case["id"],
                "expected_revision": case["revision"],
                "action": action,
                "confirmed": True,
                "data": data,
            },
        )

    for action, data, role in [
        ("PUBLISH_TASK", {}, "operator"),
        (
            "MERCHANT_DECISION",
            {"decision": "CONTEST", "reason": "合成交易事实支持抗辩"},
            "merchant",
        ),
    ]:
        response = command(action, data, role)
        assert response.status_code == 200, response.text
        case = response.json()["case"]
    root = f"/api/v2/cases/{case['id']}/collaboration"

    def upload(code, variant, evidence_id=None):
        sample = client.get(
            root + f"/samples/{code}?variant={variant}", headers=headers["merchant"]
        )
        assert sample.status_code == 200, sample.text
        payload = {
            "command_id": str(uuid4()),
            "expected_revision": case["revision"],
            "code": code,
            "title": "合成材料",
            "filename": variant + ".json",
            "mime_type": "application/json",
            "content_base64": base64.b64encode(sample.content).decode(),
        }
        if evidence_id:
            payload["evidence_id"] = evidence_id
        response = client.post(root + "/files", headers=headers["merchant"], json=payload)
        assert response.status_code == 200, response.text
        return response.json()["case"]

    code = "fulfillment.proof_of_delivery"
    case = upload(code, variant)
    old = next(e for e in case["evidence"] if e["code"] == code)
    assert old["content_check"]["status"] == "INSUFFICIENT"
    blocked = command("SUBMIT_EVIDENCE", {}, "merchant")
    assert blocked.status_code == 409
    case = upload(code, "sufficient", old["id"])
    current = next(e for e in case["evidence"] if e["id"] == old["id"])
    assert current["revision"] == old["revision"] + 1
    assert current["content_check"]["status"] == "SUPPORTED"
    plan = client.get(f"/api/v2/cases/{case['id']}/plan", headers=headers["merchant"]).json()
    for item in plan["checklist"]:
        if not item["present"]:
            case = upload(item["code"], "sufficient")
    response = command("SUBMIT_EVIDENCE", {}, "merchant")
    assert response.status_code == 200, response.text
    case = response.json()["case"]
    assert case["work_status"] == "OP_REVIEW"
    assert case["current_task"]["owner"]["role"] == "OPERATOR"
    internal = next(row for row in case["deadline_summary"] if row["kind"] == "internal")
    assert case["current_task"]["deadline"] == internal["at"]
    assert case["current_task"]["deadline_kind"] == "internal"
    assert case["primary_action"] is None
    assert case["business_outcome"] == "UNKNOWN"
    assert case["finality"] == "NOT_FINAL"


def test_http_rule_confirmation_accepts_explicit_critical_subset_and_replays(api):
    from tests.v21_support import normalized_intake, session_headers

    client, _, _, case = api
    risk = session_headers(client, "OPERATOR", "merchant-a")
    # The four-role model assigns rule confirmation to the scoped Operator.
    response = normalized_intake(
        client,
        {
            "data": {
                "merchant_id": "merchant-a",
                "transaction_id": "b-critical-subset",
                "scheme": "VISA",
                "channel": "MOCK",
                "reason_code": "13.1",
                "amount_minor": 12500,
                "currency": "USD",
                "event_id": str(uuid4()),
            }
        },
    )
    assert response.status_code == 200, response.text
    case = response.json()["case"]
    required = case["rule_snapshot"]["required_evidence"]
    assert len(required) > 1
    data = {
        "allowed_actions": ["ACCEPT", "CONTEST"],
        "source_id": "member-b-synthetic-policy",
        "source_locator": "explicit rehearsal rule",
        "rule_version": "member-b-test",
        "required_evidence": required,
        "critical_evidence": [required[0]],
        "reason": "明确区分普通必需项和关键项",
        **{
            f"{kind}_deadline": case["deadlines"][kind]
            for kind in ("merchant", "internal", "external")
        },
    }
    command = {
        "command_id": str(uuid4()),
        "action": "CONFIRM_RULE",
        "case_id": case["id"],
        "expected_revision": case["revision"],
        "confirmed": True,
        "data": data,
    }
    response = client.post("/api/v2/commands", headers=risk, json=command)
    assert response.status_code == 200, response.text
    current = response.json()["case"]
    assert current["rule_snapshot"]["critical_evidence"] == [required[0]]
    replay = client.post("/api/v2/commands", headers=risk, json=command)
    assert replay.status_code == 200
    assert replay.json()["case"]["revision"] == current["revision"]
    plan = client.get(f"/api/v2/cases/{case['id']}/plan", headers=risk).json()
    assert plan["missing_critical"] == [required[0]]
    assert set(plan["missing_required"]) == set(required)
