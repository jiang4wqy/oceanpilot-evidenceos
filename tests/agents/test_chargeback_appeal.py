from decimal import Decimal

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.adapters.upstream.mock import MockUpstreamConnector
from oceanpilot.application.chargeback_agents import ExplanationSource
from oceanpilot.application.chargeback_appeal import AppealAgent, AppealBlockedReason
from oceanpilot.application.chargeback_packager import RepresentmentPackage
from oceanpilot.application.model_provider import ModelProviderError
from oceanpilot.application.upstream import UpstreamConnector
from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode


def _package(*, ready: bool) -> RepresentmentPackage:
    evidence = (ChargebackEvidenceCode.TRANSACTION_RECEIPT,)
    return RepresentmentPackage(
        reason_code=DisputeReasonCode.CREDIT_NOT_PROCESSED,
        bank_id="ACME_BANK",
        card_network="VISA",
        ordered_evidence=evidence,
        missing_evidence=() if ready else (ChargebackEvidenceCode.REFUND_RECORD,),
        submission_window_days=14,
        completeness=Decimal("1.0000") if ready else Decimal("0.5000"),
        ready_to_submit=ready,
        rule_source="network",
        cover_note="note",
        cover_note_source=ExplanationSource.FALLBACK,
    )


def test_mock_connector_satisfies_protocol():
    assert isinstance(MockUpstreamConnector(), UpstreamConnector)


def test_draft_uses_model_then_falls_back():
    upstream = MockUpstreamConnector()
    model_ok = AppealAgent(ScriptedModelProvider(["尊敬的银行：随附证据…"]), upstream)
    draft, source = model_ok.draft(_package(ready=True))
    assert draft == "尊敬的银行：随附证据…"
    assert source is ExplanationSource.MODEL

    model_down = AppealAgent(ScriptedModelProvider(error=ModelProviderError()), upstream)
    draft2, source2 = model_down.draft(_package(ready=True))
    assert source2 is ExplanationSource.FALLBACK
    assert draft2


def test_submit_is_blocked_without_human_approval():
    upstream = MockUpstreamConnector()
    agent = AppealAgent(ScriptedModelProvider(default_text="letter"), upstream)
    outcome = agent.submit(_package(ready=True), human_approved=False, actor_id="ou_x")
    assert outcome.submitted is False
    assert outcome.blocked_reason is AppealBlockedReason.NOT_APPROVED
    assert upstream.submissions == []  # hard gate: connector never called


def test_submit_is_blocked_when_package_not_ready():
    upstream = MockUpstreamConnector()
    agent = AppealAgent(ScriptedModelProvider(default_text="letter"), upstream)
    outcome = agent.submit(_package(ready=False), human_approved=True, actor_id="ou_x")
    assert outcome.submitted is False
    assert outcome.blocked_reason is AppealBlockedReason.NOT_READY
    assert upstream.submissions == []


def test_approved_and_ready_submits_once_to_mock():
    upstream = MockUpstreamConnector()
    agent = AppealAgent(ScriptedModelProvider(default_text="letter"), upstream)
    outcome = agent.submit(_package(ready=True), human_approved=True, actor_id="ou_reviewer")
    assert outcome.submitted is True
    assert outcome.blocked_reason is None
    assert outcome.submission_id == "mock-sub-0001"
    assert outcome.status == "SUBMITTED"
    assert len(upstream.submissions) == 1
    assert upstream.submissions[0]["payload"]["approved_by"] == "ou_reviewer"
    assert upstream.submissions[0]["payload"]["synthetic"] is True
