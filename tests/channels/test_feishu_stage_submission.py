"""Stage story against real APIs/domain; Feishu transport is explicitly synthetic."""

import base64
import importlib.util
import json
from uuid import uuid4

import pytest

from oceanpilot.adapters.channels.feishu.case_explanations import focused_card
from oceanpilot.adapters.channels.feishu.v2 import FeishuV2Error
from oceanpilot.application.evidence_documents import read_document
from oceanpilot.application.model_provider import ModelResult, remaining_model_seconds
from oceanpilot.domain.dispute import DisputeError
from oceanpilot.domain.evidence_catalog import expected_source_of
from tests.channels.test_feishu_private_cases import bind, body, click, intake, message
from tests.channels.test_feishu_private_cases import env as env
from tests.v21_support import session_headers

spec = importlib.util.spec_from_file_location("stage_materials", "scripts/stage_materials.py")
materials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(materials)
PROOF = "fulfillment.proof_of_delivery"


def command(env, case, action, data, headers):
    return env.client.post(
        "/api/v2/commands",
        headers=headers,
        json={
            "command_id": str(uuid4()),
            "case_id": case["id"],
            "expected_revision": case["revision"],
            "action": action,
            "confirmed": True,
            "data": data,
        },
    )


def upload(env, case, code, content, headers, *, pdf=False, evidence_id=None):
    response = env.client.post(
        f"/api/v2/cases/{case['id']}/collaboration/files",
        headers=headers,
        json={
            "command_id": str(uuid4()),
            "expected_revision": case["revision"],
            "code": code,
            "title": "合成舞台材料",
            "filename": "proof.pdf" if pdf else "sample.json",
            "mime_type": "application/pdf" if pdf else "application/json",
            "content_base64": base64.b64encode(content).decode(),
            **({"evidence_id": evidence_id} if evidence_id else {}),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def prepared(env, *, include_proof=False):
    bind(env)
    case = intake(env)
    merchant = env.accounts["a"]["headers"]
    operator = session_headers(env.client, "OPERATOR", "synthetic-a")
    response = command(
        env,
        case,
        "MERCHANT_DECISION",
        {"decision": "CONTEST", "reason": "Synthetic stage"},
        merchant,
    )
    assert response.status_code == 200, response.text
    case = response.json()["case"]
    for code in case["rule_snapshot"]["required_evidence"]:
        if code == PROOF and not include_proof:
            continue
        sample = env.client.get(
            f"/api/v2/cases/{case['id']}/collaboration/samples/{code}?variant=sufficient",
            headers=merchant,
        )
        assert sample.status_code == 200, sample.text
        who = operator if expected_source_of(code) == "SYSTEM_OF_RECORD" else merchant
        case = upload(env, case, code, sample.content, who)["case"]
    return case, merchant, operator


def submission_card(env):
    env.bot.handle(message("我还缺什么"), mode="events")
    env.bot.drain()
    return env.bot.client.sent[-1]


def test_live_story_missing_time_revision_manual_notice_two_step_once(env):
    pytest.importorskip("reportlab")
    case, merchant, operator = prepared(env)
    card = submission_card(env)
    assert "确定性规则" in body(card)
    assert "提交材料给 OceanPayment" not in [
        b["text"]["content"] for e in card.card["elements"] for b in e.get("actions", [])
    ]
    first = upload(env, case, PROOF, materials.delivery_pdf(case), merchant, pdf=True)
    case = first["case"]
    check = first["file"]["content_check"]
    assert check["extraction_check_status"] == "INSUFFICIENT"
    assert "缺少送达时间" in " ".join(check["findings"])
    assert command(env, case, "SUBMIT_EVIDENCE", {}, merchant).status_code == 409
    evidence = next(e for e in case["evidence"] if e["code"] == PROOF)
    review = {
        "evidence_id": evidence["id"],
        "decision": "SUPPORTED",
        "reason": "独立打开原件核验",
        "original_checked": True,
        "transaction_id": case["transaction_id"],
        "currency": case["currency"],
        "amount_minor": case["amount_minor"],
        "applicable_facts": [
            "Received by Alex Demo (synthetic)",
            "delivered_at: 2026-09-12T10:00:00Z",
        ],
        "locators": ["page:1"],
    }
    blocked = command(env, case, "REVIEW_EVIDENCE_CONTENT", review, operator)
    assert blocked.status_code == 409 and "CONTENT_CORRECTION_REQUIRED" in blocked.text
    second = upload(
        env,
        case,
        PROOF,
        materials.delivery_pdf(case, delivered_at="2026-09-12T10:00:00Z"),
        merchant,
        pdf=True,
        evidence_id=evidence["id"],
    )
    case = second["case"]
    evidence = next(e for e in case["evidence"] if e["code"] == PROOF)
    assert evidence["revision"] == 2 and evidence["history"][0]["object_id"] == first["file"]["id"]
    assert second["file"]["content_check"]["extraction_check_status"] == "SUPPORTED"
    assert second["file"]["content_check"]["status"] == "NEEDS_MANUAL"
    assert command(env, case, "SUBMIT_EVIDENCE", {}, merchant).status_code == 409
    stale_review = env.client.post(
        "/api/v2/commands",
        headers=operator,
        json={
            "command_id": str(uuid4()),
            "action": "REVIEW_EVIDENCE_CONTENT",
            "case_id": case["id"],
            "expected_revision": first["case"]["revision"],
            "confirmed": True,
            "data": review,
        },
    )
    assert stale_review.status_code == 409
    reviewed = command(env, case, "REVIEW_EVIDENCE_CONTENT", review, operator)
    assert reviewed.status_code == 200, reviewed.text
    case = reviewed.json()["case"]
    env.bot.observe()
    env.bot.drain()
    receipt = env.bot.client.sent[-1]
    assert "材料已核验，可以提交" in body(receipt)
    before = case["revision"]
    env.bot.handle(click(receipt, "提交材料给 OceanPayment"), mode="card")
    env.bot.drain()
    receipt = env.bot.client.sent[-1]
    assert "不提交银行" in body(receipt)
    assert env.disputes.get_case(case["id"], env.accounts["a"])["revision"] == before
    callback = click(receipt, "确认提交材料给 OceanPayment")
    env.bot.handle(callback, mode="card")
    env.bot.handle(callback, mode="card")
    env.bot.handle(click(receipt, "确认提交材料给 OceanPayment"), mode="card")
    final = env.disputes.get_case(case["id"], env.accounts["a"])
    assert final["revision"] == before + 1
    assert final["work_status"] == "OP_REVIEW"
    assert final["business_outcome"] == "UNKNOWN" and final["finality"] == "NOT_FINAL"
    assert len([a for a in final["audit"] if a["action"] == "SUBMIT_EVIDENCE"]) == 1


@pytest.mark.parametrize("failure", ["forward", "other_merchant", "expiry", "revision", "unlink"])
def test_submit_confirmation_fails_closed(env, failure):
    case, merchant, _ = prepared(env, include_proof=True)
    receipt = submission_card(env)
    env.bot.handle(click(receipt, "提交材料给 OceanPayment"), mode="card")
    env.bot.drain()
    receipt = env.bot.client.sent[-1]
    callback = click(receipt, "确认提交材料给 OceanPayment")
    if failure == "forward":
        callback["event"]["context"]["open_message_id"] = "om_forwarded"
    if failure == "other_merchant":
        bind(env, "b")
        callback = click(receipt, "确认提交材料给 OceanPayment", actor="b")
    if failure == "expiry":
        env.clock[0] += 301
    if failure == "unlink":
        env.bot.unlink(env.accounts["a"]["actor_id"])
    if failure == "revision":
        response = command(env, case, "COMMENT", {"message": "Another version"}, merchant)
        assert response.status_code == 200, response.text
    with pytest.raises((FeishuV2Error, DisputeError)):
        env.bot.handle(callback, mode="card")
    assert (
        env.disputes.get_case(case["id"], env.accounts["a"])["work_status"] == "EVIDENCE_COLLECTING"
    )


def test_fact_focus_labels_real_model_and_deadline_without_business_text_invention(env):
    case, _, _ = prepared(env)
    card = submission_card(env).card

    class Model:
        def complete(self, *args, **kwargs):
            assert 0 < remaining_model_seconds(99) <= 3
            return ModelResult(
                text=json.dumps({"fact_ids": ["fact-0"]}), model="deepseek-test-exact-model"
            )

    result = focused_card(card, "materials", Model())
    assert "deepseek-test-exact-model" in result["elements"][0]["text"]["content"]

    class Failure:
        def complete(self, *args, **kwargs):
            raise TimeoutError("secret vendor error")

    result = focused_card(card, "materials", Failure())
    assert "确定性回退" in result["elements"][0]["text"]["content"]
    assert "secret vendor" not in json.dumps(result)
    assert env.disputes.get_case(case["id"], env.accounts["a"])["revision"] == case["revision"]


def test_explicit_text_pdf_does_not_need_model():
    pytest.importorskip("reportlab")

    class Failure:
        def complete(self, *args, **kwargs):
            raise AssertionError("Must not call model for explicit text fields")

    result = read_document(
        "any-name.pdf",
        materials.delivery_pdf(
            {"transaction_id": "synthetic-transaction", "currency": "USD", "amount_minor": 12500}
        ),
        PROOF,
        model=Failure(),
    )
    assert result["recognition"]["status"] == "LOCAL_EXTRACTED"
    assert "delivered_at" not in result["facts"]
    assert result["facts"]["transaction_id"] == "synthetic-transaction"


def test_duplicate_explicit_fields_are_missing_not_last_value_wins(monkeypatch):
    from oceanpilot.application import evidence_documents

    monkeypatch.setattr(
        evidence_documents,
        "_read_pdf",
        lambda _: (
            "transaction_id: synthetic\ncurrency: USD\namount_minor: 100\n"
            "delivered_at: 2026-09-12\ndelivered_at: 2026-09-13",
            [],
            1,
            False,
        ),
    )
    result = read_document("file.pdf", b"%PDF-synthetic", PROOF)
    assert result["facts"]["delivered_at"] is None
