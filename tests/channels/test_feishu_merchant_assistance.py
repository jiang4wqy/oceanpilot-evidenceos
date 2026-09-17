"""Regression for the owner's 2026-09-16 live findings; mock receipts, not live proof."""

import hashlib
import sqlite3
import time
from copy import deepcopy
from datetime import datetime

import pytest

from oceanpilot.adapters.channels.feishu.case_explanations import (
    merchant_answer,
    merchant_deadline,
    query_intent,
)
from oceanpilot.adapters.channels.feishu.private_cases import PrivateCaseBot
from oceanpilot.adapters.channels.feishu.v2 import FeishuV2Error
from oceanpilot.domain.dispute import DisputeError
from tests.channels.test_feishu_private_cases import bind, body, click, decision, intake, message
from tests.channels.test_feishu_private_cases import env as env
from tests.feishu.crypto_helpers import encrypted_body


def signed_post(env, payload, *, valid=True):
    payload = deepcopy(payload)
    payload["header"]["token"] = "test-token"
    raw = encrypted_body(payload, "test-secret")
    stamp = str(int(time.time()))
    nonce = "assistance-test"
    signature = hashlib.sha256((stamp + nonce + "test-secret").encode() + raw).hexdigest()
    return env.client.post(
        "/api/v2/integrations/feishu/events",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Lark-Request-Timestamp": stamp,
            "X-Lark-Request-Nonce": nonce,
            "X-Lark-Signature": signature if valid else "invalid",
        },
    )


def test_missing_unauthorized_and_retired_queries_get_same_safe_durable_reply(env):
    bind(env)
    other = intake(env, "b")
    retired = intake(env)
    with env.bot.db() as db:
        env.bot.put(db, "retired", retired["id"], "", "RETIRED", {})
    texts = []
    for target in [other["id"], "OPV2-unknown", retired["id"]]:
        request = message("查询 " + target)
        request["header"]["token"] = "test-token"
        before = len(env.bot.client.sent)
        assert signed_post(env, request, valid=False).status_code == 401
        assert signed_post(env, request).json()["outcome"] == "QUEUED"
        assert signed_post(env, request).json()["outcome"] == "REPLAYED"
        env.bot.drain()
        assert len(env.bot.client.sent) == before + 1
        text = body(env.bot.client.sent[-1])
        assert "无法访问该案件" in text and "我的案件" in text
        assert target not in text and "OPV2-" not in text
        texts.append(text)
        restarted = PrivateCaseBot(
            env.bot.path,
            directory=env.bot.directory,
            disputes=env.disputes,
            app_id="cli_test",
            secret="test-secret",
            base_url="https://example.test",
            client=env.bot.client,
            now=env.bot.now,
        )
        assert restarted.handle(request, mode="events")["outcome"] == "REPLAYED"
        restarted.drain()
        assert len(env.bot.client.sent) == before + 1
    assert len(set(texts)) == 1
    assert env.disputes.store.get_case(other["id"])["revision"] == other["revision"]


@pytest.mark.parametrize(
    "error", [sqlite3.OperationalError("storage"), DisputeError("BROKEN", "internal", 500)]
)
def test_expected_access_rejection_does_not_mask_operational_errors(env, monkeypatch, error):
    bind(env)

    def fail(*args):
        raise error

    monkeypatch.setattr(env.bot, "visible_case", fail)
    with pytest.raises(type(error)):
        env.bot.handle(message("OPV2-any"), mode="events")


def test_denial_reply_rechecks_binding_before_delivery(env):
    bind(env)
    env.bot.handle(message("OPV2-unknown"), mode="events")
    before = len(env.bot.client.sent)
    env.bot.unlink(env.accounts["a"]["actor_id"])
    env.bot.drain()
    assert len(env.bot.client.sent) == before


def test_disabled_account_cannot_use_query_error_as_auth_bypass(env):
    bind(env)
    env.bot.directory.set_disabled(env.accounts["a"]["actor_id"], True)
    with pytest.raises(FeishuV2Error, match="PRIVATE_ACCOUNT_UNAVAILABLE"):
        env.bot.handle(message("OPV2-unknown"), mode="events")


def test_no_model_accept_case_answers_are_question_specific_and_non_mutating(env):
    case, confirmation = decision(env, "ACCEPT")
    env.bot.handle(confirmation, mode="card")
    env.bot.drain()
    revision = env.disputes.store.get_case(case["id"])["revision"]
    replies = []
    for question, expected in [
        ("当前进度", "正在等待 OceanPayment 完成接受处理"),
        ("缺什么材料", "不需要继续提交抗辩材料"),
        ("为什么退回", "本案当前不是退回补件状态"),
        ("下一步做什么", "你已选择接受，暂不需要提交抗辩材料"),
        ("截止时间是什么，请换成北京时间", "北京时间 UTC+8"),
        ("请帮我把材料审核通过并提交银行", "我不能替代工作人员"),
    ]:
        env.bot.handle(message(question), mode="events")
        env.bot.drain()
        text = body(env.bot.client.sent[-1])
        assert expected in text[:600]
        assert "提交银行成功" not in text
        replies.append(text)
    assert len(set(replies)) == len(replies)
    assert env.disputes.store.get_case(case["id"])["revision"] == revision
    assert "本次未执行任何业务操作" in replies[-1]
    assert case["id"] not in replies[-1]


def test_multi_case_selection_preserves_deadline_question(env):
    bind(env)
    first = intake(env)
    second = intake(env)
    env.bot.handle(message("什么时候截止？"), mode="events")
    env.bot.drain()
    assert "请选择" in body(env.bot.client.sent[-1])
    env.bot.handle(
        click(env.bot.client.sent[-1], f"{second['id']} · {second['work_status']}"), mode="card"
    )
    env.bot.drain()
    text = body(env.bot.client.sent[-1])
    assert "答复：记录中的商户期限" in text
    assert first["id"] not in text and second["id"] in text


def test_deadline_conversion_expiry_accept_exemption_and_unknown_zone():
    view = {"deadlines": {"merchant": "2026-09-18T10:44:42+00:00"}, "merchant_decision": "CONTEST"}
    now = datetime.fromisoformat("2026-09-18T10:00:00+00:00").timestamp()
    text = merchant_deadline(view, now)
    assert "2026-09-18 18:44:42（北京时间 UTC+8）" in text and "约剩 45 分钟" in text
    assert "截至 2026-09-18 18:00" in text
    assert "期限已到" in merchant_deadline(view, now + 3600)
    accepted = merchant_deadline(view | {"merchant_decision": "ACCEPT"}, now + 3600)
    assert "不再要求提交抗辩材料" in accepted and "期限已到" not in accepted
    for raw in [None, "tomorrow", "2026-09-18T10:00:00"]:
        unknown = merchant_deadline({"deadlines": {"merchant": raw}}, now)
        assert "尚未核实" in unknown and "约剩" not in unknown


def test_materials_and_feedback_use_actual_projection_without_inventing():
    view = {"work_status": "EVIDENCE_COLLECTING", "merchant_decision": "CONTEST"}
    plan = {"checklist": [{"label": "规则指定样例", "upload_status": "MISSING"}]}
    assert "规则指定样例" in merchant_answer(view, plan, "materials", 0)
    assert "没有可查看的审核退回理由" in merchant_answer(view, plan, "feedback", 0)
    returned = view | {
        "work_status": "MERCHANT_REVISION_REQUIRED",
        "public_feedback": [{"reason": "只补签收页"}],
    }
    assert "审核反馈：只补签收页" in merchant_answer(returned, plan, "feedback", 0)
    assert "已有文件记录不等于本次审核通过" in merchant_answer(returned, plan, "materials", 0)
    assert query_intent("请帮我把材料审核通过并提交银行") == "staff_action"
    assert "缺少可核实的材料清单" in merchant_answer(view, {}, "materials", 0)
