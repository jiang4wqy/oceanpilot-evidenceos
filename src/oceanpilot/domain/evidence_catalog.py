"""Human-facing catalog for chargeback evidence codes.

The kernel and agents speak in machine ``ChargebackEvidenceCode`` tokens (e.g.
``fulfillment.proof_of_delivery``). Those tokens must never be shown to a
merchant verbatim. This catalog maps every evidence code to a plain-language
label, a short description, *why* it matters for a representment, and a few
acceptable examples — so the evidence questions, the representment package, and
the appeal letter can all read like something a person wrote.

Content is synthetic, general card-scheme knowledge (no company data). The map
is exhaustive over ``ChargebackEvidenceCode`` — a test enforces that every code
has an entry, so adding a new code without describing it fails the suite.
"""

from dataclasses import dataclass

from oceanpilot.domain.chargeback import ChargebackEvidenceCode

_C = ChargebackEvidenceCode


@dataclass(frozen=True)
class EvidenceDisplay:
    """Merchant-facing description of one evidence code."""

    code: ChargebackEvidenceCode
    label: str
    description: str
    why: str
    examples: tuple[str, ...]


_CATALOG: dict[ChargebackEvidenceCode, EvidenceDisplay] = {
    _C.TRANSACTION_RECEIPT: EvidenceDisplay(
        code=_C.TRANSACTION_RECEIPT,
        label="交易收据",
        description="记录本笔交易的支付凭证。",
        why="证明交易真实发生,以及金额、时间与商户信息。",
        examples=("支付网关交易详情", "订单确认页", "收款回执"),
    ),
    _C.AVS_RESULT: EvidenceDisplay(
        code=_C.AVS_RESULT,
        label="AVS 地址验证结果",
        description="发卡行返回的账单地址验证结果。",
        why="证明下单时提供的账单地址与发卡行记录匹配,削弱盗刷主张。",
        examples=("授权响应中的 AVS 返回码(如 Y/A/Z)",),
    ),
    _C.CVV_RESULT: EvidenceDisplay(
        code=_C.CVV_RESULT,
        label="CVV 校验结果",
        description="交易时卡背验证码(CVV/CVC)的校验结果。",
        why="证明交易时持卡人提供了正确的卡背码,支持是本人交易。",
        examples=("授权响应中的 CVV 返回码(如 M=匹配)",),
    ),
    _C.THREEDS_AUTHENTICATION: EvidenceDisplay(
        code=_C.THREEDS_AUTHENTICATION,
        label="3DS 认证结果",
        description="交易的 3-D Secure 强客户认证记录。",
        why="3DS 认证通过通常将欺诈责任转移至发卡行,是欺诈类争议的关键证据。",
        examples=("3DS 认证日志", "ECI 值", "CAVV/AAV"),
    ),
    _C.DEVICE_OR_IP_MATCH: EvidenceDisplay(
        code=_C.DEVICE_OR_IP_MATCH,
        label="设备/IP 匹配",
        description="下单设备指纹或 IP 与持卡人历史的一致性。",
        why="证明下单设备/网络与持卡人既往行为一致,支持是本人交易。",
        examples=("风控系统的设备指纹比对", "下单 IP 与归属地"),
    ),
    _C.DELIVERY_TRACKING: EvidenceDisplay(
        code=_C.DELIVERY_TRACKING,
        label="物流跟踪号/轨迹",
        description="商品的承运商单号与物流轨迹。",
        why="证明商品已发出并可全程追踪,反驳「未收到商品」。",
        examples=("快递单号", "承运商物流轨迹截图"),
    ),
    _C.PROOF_OF_DELIVERY: EvidenceDisplay(
        code=_C.PROOF_OF_DELIVERY,
        label="签收证明",
        description="商品已妥投至持卡人的证明。",
        why="直接证明商品已送达,是「未收到商品」类争议的关键证据。",
        examples=("快递妥投面单", "签收照片", "承运商出具的 POD"),
    ),
    _C.SHIPPING_ADDRESS_MATCH: EvidenceDisplay(
        code=_C.SHIPPING_ADDRESS_MATCH,
        label="收货地址匹配",
        description="收货地址与持卡人账单地址的一致性。",
        why="证明商品寄往持卡人本人地址,支持是本人交易且已送达。",
        examples=("订单收货地址与账单地址对比",),
    ),
    _C.PRODUCT_DESCRIPTION: EvidenceDisplay(
        code=_C.PRODUCT_DESCRIPTION,
        label="商品描述",
        description="下单时展示给消费者的商品描述与规格。",
        why="证明实际商品与页面描述一致,反驳「与描述不符」。",
        examples=("商品详情页快照", "规格/参数说明"),
    ),
    _C.REFUND_RECORD: EvidenceDisplay(
        code=_C.REFUND_RECORD,
        label="退款记录",
        description="已按约定处理退款的凭证。",
        why="证明退款已发起/完成,反驳「退款未入账」。",
        examples=("退款交易流水", "退款回执"),
    ),
    _C.TERMS_AND_REFUND_POLICY: EvidenceDisplay(
        code=_C.TERMS_AND_REFUND_POLICY,
        label="条款与退款政策",
        description="交易时已明示并经同意的服务条款与退款政策。",
        why="证明消费者在交易时已知悉并接受相关条款,界定责任边界。",
        examples=("结算页条款勾选记录", "退款政策页快照"),
    ),
    _C.CUSTOMER_COMMUNICATION: EvidenceDisplay(
        code=_C.CUSTOMER_COMMUNICATION,
        label="客户沟通记录",
        description="与持卡人就本次问题的沟通与处理经过。",
        why="佐证商户已积极处理,并还原争议的真实经过。",
        examples=("客服工单", "邮件/IM 往来(需脱敏)"),
    ),
    _C.CANCELLATION_RECORD: EvidenceDisplay(
        code=_C.CANCELLATION_RECORD,
        label="订阅取消记录",
        description="订阅取消请求的实际时间与状态。",
        why="界定扣费发生在取消之前还是之后,判断扣费是否合理。",
        examples=("取消操作日志", "取消确认邮件"),
    ),
    _C.PRIOR_TRANSACTION_HISTORY: EvidenceDisplay(
        code=_C.PRIOR_TRANSACTION_HISTORY,
        label="历史交易记录",
        description="同一持卡人与商户的既往正常交易。",
        why="证明持卡人与商户存在长期正常交易关系,削弱欺诈主张。",
        examples=("同卡历史成功订单列表(脱敏)",),
    ),
    _C.DUPLICATE_CHECK: EvidenceDisplay(
        code=_C.DUPLICATE_CHECK,
        label="重复扣款核查",
        description="两笔交易是否为重复扣款的比对结果。",
        why="通过授权码/流水比对确认两笔并非重复,反驳「重复扣款」。",
        examples=("两笔交易的授权码/流水对比",),
    ),
}


# English labels (cross-border): keyed by code, exhaustive over the enum.
_LABELS_EN: dict[ChargebackEvidenceCode, str] = {
    _C.TRANSACTION_RECEIPT: "Transaction receipt",
    _C.AVS_RESULT: "AVS result",
    _C.CVV_RESULT: "CVV result",
    _C.THREEDS_AUTHENTICATION: "3DS authentication",
    _C.DEVICE_OR_IP_MATCH: "Device/IP match",
    _C.DELIVERY_TRACKING: "Delivery tracking",
    _C.PROOF_OF_DELIVERY: "Proof of delivery",
    _C.SHIPPING_ADDRESS_MATCH: "Shipping address match",
    _C.PRODUCT_DESCRIPTION: "Product description",
    _C.REFUND_RECORD: "Refund record",
    _C.TERMS_AND_REFUND_POLICY: "Terms & refund policy",
    _C.CUSTOMER_COMMUNICATION: "Customer communication",
    _C.CANCELLATION_RECORD: "Cancellation record",
    _C.PRIOR_TRANSACTION_HISTORY: "Prior transaction history",
    _C.DUPLICATE_CHECK: "Duplicate-charge check",
}


def describe(code: ChargebackEvidenceCode) -> EvidenceDisplay:
    """The merchant-facing description of an evidence code."""
    if type(code) is not ChargebackEvidenceCode:
        raise TypeError("code must be a ChargebackEvidenceCode")
    return _CATALOG[code]


def label_of(code: ChargebackEvidenceCode, *, locale: str = "zh") -> str:
    """The short human label for an evidence code (never the raw token).

    ``locale="en"`` returns the English label; anything else falls back to zh.
    """
    display = describe(code)  # validates the code
    return _LABELS_EN[code] if locale == "en" else display.label


def rebuttal_line(code: ChargebackEvidenceCode) -> str:
    """A representment bullet: the evidence label and how it rebuts the dispute.

    Used by the packager and appeal letter so each enclosed item reads as an
    argument ("签收证明 —— 直接证明商品已送达 …"), never a raw code token.
    """
    display = describe(code)
    return f"{display.label} —— {display.why}"


def request_sentence(code: ChargebackEvidenceCode, remaining: int) -> str:
    """A deterministic, merchant-friendly ask for one evidence item.

    Used as the Evidence agent's fallback question when no model is reachable —
    it names the evidence in plain language and says why it matters, instead of
    leaking the raw ``code.value`` token.
    """
    display = describe(code)
    tail = f"(还差 {remaining} 项)" if remaining > 1 else "(最后 1 项)"
    return f"请提供「{display.label}」——{display.description}{display.why}{tail}"
