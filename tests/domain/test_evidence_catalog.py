import pytest

from oceanpilot.domain.chargeback import ChargebackEvidenceCode
from oceanpilot.domain.evidence_catalog import (
    EvidenceDisplay,
    describe,
    label_of,
    rebuttal_line,
    request_sentence,
)


def test_catalog_covers_every_evidence_code():
    # Every code must be describable; a new code without an entry fails here.
    for code in ChargebackEvidenceCode:
        display = describe(code)
        assert isinstance(display, EvidenceDisplay)
        assert display.code is code


def test_every_entry_has_non_empty_human_content():
    for code in ChargebackEvidenceCode:
        d = describe(code)
        assert d.label.strip()
        assert d.description.strip()
        assert d.why.strip()
        assert len(d.examples) >= 1
        assert all(example.strip() for example in d.examples)


def test_labels_never_leak_the_raw_token():
    for code in ChargebackEvidenceCode:
        assert code.value not in label_of(code)


def test_describe_rejects_non_enum():
    with pytest.raises(TypeError):
        describe("fulfillment.proof_of_delivery")  # type: ignore[arg-type]


def test_request_sentence_is_human_and_hides_the_token():
    code = ChargebackEvidenceCode.PROOF_OF_DELIVERY
    sentence = request_sentence(code, remaining=3)
    assert label_of(code) in sentence
    assert code.value not in sentence
    assert "还差 3 项" in sentence


def test_request_sentence_marks_the_last_item():
    sentence = request_sentence(ChargebackEvidenceCode.TRANSACTION_RECEIPT, remaining=1)
    assert "最后 1 项" in sentence


def test_rebuttal_line_pairs_label_with_rationale_and_hides_token():
    for code in ChargebackEvidenceCode:
        line = rebuttal_line(code)
        display = describe(code)
        assert display.label in line
        assert display.why in line
        assert code.value not in line
