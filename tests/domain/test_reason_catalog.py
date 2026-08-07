import pytest

from oceanpilot.domain.chargeback import DisputeReasonCode
from oceanpilot.domain.reason_catalog import confirm_prompt, reason_label


def test_every_reason_code_has_a_label():
    for code in DisputeReasonCode:
        assert reason_label(code).strip()


def test_label_never_leaks_the_raw_token():
    for code in DisputeReasonCode:
        assert code.value not in reason_label(code)


def test_reason_label_rejects_non_enum():
    with pytest.raises(TypeError):
        reason_label("PRODUCT_NOT_RECEIVED")  # type: ignore[arg-type]


def test_confirm_prompt_contains_label_and_hides_token():
    code = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    for confident in (True, False):
        prompt = confirm_prompt(code, confident=confident)
        assert reason_label(code) in prompt
        assert code.value not in prompt


def test_confirm_prompt_distinguishes_confidence():
    code = DisputeReasonCode.AUTHORIZATION_ERROR
    assert confirm_prompt(code, confident=True) != confirm_prompt(code, confident=False)
    assert "暂不确定" in confirm_prompt(code, confident=False)


def test_english_reason_labels_are_exhaustive_and_distinct():
    for code in DisputeReasonCode:
        en = reason_label(code, locale="en")
        assert en.strip() and en.isascii()
        assert en != reason_label(code, locale="zh")
        assert code.value not in en
