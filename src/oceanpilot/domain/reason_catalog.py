"""Human-facing labels for dispute reason codes.

Mirrors ``evidence_catalog``: the kernel speaks ``DisputeReasonCode`` tokens,
but a merchant/operator must see plain language. Used by the reason-confirmation
step so a human confirms 「未收到商品/服务」 rather than a ``PRODUCT_NOT_RECEIVED``
token. Exhaustive over ``DisputeReasonCode`` — a test enforces every code has a
label, so adding a reason code without a label fails the suite.
"""

from oceanpilot.domain.chargeback import DisputeReasonCode

_R = DisputeReasonCode

_LABELS: dict[DisputeReasonCode, str] = {
    _R.FRAUD_CARD_NOT_PRESENT: "无卡欺诈（未授权交易）",
    _R.PRODUCT_NOT_RECEIVED: "未收到商品/服务",
    _R.PRODUCT_NOT_AS_DESCRIBED: "商品与描述不符",
    _R.DUPLICATE_PROCESSING: "重复扣款",
    _R.CREDIT_NOT_PROCESSED: "退款未入账",
    _R.SUBSCRIPTION_CANCELED: "已取消订阅仍被扣费",
    _R.AUTHORIZATION_ERROR: "授权错误",
}


def reason_label(code: DisputeReasonCode) -> str:
    """The short human label for a reason code (never the raw token)."""
    if type(code) is not DisputeReasonCode:
        raise TypeError("code must be a DisputeReasonCode")
    return _LABELS[code]


def confirm_prompt(code: DisputeReasonCode, *, confident: bool) -> str:
    """The message shown when asking a human to confirm the proposed reason."""
    label = reason_label(code)
    if confident:
        return f"系统判定争议原因为「{label}」,请确认;如不符请更正后再继续。"
    return f"系统暂不确定争议原因,初步判断可能为「{label}」。请确认,或更正为正确的原因后再继续。"
