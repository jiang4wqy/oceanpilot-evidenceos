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

import re
from dataclasses import dataclass

from oceanpilot.domain.chargeback import ChargebackEvidenceCode

_C = ChargebackEvidenceCode

MATERIAL_REGISTRATION_BOUNDARY = (
    "仅登记合成材料元数据；未读取或核验真实文件正文。"
    "材料就绪度仅表示内部清单登记情况，内容、真实性与适用性仍待人工核验。"
)


def has_unsupported_material_claim(text: str) -> bool:
    """Reject explicit content/probability claims unsupported by registered metadata.

    This is a conservative output guard in addition to deterministic fields and
    model instructions. It does not establish that arbitrary prose is true.
    """
    normalized = text.lower().replace(" ", "")
    for boundary in (
        "非胜诉概率",
        "不代表胜诉概率",
        "不代表真实胜诉概率",
        "notawinprobability",
        "notpredictedwinprobability",
    ):
        normalized = normalized.replace(boundary, "")
    patterns = (
        r"胜(?:诉)?(?:率|概率|评估)",
        r"真实业务准确率",
        r"准确率.{0,8}\d+%",
        r"交易(?:真实|属实)",
        r"内容(?:完全)?一致",
        r"(?:已|经)(?:读取|核验|验证).{0,12}(?:正文|文件|材料)",
        r"(?:正文|文件|材料).{0,12}(?:已核验|已验证|已读取)",
        r"证明.{0,18}(?:本人|真实|交付|送达|履约)",
        r"无需人工",
        r"可自动(?:通过|推进|提交)",
        r"官方(?:认可|可提交|证据包)",
        r"责任(?:已转移|转移成功)",
        r"win(?:rate|probability)",
        r"(?:verified|validated|read).{0,15}(?:document|content|file)",
        r"(?:genuine|authentic)transaction",
        r"contents?(?:is|are)?consistent",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


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
        why="供人工核对交易标识、金额、时间与商户信息；登记不表示真实性已核验。",
        examples=("支付网关交易详情", "订单确认页", "收款回执"),
    ),
    _C.AVS_RESULT: EvidenceDisplay(
        code=_C.AVS_RESULT,
        label="AVS 地址验证结果",
        description="发卡行返回的账单地址验证结果。",
        why="供人工核对返回码及其含义；登记不代表地址确已匹配。",
        examples=("授权响应中的 AVS 返回码(如 Y/A/Z)",),
    ),
    _C.CVV_RESULT: EvidenceDisplay(
        code=_C.CVV_RESULT,
        label="CVV 校验结果",
        description="交易时卡背验证码(CVV/CVC)的校验结果。",
        why="供人工核对校验结果；仅保留结果码，不能据此认定本人交易。",
        examples=("授权响应中的 CVV 返回码(如 M=匹配)",),
    ),
    _C.THREEDS_AUTHENTICATION: EvidenceDisplay(
        code=_C.THREEDS_AUTHENTICATION,
        label="3DS 认证结果",
        description="交易的 3-D Secure 强客户认证记录。",
        why="属于本合成内部清单的关键项，供人工核对认证记录；不据此认定责任转移或举证资格。",
        examples=("3DS 认证日志", "ECI 值", "CAVV/AAV"),
    ),
    _C.DEVICE_OR_IP_MATCH: EvidenceDisplay(
        code=_C.DEVICE_OR_IP_MATCH,
        label="设备/IP 匹配",
        description="下单设备指纹或 IP 与持卡人历史的一致性。",
        why="供人工核对设备与网络关联；登记不代表匹配结果或本人交易已获确认。",
        examples=("风控系统的设备指纹比对", "下单 IP 与归属地"),
    ),
    _C.DELIVERY_TRACKING: EvidenceDisplay(
        code=_C.DELIVERY_TRACKING,
        label="物流跟踪号/轨迹",
        description="商品的承运商单号与物流轨迹。",
        why="属于本合成内部清单的关键项，供人工追查运输过程；登记不代表实际发货或送达。",
        examples=("快递单号", "承运商物流轨迹截图"),
    ),
    _C.PROOF_OF_DELIVERY: EvidenceDisplay(
        code=_C.PROOF_OF_DELIVERY,
        label="签收证明",
        description="商品已妥投至持卡人的证明。",
        why="供人工核对妥投时间、地点与签收信息；登记不代表已核实送达。",
        examples=("快递妥投面单", "签收照片", "承运商出具的 POD"),
    ),
    _C.SHIPPING_ADDRESS_MATCH: EvidenceDisplay(
        code=_C.SHIPPING_ADDRESS_MATCH,
        label="收货地址匹配",
        description="收货地址与持卡人账单地址的一致性。",
        why="供人工比对订单、物流与账单地址；登记不代表地址匹配或送达已获确认。",
        examples=("订单收货地址与账单地址对比",),
    ),
    _C.PRODUCT_DESCRIPTION: EvidenceDisplay(
        code=_C.PRODUCT_DESCRIPTION,
        label="商品描述",
        description="下单时展示给消费者的商品描述与规格。",
        why="供人工比对下单页面与争议描述；登记不代表实际商品已核验。",
        examples=("商品详情页快照", "规格/参数说明"),
    ),
    _C.REFUND_RECORD: EvidenceDisplay(
        code=_C.REFUND_RECORD,
        label="退款记录",
        description="已按约定处理退款的凭证。",
        why="供人工核对退款标识、金额与状态；登记不代表退款已完成或已入账。",
        examples=("退款交易流水", "退款回执"),
    ),
    _C.TERMS_AND_REFUND_POLICY: EvidenceDisplay(
        code=_C.TERMS_AND_REFUND_POLICY,
        label="条款与退款政策",
        description="交易时已明示并经同意的服务条款与退款政策。",
        why="供人工核对当时展示的版本与接受记录；登记不代表条款已生效或被接受。",
        examples=("结算页条款勾选记录", "退款政策页快照"),
    ),
    _C.CUSTOMER_COMMUNICATION: EvidenceDisplay(
        code=_C.CUSTOMER_COMMUNICATION,
        label="客户沟通记录",
        description="与持卡人就本次问题的沟通与处理经过。",
        why="供人工梳理双方陈述与处理经过；登记不代表陈述已获得核实。",
        examples=("客服工单", "邮件/IM 往来(需脱敏)"),
    ),
    _C.CANCELLATION_RECORD: EvidenceDisplay(
        code=_C.CANCELLATION_RECORD,
        label="订阅取消记录",
        description="订阅取消请求的实际时间与状态。",
        why="供人工核对取消和扣费的时间顺序；登记不代表已判断扣费是否合理。",
        examples=("取消操作日志", "取消确认邮件"),
    ),
    _C.PRIOR_TRANSACTION_HISTORY: EvidenceDisplay(
        code=_C.PRIOR_TRANSACTION_HISTORY,
        label="历史交易记录",
        description="同一持卡人与商户的既往正常交易。",
        why="供人工核对既往交易关联；登记不代表历史记录真实或争议主张已被排除。",
        examples=("同卡历史成功订单列表(脱敏)",),
    ),
    _C.DUPLICATE_CHECK: EvidenceDisplay(
        code=_C.DUPLICATE_CHECK,
        label="重复扣款核查",
        description="两笔交易是否为重复扣款的比对结果。",
        why="供人工比对授权与流水标识；登记不代表已排除重复扣款。",
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
    """A material-registration bullet describing what still needs human review."""
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
