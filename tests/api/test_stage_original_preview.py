"""Authenticated, saved-byte preview and safe history projection."""

import base64
from copy import deepcopy
from uuid import uuid4

from oceanpilot.application.dispute_views import merchant_case_view
from tests.api.test_dispute_collaboration_api import api as api
from tests.application.test_member_b_documents import document_bytes


def test_preview_requires_case_access_and_valid_page(api):
    client, app, headers, case = api
    app.state.dispute_collaboration.agent.model = None
    for action, data, who in [
        ("PUBLISH_TASK", {}, "operator"),
        ("MERCHANT_DECISION", {"decision": "CONTEST", "reason": "synthetic"}, "merchant"),
    ]:
        r = client.post(
            "/api/v2/commands",
            headers=headers[who],
            json={
                "command_id": str(uuid4()),
                "case_id": case["id"],
                "expected_revision": case["revision"],
                "confirmed": True,
                "action": action,
                "data": data,
            },
        )
        assert r.status_code == 200, r.text
        case = r.json()["case"]
    root = f"/api/v2/cases/{case['id']}/collaboration/files"
    r = client.post(
        root,
        headers=headers["merchant"],
        json={
            "command_id": str(uuid4()),
            "expected_revision": case["revision"],
            "code": "fulfillment.proof_of_delivery",
            "title": "synthetic",
            "filename": "proof.pdf",
            "mime_type": "application/pdf",
            "content_base64": base64.b64encode(document_bytes("pdf")).decode(),
        },
    )
    assert r.status_code == 200, r.text
    path = root + "/" + r.json()["file"]["id"] + "/pages/"
    preview = client.get(path + "1", headers=headers["operator"])
    assert preview.status_code == 200 and preview.content.startswith(b"\xff\xd8")
    assert preview.headers["Cache-Control"] == "private, no-store"
    assert client.get(path + "1", headers=headers["outsider"]).status_code == 404
    assert client.get(path + "2", headers=headers["merchant"]).status_code == 404
    assert client.get(path + "11", headers=headers["merchant"]).status_code == 422
    client.cookies.clear()
    assert client.get(path + "1").status_code == 401


def test_merchant_history_does_not_expose_staff_notes_or_internal_versions(api):
    *_, case = api
    case = deepcopy(case)
    case["evidence"] = [
        {
            "id": "one",
            "history": [
                {
                    "revision": 1,
                    "object_id": "shared-original",
                    "notes": "staff secret",
                    "registered_by": "staff-id",
                },
                {"revision": 2, "object_id": "internal-original", "visibility": "OP_INTERNAL"},
            ],
        }
    ]
    history = merchant_case_view(case)["evidence"][0]["history"]
    assert history == [{"revision": 1, "object_id": "shared-original"}]
