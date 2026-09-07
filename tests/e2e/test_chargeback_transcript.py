from examples.chargeback_transcript import build


def test_transcript_runs_review_and_versioned_summary_offline(monkeypatch):
    # Explicit injection keeps the walkthrough offline even in a live shell.
    monkeypatch.setenv("OCEANPILOT_CHARGEBACK_LIVE_MODEL", "1")
    monkeypatch.setenv("OCEANPILOT_MODEL_PROVIDER", "unsupported")
    joined = "\n".join(build())
    for stage in ("材料就绪度 5/6", "补问", "操作回执", "人工登记复核", "HTML / JSON 已生成"):
        assert stage in joined
    assert "案件复核摘要（合成示例）" in joined
    assert "未读取或核验真实文件正文" in joined
    assert "不执行支付/退款/风控/提交动作" in joined
    assert "已提交上游" not in joined


def test_transcript_demonstrates_withdrawal_block_and_cross_scenario():
    joined = "\n".join(build())
    assert "旧审核已失效并保留历史" in joined
    assert "Visa 13.1" in joined
    assert "默认最终模拟发送由后端关闭" in joined
