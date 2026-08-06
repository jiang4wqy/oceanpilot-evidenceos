from examples.chargeback_demo import DemoResult, run
from oceanpilot.domain.chargeback import DisputeReasonCode, required_evidence_for


def test_offline_demo_runs_full_loop_without_a_key():
    result = run()
    assert isinstance(result, DemoResult)
    assert result.reason_code == DisputeReasonCode.PRODUCT_NOT_RECEIVED.value
    # the loop collected exactly the required evidence and converged
    assert set(result.collected) == {
        code.value for code in required_evidence_for(DisputeReasonCode.PRODUCT_NOT_RECEIVED)
    }
    assert result.win_likelihood == "1.0000"
    assert result.explanation


def test_demo_emits_synthetic_disclaimer_and_steps():
    lines: list[str] = []
    run(emit=lines.append)
    joined = "\n".join(lines)
    assert "SYNTHETIC CHARGEBACK DEMO" in joined
    assert "不执行任何业务动作" in joined
    assert any("补问" in line for line in lines)
    assert any("评估" in line for line in lines)
