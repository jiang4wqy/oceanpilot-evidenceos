import base64
from uuid import uuid4

import pytest

from oceanpilot.application.evidence_documents import FILE_TYPES
from tests.api.test_dispute_collaboration_api import api as api
from tests.application.test_member_b_documents import document_bytes


@pytest.mark.parametrize("kind", ["png", "pdf", "docx", "doc"])
def test_real_document_http_upload_download_and_independent_review(api, kind):
    client, app, headers, case = api
    app.state.dispute_collaboration.agent.model = None

    def command(action, data, who):
        return client.post(
            "/api/v2/commands",
            headers=headers[who],
            json={
                "command_id": str(uuid4()),
                "action": action,
                "case_id": case["id"],
                "expected_revision": case["revision"],
                "confirmed": True,
                "data": data,
            },
        )

    for action, data, who in [
        ("PUBLISH_TASK", {}, "operator"),
        (
            "MERCHANT_DECISION",
            {"decision": "CONTEST", "reason": "Synthetic document test"},
            "merchant",
        ),
    ]:
        response = command(action, data, who)
        assert response.status_code == 200, response.text
        case = response.json()["case"]
    original = document_bytes(kind)
    root = f"/api/v2/cases/{case['id']}/collaboration"
    response = client.post(
        root + "/files",
        headers=headers["merchant"],
        json={
            "command_id": str(uuid4()),
            "expected_revision": case["revision"],
            "code": "fulfillment.proof_of_delivery",
            "title": "Synthetic document",
            "filename": "test." + kind,
            "mime_type": FILE_TYPES["." + kind],
            "content_base64": base64.b64encode(original).decode(),
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    case = result["case"]
    obj = result["file"]
    assert obj["content_check"]["status"] == "NEEDS_MANUAL"
    download = client.get(root + "/files/" + obj["id"], headers=headers["merchant"])
    assert download.content == original
    assert download.headers["content-disposition"].startswith("attachment;")
    assert client.get(root + "/files/" + obj["id"], headers=headers["outsider"]).status_code == 404
    response = command("SUBMIT_EVIDENCE", {}, "merchant")
    assert response.status_code == 409
