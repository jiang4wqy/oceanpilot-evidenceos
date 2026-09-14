"""Document acceptance exercises real object storage and normal evidence commands."""

import base64
import io
import json
import zipfile
from hashlib import sha256
from uuid import uuid4

import pytest
from PIL import Image

from oceanpilot.application.evidence_documents import (
    MAX_BASE64_CHARS,
    MAX_FILE_BYTES,
    read_document,
)
from oceanpilot.application.model_provider import ModelResult
from oceanpilot.domain.dispute import DisputeError
from tests.application.test_dispute_collaboration import (
    MERCHANT,
    RISK,
    SUPERVISOR,
    collecting,
    command,
    file_payload,
    submitted_evidence,
)
from tests.application.test_dispute_collaboration import (
    stack as stack,
)


def document_bytes(kind):
    out = io.BytesIO()
    if kind in {"png", "pdf"}:
        image = Image.new("RGB", (500, 160), "white")
        image.save(out, format=kind.upper())
    elif kind == "docx":
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>synthetic document</w:t></w:r></w:p></w:body></w:document>",
            )
    else:
        out.write(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"synthetic legacy document placeholder")
    return out.getvalue()


def upload(collab, case, kind="png", *, content=None, **kwargs):
    from oceanpilot.application.evidence_documents import FILE_TYPES

    payload = file_payload(case)
    payload.update(
        filename="synthetic." + kind,
        mime_type=FILE_TYPES["." + kind],
        content_base64=base64.b64encode(content or document_bytes(kind)).decode(),
        **kwargs,
    )
    return collab.upload_file(case["id"], MERCHANT, **payload), payload


@pytest.mark.parametrize("kind", ["png", "pdf", "docx", "doc"])
def test_documents_save_original_without_claiming_recognition_or_approval(stack, kind):
    _, agent, collab, _, _, _ = stack
    agent.model = None
    case = collecting(stack)
    result, payload = upload(collab, case, kind)
    obj = result["file"]
    assert obj["content_check"]["status"] == "NEEDS_MANUAL"
    assert obj["content_check"]["recognition"]["status"] in {"NOT_CONFIGURED", "MANUAL_ONLY"}
    original = collab.download_file(case["id"], obj["id"], MERCHANT)
    assert original["content"] == base64.b64decode(payload["content_base64"])
    assert obj["sha256"] == sha256(original["content"]).hexdigest()
    assert not result["case"]["evidence"][0]["content_verified"]
    assert result["case"]["business_outcome"] == "UNKNOWN"


def test_twenty_mib_boundary_and_base64_cap_use_actual_decoded_size(stack):
    _, _, collab, _, _, _ = stack
    case = collecting(stack)
    payload = file_payload(case)
    raw = base64.b64decode(payload["content_base64"])
    raw += b" " * (MAX_FILE_BYTES - len(raw))
    payload["content_base64"] = base64.b64encode(raw).decode()
    assert len(payload["content_base64"]) == MAX_BASE64_CHARS
    result = collab.upload_file(case["id"], MERCHANT, **payload)
    assert result["file"]["size"] == MAX_FILE_BYTES
    assert result["file"]["content_check"]["status"] == "SUPPORTED"
    payload.update(command_id=str(uuid4()), content_base64=base64.b64encode(raw + b" ").decode())
    with pytest.raises(DisputeError, match="20 MiB"):
        collab.upload_file(case["id"], MERCHANT, **payload)


class VisionModel:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    def complete(self, task, messages, **kwargs):
        self.calls.append((task, messages))
        if self.fail:
            raise TimeoutError("private endpoint error")
        return ModelResult(
            text=json.dumps({"text": "[page:1]\nSynthetic receipt", "facts": {}}),
            model="test-vision",
        )


def test_vision_uses_image_blocks_and_lost_response_replay_does_not_recall_model(stack):
    _, agent, collab, _, _, _ = stack
    agent.model = VisionModel()
    case = collecting(stack)
    result, payload = upload(collab, case)
    assert result["file"]["content_check"]["recognition"]["status"] == "SUCCEEDED"
    assert result["file"]["content_check"]["status"] == "NEEDS_MANUAL"
    messages = agent.model.calls[0][1]
    assert messages[0].images[0].mime_type == "image/jpeg"
    assert base64.b64decode(messages[0].images[0].data_base64).startswith(b"\xff\xd8")
    assert case["transaction_id"] not in messages[0].content
    replay = collab.upload_file(case["id"], MERCHANT, **payload)
    assert replay["file"]["id"] == result["file"]["id"]
    assert replay["case"]["revision"] == result["case"]["revision"]
    assert len(agent.model.calls) == 1


def test_recognition_failure_preserves_original_and_explicit_replacement_retries(stack):
    _, agent, collab, _, _, _ = stack
    agent.model = VisionModel(fail=True)
    case = collecting(stack)
    first, _ = upload(collab, case)
    assert first["file"]["content_check"]["recognition"]["status"] == "FAILED"
    assert "private endpoint" not in json.dumps(first)
    agent.model.fail = False
    case = first["case"]
    second, _ = upload(collab, case, evidence_id=case["evidence"][0]["id"])
    evidence = second["case"]["evidence"][0]
    assert evidence["revision"] == 2
    assert evidence["history"][0]["object_id"] == first["file"]["id"]
    assert second["file"]["sha256"] == first["file"]["sha256"]
    assert second["file"]["content_check"]["recognition"]["status"] == "SUCCEEDED"
    assert second["case"]["revision"] == case["revision"] + 1


def test_visual_manual_review_requires_original_confirmation_matching_case_and_independent_actor(
    stack,
):
    disputes, agent, collab, _, _, _ = stack
    agent.model = None
    case = upload(collab, collecting(stack))[0]["case"]
    data = {
        "evidence_id": case["evidence"][0]["id"],
        "decision": "SUPPORTED",
        "reason": "Independent synthetic file inspection",
        "applicable_facts": ["Synthetic original reviewed"],
        "locators": ["page:1"],
        "transaction_id": case["transaction_id"],
        "currency": case["currency"],
        "amount_minor": case["amount_minor"],
    }
    with pytest.raises(DisputeError, match="Independently inspect"):
        command(disputes, case, "REVIEW_EVIDENCE_CONTENT", data, RISK)
    data["original_checked"] = True
    with pytest.raises(DisputeError, match="association"):
        command(
            disputes, case, "REVIEW_EVIDENCE_CONTENT", data | {"transaction_id": "unrelated"}, RISK
        )
    with pytest.raises(DisputeError):
        command(disputes, case, "REVIEW_EVIDENCE_CONTENT", data, MERCHANT)
    with pytest.raises(DisputeError, match="Cite a page"):
        command(disputes, case, "REVIEW_EVIDENCE_CONTENT", data | {"locators": ["page:2"]}, RISK)
    case = command(disputes, case, "REVIEW_EVIDENCE_CONTENT", data, RISK)
    item = case["evidence"][0]
    assert item["content_verified"] is True
    assert item["content_check"]["manual_review"]["original_checked"] is True
    assert item["content_check"]["automatic_check"]["status"] == "NEEDS_MANUAL"
    assert case["business_outcome"] == "UNKNOWN"


def test_document_replacement_invalidates_approved_package(stack):
    disputes, agent, collab, _, _, _ = stack
    case = submitted_evidence(stack)
    case = command(
        disputes,
        case,
        "REVIEW",
        {"decision": "PASS", "reason": "Synthetic independent review"},
        RISK,
    )
    case = command(disputes, case, "BUILD_PACKAGE")
    case = command(
        disputes,
        case,
        "APPROVE_PACKAGE",
        {"reason": "Synthetic final human review", "pii_checked": True},
        SUPERVISOR,
    )
    agent.model = None
    evidence = next(e for e in case["evidence"] if e["code"] == "fulfillment.proof_of_delivery")
    result, _ = upload(collab, case, evidence_id=evidence["id"])
    assert all(p["status"] != "APPROVED" for p in result["case"]["packages"])
    assert not result["case"]["evidence"][
        [e["id"] for e in case["evidence"]].index(evidence["id"])
    ]["content_verified"]


def test_document_parser_bounds_and_failures_are_explicit():
    damaged = read_document("bad.pdf", b"%PDF-corrupted", "proof")
    assert damaged["recognition"]["status"] == "FAILED"
    assert damaged["facts"] == {}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"x" * (6 * 1024 * 1024))
    assert read_document("big.docx", out.getvalue(), "proof")["recognition"]["status"] == "FAILED"
