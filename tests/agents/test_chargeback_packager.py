from decimal import Decimal

from oceanpilot.adapters.knowledge.bank_rules import InMemoryBankRules
from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.chargeback_agents import ExplanationSource
from oceanpilot.application.chargeback_packager import PackagerAgent
from oceanpilot.application.model_provider import ModelProviderError
from oceanpilot.domain.chargeback import (
    ChargebackEvidenceCode,
    DisputeReasonCode,
    required_evidence_for,
)


def _agent(model):
    return PackagerAgent(model, InMemoryBankRules())


def test_full_default_evidence_is_ready_and_ordered():
    reason = DisputeReasonCode.CREDIT_NOT_PROCESSED
    agent = _agent(ScriptedModelProvider(["随附退款凭证等证据。"]))
    pkg = agent.build(reason, required_evidence_for(reason))
    assert pkg.ready_to_submit is True
    assert pkg.missing_evidence == ()
    assert pkg.completeness == Decimal("1.0000")
    assert pkg.rule_source == "default"
    assert pkg.cover_note == "随附退款凭证等证据。"
    assert pkg.cover_note_source is ExplanationSource.MODEL


def test_bank_template_drives_order_and_window():
    agent = _agent(ScriptedModelProvider(default_text="note"))
    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    # ACME/VISA template puts proof of delivery first, 12-day window
    present = [
        ChargebackEvidenceCode.TRANSACTION_RECEIPT,
        ChargebackEvidenceCode.PROOF_OF_DELIVERY,
        ChargebackEvidenceCode.DELIVERY_TRACKING,
        ChargebackEvidenceCode.SHIPPING_ADDRESS_MATCH,
    ]
    pkg = agent.build(reason, present, bank_id="ACME_BANK", card_network="VISA")
    assert pkg.rule_source == "bank"
    assert pkg.submission_window_days == 12
    assert pkg.ordered_evidence[0] is ChargebackEvidenceCode.PROOF_OF_DELIVERY
    assert pkg.ready_to_submit is True


def test_scheme_guidance_exposes_traceable_rule_metadata():
    agent = _agent(ScriptedModelProvider(default_text="note"))
    pkg = agent.build(
        DisputeReasonCode.PRODUCT_NOT_RECEIVED,
        required_evidence_for(DisputeReasonCode.PRODUCT_NOT_RECEIVED),
        card_network="VISA",
    )
    assert pkg.rule_source == "network-guidance"
    assert pkg.scheme_reason_code == "13.1"
    assert pkg.rule_version == "June 2024"
    assert pkg.source_document == "Dispute Management Guidelines for Visa Merchants"
    assert "Condition 13.1" in (pkg.source_section or "")
    assert pkg.required_assertions
    assert "不是 Visa 官方申诉期限" in (pkg.rule_limitation or "")


def test_mastercard_4853_profile_is_scoped_to_not_as_described():
    agent = _agent(ScriptedModelProvider(default_text="note"))
    reason = DisputeReasonCode.PRODUCT_NOT_AS_DESCRIBED
    pkg = agent.build(reason, required_evidence_for(reason), card_network="MASTERCARD")
    assert pkg.scheme_reason_code == "4853"
    assert pkg.rule_version == "19 May 2026"
    assert "适用地区" in (pkg.rule_limitation or "")


def test_partial_evidence_reports_missing_and_not_ready():
    reason = DisputeReasonCode.CREDIT_NOT_PROCESSED
    agent = _agent(ScriptedModelProvider(default_text="note"))
    pkg = agent.build(reason, [ChargebackEvidenceCode.TRANSACTION_RECEIPT])
    assert pkg.ready_to_submit is False
    assert pkg.missing_evidence
    assert Decimal("0") < pkg.completeness < Decimal("1")
    # ordered only contains present items, in template order
    assert all(c in {ChargebackEvidenceCode.TRANSACTION_RECEIPT} for c in pkg.ordered_evidence)


def test_model_failure_falls_back_to_deterministic_note():
    reason = DisputeReasonCode.CREDIT_NOT_PROCESSED
    agent = _agent(ScriptedModelProvider(error=ModelProviderError()))
    pkg = agent.build(reason, required_evidence_for(reason))
    assert pkg.cover_note_source is ExplanationSource.FALLBACK
    assert pkg.cover_note
    assert pkg.ready_to_submit is True  # model failure never changes the package


def test_model_cannot_change_inclusion_or_order():
    reason = DisputeReasonCode.CREDIT_NOT_PROCESSED
    present = required_evidence_for(reason)
    deterministic = _agent(ScriptedModelProvider(default_text="A")).build(reason, present)
    other = _agent(ScriptedModelProvider(default_text="totally different note")).build(
        reason, present
    )
    assert deterministic.ordered_evidence == other.ordered_evidence
    assert deterministic.completeness == other.completeness
    assert deterministic.ready_to_submit == other.ready_to_submit


def test_fallback_note_uses_labels_not_raw_codes():
    from oceanpilot.domain.evidence_catalog import label_of

    agent = _agent(ScriptedModelProvider(error=ModelProviderError()))
    pkg = agent.build(
        DisputeReasonCode.CREDIT_NOT_PROCESSED,
        [ChargebackEvidenceCode.TRANSACTION_RECEIPT],
    )
    assert pkg.cover_note_source is ExplanationSource.FALLBACK
    assert label_of(ChargebackEvidenceCode.TRANSACTION_RECEIPT) in pkg.cover_note
    assert ChargebackEvidenceCode.TRANSACTION_RECEIPT.value not in pkg.cover_note
