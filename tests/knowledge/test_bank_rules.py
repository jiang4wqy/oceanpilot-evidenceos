from oceanpilot.adapters.knowledge.bank_rules import InMemoryBankRules
from oceanpilot.application.knowledge_base import BankRuleEntry, KnowledgeBase
from oceanpilot.domain.chargeback import (
    DisputeReasonCode,
    required_evidence_for,
)


def test_store_satisfies_protocol():
    assert isinstance(InMemoryBankRules(), KnowledgeBase)


def test_default_lookup_uses_kernel_checklist():
    kb = InMemoryBankRules()
    entry = kb.lookup(DisputeReasonCode.PRODUCT_NOT_AS_DESCRIBED)
    assert isinstance(entry, BankRuleEntry)
    assert entry.source == "default"
    assert entry.required_evidence == required_evidence_for(
        DisputeReasonCode.PRODUCT_NOT_AS_DESCRIBED
    )
    assert entry.submission_window_days == 15


def test_bank_specific_entry_wins_over_default():
    kb = InMemoryBankRules()
    entry = kb.lookup(
        DisputeReasonCode.PRODUCT_NOT_RECEIVED,
        bank_id="ACME_BANK",
        card_network="VISA",
    )
    assert entry.source == "bank"
    assert entry.submission_window_days == 12
    assert entry.template_order[0].value == "fulfillment.proof_of_delivery"


def test_network_entry_used_when_no_bank_match():
    kb = InMemoryBankRules()
    entry = kb.lookup(
        DisputeReasonCode.CREDIT_NOT_PROCESSED,
        bank_id="UNKNOWN_BANK",
        card_network="VISA",
    )
    assert entry.source == "network"


def test_unknown_bank_and_network_falls_back_to_default():
    kb = InMemoryBankRules()
    entry = kb.lookup(
        DisputeReasonCode.PRODUCT_NOT_RECEIVED,
        bank_id="NOPE",
        card_network="MASTERCARD",
    )
    assert entry.source == "default"


def test_every_reason_resolves():
    kb = InMemoryBankRules()
    for reason in DisputeReasonCode:
        entry = kb.lookup(reason)
        assert entry.required_evidence
        assert entry.template_order
