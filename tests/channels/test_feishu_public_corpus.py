"""Release-corpus checks, not proof of real Feishu delivery or model quality."""

from pathlib import Path

import pytest

from oceanpilot.adapters.channels.feishu.public_knowledge import PublicKnowledge

CORPUS = Path(__file__).resolve().parents[2] / "docs/v2/feishu-public-knowledge.approved.json"


@pytest.mark.parametrize(
    "question,expected_source",
    [
        ("OceanPilot 是做什么的？", "oceanpilot-product-purpose"),
        ("怎样登录网站？", "oceanpilot-website-login"),
        ("在哪里上传材料？", "oceanpilot-material-guide"),
        ("退回补件是什么意思？", "oceanpilot-correction-feedback"),
        ("私聊案件助手开启了吗？", "oceanpilot-bot-boundary"),
        ("未收到货物的合成演示流程是什么？", "oceanpilot-synthetic-refusal-flow"),
        ("你能解决问题么", "oceanpilot-product-purpose"),
        ("能帮我做什么", "oceanpilot-product-purpose"),
        ("这是什么系统", "oceanpilot-product-purpose"),
        ("怎么用", "oceanpilot-website-login"),
        ("使用教程", "oceanpilot-website-login"),
        ("材料怎么传", "oceanpilot-material-guide"),
        ("资料在哪交", "oceanpilot-material-guide"),
        ("怎么补交文件", "oceanpilot-material-guide"),
        ("为什么被退回", "oceanpilot-correction-feedback"),
        ("被退回怎么办", "oceanpilot-correction-feedback"),
        ("如何登录", "oceanpilot-website-login"),
        ("登录不上怎么办", "oceanpilot-website-login"),
        ("商户和运营有什么区别", "oceanpilot-website-login"),
        ("经理和专员有啥区别", "oceanpilot-website-login"),
        ("群里能查订单吗", "oceanpilot-bot-boundary"),
        ("私聊能查进度吗", "oceanpilot-bot-boundary"),
        ("演示怎么走", "oceanpilot-synthetic-refusal-flow"),
        ("接受和抗辩有啥区别", "oceanpilot-synthetic-refusal-flow"),
        ("拒付已经撤销了吗", "oceanpilot-synthetic-refusal-flow"),
        ("能保证赢吗", "oceanpilot-synthetic-refusal-flow"),
    ],
)
def test_published_product_topics_retrieve_expected_source(question, expected_source):
    knowledge = PublicKnowledge.from_path(CORPUS)
    assert len(knowledge.documents) == 6
    answer = knowledge.answer(question)
    assert answer["mode"] == "RETRIEVAL_ONLY"
    assert answer["sources"][0]["id"] == expected_source


def test_release_corpus_distinguishes_local_private_activation_from_real_bank_access():
    knowledge = PublicKnowledge.from_path(CORPUS)
    documents = {doc["id"]: doc for doc in knowledge.documents}
    boundary = documents["oceanpilot-bot-boundary"]
    assert boundary["version"] == "public-v2"
    assert "绑定不增加原有案件权限" in boundary["text"]
    assert "群里不查询个人业务" in boundary["text"]
    assert "不代表真实银行已接通" in boundary["text"]
    flow = documents["oceanpilot-synthetic-refusal-flow"]
    assert flow["version"] == "public-v2"
    assert "第二次点击确认后才改变案件状态" in flow["text"]
    assert "完整独立验收和固定服务器部署仍待完成" in flow["text"]
    assert "Mock" in documents["oceanpilot-synthetic-refusal-flow"]["text"]
    assert "不保证胜诉" in documents["oceanpilot-synthetic-refusal-flow"]["text"]
    assert knowledge.answer("我的案件进度")["mode"] == "WEBSITE_HANDOFF"
    assert knowledge.answer("银行实际判决胜率是多少")["mode"] == "NO_MATCH"


@pytest.mark.parametrize(
    "question",
    [
        "今天北京天气怎么样",
        "OceanPilot 今天北京天气怎么样",
        "OceanPilot 银行实际判决胜率是多少",
        "拒付胜率是多少",
    ],
)
def test_product_name_or_single_incidental_word_is_not_evidence(question):
    assert PublicKnowledge.from_path(CORPUS).answer(question)["mode"] == "NO_MATCH"
