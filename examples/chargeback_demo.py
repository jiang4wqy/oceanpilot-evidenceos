"""Runnable synthetic chargeback demo — the agent cluster end to end.

Offline by default: uses the deterministic ScriptedModelProvider, so it runs
with no API key or network. Pass a real ModelProvider (e.g. ClaudeProvider) to
run against a model. It drives the full loop — describe -> intake classifies the
reason code -> evidence agent asks for each missing item (the demo answers on
the merchant's behalf) -> deterministic assessment + explanation.

Synthetic data only; no Oceanpayment/bank connection; no business action is
executed; human confirmation would only record advice.

Run:  python examples/chargeback_demo.py
"""

from collections.abc import Callable
from dataclasses import dataclass

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.chargeback_agents import (
    ChargebackAssessAgent,
    EvidenceAgent,
    IntakeAgent,
)
from oceanpilot.application.chargeback_supervisor import (
    ChargebackCaseState,
    ChargebackSupervisor,
    SupervisorPhase,
)
from oceanpilot.application.model_provider import ModelProvider

_DEFAULT_DESCRIPTION = "客户下单后一直没收到货，现在要求拒付。"
_MAX_ROUNDS = 50


def offline_provider() -> ModelProvider:
    """A deterministic provider for no-key demos.

    Its output does not parse to a reason code, so IntakeAgent falls back to its
    keyword heuristic (classifying from the description itself); evidence
    questions and the assessment explanation use this canned text.
    """
    return ScriptedModelProvider(default_text="（合成模型输出，仅用于离线演示）")


def build_supervisor(model: ModelProvider) -> ChargebackSupervisor:
    return ChargebackSupervisor(
        intake=IntakeAgent(model),
        evidence=EvidenceAgent(model),
        assess=ChargebackAssessAgent(model),
    )


@dataclass
class DemoResult:
    reason_code: str
    submitted_evidence: list[str]
    collected: list[str]
    win_likelihood: str
    responsible_team: str
    requires_human: bool
    explanation: str


def run(
    description: str = _DEFAULT_DESCRIPTION,
    *,
    model: ModelProvider | None = None,
    emit: Callable[[str], None] | None = None,
) -> DemoResult:
    say = emit or (lambda _message: None)
    supervisor = build_supervisor(model or offline_provider())
    state = ChargebackCaseState()

    say(
        "SYNTHETIC CHARGEBACK DEMO — no Oceanpayment/bank connection; "
        "no business action is executed."
    )
    say(f"商户描述：{description}")

    intake = supervisor.intake(state, description)
    say(
        f"→ Intake 分类：{state.reason_code.value} "
        f"(source={intake.source.value}, confident={intake.confident})"
    )

    submitted: list[str] = []
    step = supervisor.advance(state)
    while step.phase is SupervisorPhase.NEED_EVIDENCE:
        request = step.evidence_request
        assert request is not None and request.next_evidence is not None
        say(f"→ 补问：{request.question}")
        supervisor.submit_evidence(state, request.next_evidence)  # merchant answers
        submitted.append(request.next_evidence.value)
        if len(submitted) > _MAX_ROUNDS:
            raise RuntimeError("evidence loop did not converge")
        step = supervisor.advance(state)

    assert step.phase is SupervisorPhase.ASSESSED
    assert step.assessment is not None
    assessment = step.assessment.assessment
    say(
        f"→ 评估：规则证据就绪度 {int(assessment.win_likelihood * 100)}%（非胜诉概率），"
        f"责任域 {assessment.responsible_team.value}，"
        f"{'需人工复核' if assessment.requires_human else '可自动推进'}"
    )
    say(f"→ 说明：{step.assessment.explanation}")
    say("完成（合成）。人工确认仅记录建议，不执行任何业务动作。")

    return DemoResult(
        reason_code=state.reason_code.value,
        submitted_evidence=submitted,
        collected=sorted(code.value for code in state.collected),
        win_likelihood=str(assessment.win_likelihood),
        responsible_team=assessment.responsible_team.value,
        requires_human=assessment.requires_human,
        explanation=step.assessment.explanation,
    )


def main() -> int:
    run(emit=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
