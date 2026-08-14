import json

import pytest

from oceanpilot.adapters.ingestion.loader import (
    IngestionError,
    load_bank_rules,
    load_case_samples,
    load_reason_code_mappings,
    load_reason_policies,
    parse_json_records,
)
from oceanpilot.adapters.ingestion.samples import (
    SYNTHETIC_BANK_RULES,
    SYNTHETIC_CASE_SAMPLES,
    SYNTHETIC_REASON_CODE_MAPPINGS,
    SYNTHETIC_REASON_POLICIES,
)
from oceanpilot.application.knowledge_base import KnowledgeBase
from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode


def test_synthetic_bank_rules_load_into_a_working_knowledge_base():
    kb = load_bank_rules(SYNTHETIC_BANK_RULES)
    assert isinstance(kb, KnowledgeBase)

    # Bank-specific rule resolves most-specific first.
    bank = kb.lookup(
        DisputeReasonCode.PRODUCT_NOT_RECEIVED, bank_id="ACME_BANK", card_network="VISA"
    )
    assert bank.source == "bank"
    assert bank.template_order[0] is ChargebackEvidenceCode.PROOF_OF_DELIVERY
    assert bank.submission_window_days == 12

    # Network rule resolves when no bank match.
    network = kb.lookup(DisputeReasonCode.CREDIT_NOT_PROCESSED, card_network="VISA")
    assert network.source == "network"

    # Falls back to the kernel-derived default otherwise.
    default = kb.lookup(DisputeReasonCode.DUPLICATE_PROCESSING, card_network="MASTERCARD")
    assert default.source == "default"


def test_bank_rules_loaded_from_json_text_match_the_in_memory_bundle():
    records = parse_json_records(json.dumps(list(SYNTHETIC_BANK_RULES)))
    kb = load_bank_rules(records)
    entry = kb.lookup(
        DisputeReasonCode.PRODUCT_NOT_RECEIVED, bank_id="ACME_BANK", card_network="VISA"
    )
    assert entry.submission_window_days == 12


def test_reason_policies_load_and_key_by_reason_code():
    policies = load_reason_policies(SYNTHETIC_REASON_POLICIES)
    assert set(policies) == {
        DisputeReasonCode.PRODUCT_NOT_RECEIVED,
        DisputeReasonCode.FRAUD_CARD_NOT_PRESENT,
    }
    fraud = policies[DisputeReasonCode.FRAUD_CARD_NOT_PRESENT]
    assert fraud.high_risk is True
    assert any(req.critical for req in fraud.required)


def test_reason_code_mappings_normalize_and_resolve():
    mappings = load_reason_code_mappings(SYNTHETIC_REASON_CODE_MAPPINGS)
    assert mappings[("VISA", "13.1")] is DisputeReasonCode.PRODUCT_NOT_RECEIVED
    lower_case = [{**SYNTHETIC_REASON_CODE_MAPPINGS[0], "card_network": "visa"}]
    assert load_reason_code_mappings(lower_case)[("VISA", "13.1")] is (
        DisputeReasonCode.PRODUCT_NOT_RECEIVED
    )


def test_duplicate_reason_code_mapping_is_rejected_after_normalization():
    duplicate = {
        **SYNTHETIC_REASON_CODE_MAPPINGS[0],
        "card_network": "visa",
        "network_reason_code": "13.1",
    }
    with pytest.raises(IngestionError):
        load_reason_code_mappings([SYNTHETIC_REASON_CODE_MAPPINGS[0], duplicate])


@pytest.mark.parametrize("field", ["network_reason_code", "notes"])
def test_reason_code_mapping_rejects_sensitive_free_text(field: str):
    bad = [{**SYNTHETIC_REASON_CODE_MAPPINGS[0], field: "authorization=Bearer-SECRET"}]
    with pytest.raises(IngestionError):
        load_reason_code_mappings(bad)


def test_case_samples_load_and_are_synthetic():
    samples = load_case_samples(SYNTHETIC_CASE_SAMPLES)
    assert len(samples) == len(SYNTHETIC_CASE_SAMPLES)
    assert all(sample.synthetic is True for sample in samples)


def test_non_synthetic_case_sample_is_rejected():
    bad = [{**SYNTHETIC_CASE_SAMPLES[0], "synthetic": False}]
    with pytest.raises(IngestionError):
        load_case_samples(bad)


def test_case_sample_with_sensitive_notes_is_rejected():
    bad = [{**SYNTHETIC_CASE_SAMPLES[0], "notes": "authorization=Bearer-SECRET"}]
    with pytest.raises(IngestionError):
        load_case_samples(bad)


def test_bank_rule_with_sensitive_notes_is_rejected():
    bad = [{**SYNTHETIC_BANK_RULES[0], "notes": "authorization=Bearer-SECRET"}]
    with pytest.raises(IngestionError):
        load_bank_rules(bad)


def test_unknown_enum_value_is_rejected():
    bad = [{**SYNTHETIC_REASON_POLICIES[0], "reason_code": "NOT_A_REASON"}]
    with pytest.raises(IngestionError):
        load_reason_policies(bad)


def test_extra_field_is_rejected():
    bad = [{**SYNTHETIC_REASON_POLICIES[0], "surprise": "x"}]
    with pytest.raises(IngestionError):
        load_reason_policies(bad)


def test_template_order_must_be_a_permutation_of_required_evidence():
    bad = [{**SYNTHETIC_BANK_RULES[0], "template_order": ["transaction.receipt"]}]
    with pytest.raises(IngestionError):
        load_bank_rules(bad)


def test_bank_source_requires_bank_id():
    record = dict(SYNTHETIC_BANK_RULES[0])
    record.pop("bank_id")
    with pytest.raises(IngestionError):
        load_bank_rules([record])


def test_duplicate_reason_policy_is_rejected():
    with pytest.raises(IngestionError):
        load_reason_policies([SYNTHETIC_REASON_POLICIES[0], SYNTHETIC_REASON_POLICIES[0]])


def test_invalid_json_is_rejected():
    with pytest.raises(IngestionError):
        parse_json_records("{not json")
    with pytest.raises(IngestionError):
        parse_json_records(json.dumps({"not": "a list"}))
