from examples.chargeback_transcript import build


def test_transcript_runs_full_http_flow_offline():
    lines = build()
    joined = "\n".join(lines)
    # Each stage of the cluster appears in the transcript.
    assert "拒付风险" in joined  # prevention
    assert "判定原因" in joined  # intake
    assert "补问" in joined  # evidence loop
    assert "胜诉可能性" in joined  # assessment
    assert "证据构成" in joined  # per-evidence breakdown
    assert "representment" in joined  # packaging
    assert "已提交上游(mock)" in joined  # appeal after approval
    assert "CASE_OPENED" in joined  # audit trail
    # Safety envelope is stated.
    assert "不执行支付/退款/风控/提交动作" in joined


def test_transcript_appeal_is_blocked_before_approval():
    joined = "\n".join(build())
    # The hard human-approval gate is visible: blocked first, submitted after.
    assert "submitted=False" in joined
    assert "NOT_APPROVED" in joined
