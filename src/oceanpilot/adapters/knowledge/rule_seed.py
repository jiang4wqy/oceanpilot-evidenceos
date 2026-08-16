"""Curated, public-source rule summaries used to seed the local demo catalog."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuleDocumentSeed:
    document_id: str
    scheme: str
    title: str
    publisher: str
    source_url: str
    source_version: str | None


@dataclass(frozen=True, slots=True)
class RuleVersionSeed:
    rule_version_id: str
    document_id: str
    scheme_reason_code: str
    display_name: str
    category: str
    region: str
    version_label: str | None
    source_section: str | None
    effective_date: str | None
    internal_reason_code: str | None
    demo_role: str
    internal_window_days: int | None
    verification_status: str
    limitation: str


@dataclass(frozen=True, slots=True)
class RuleRequirementSeed:
    requirement_id: str
    rule_version_id: str
    requirement_type: str
    necessity: str
    sequence: int
    description_zh: str
    internal_evidence_code: str | None


def _requirement(
    rule_version_id: str,
    requirement_type: str,
    sequence: int,
    description_zh: str,
    internal_evidence_code: str | None = None,
    *,
    necessity: str = "REQUIRED",
) -> RuleRequirementSeed:
    prefix = "assertion" if requirement_type == "ASSERTION" else "evidence"
    return RuleRequirementSeed(
        requirement_id=f"{rule_version_id}-{prefix}-{sequence:02d}",
        rule_version_id=rule_version_id,
        requirement_type=requirement_type,
        necessity=necessity,
        sequence=sequence,
        description_zh=description_zh,
        internal_evidence_code=internal_evidence_code,
    )


RULE_DOCUMENT_SEEDS = (
    RuleDocumentSeed(
        document_id="visa-dispute-management-guidelines",
        scheme="VISA",
        title="Dispute Management Guidelines for Visa Merchants",
        publisher="Visa",
        source_url=(
            "https://by.visa.com/dam/VCOM/global/support-legal/documents/"
            "merchants-dispute-management-guidelines.pdf"
        ),
        source_version="June 2024",
    ),
    RuleDocumentSeed(
        document_id="mastercard-chargeback-guide-merchant",
        scheme="MASTERCARD",
        title="Chargeback Guide — Merchant Edition",
        publisher="Mastercard",
        source_url=(
            "https://www.mastercard.com/content/dam/mccom/shared/business/support/"
            "rules-pdfs/chargeback-guide.pdf"
        ),
        source_version="19 May 2026",
    ),
    RuleDocumentSeed(
        document_id="amex-merchant-regulations-international",
        scheme="AMEX",
        title="American Express Merchant Regulations — International",
        publisher="American Express",
        source_url=(
            "https://www.americanexpress.com/content/dam/amex/us/merchant/"
            "new-merchant-regulations/Regs_EN_SG.pdf"
        ),
        source_version=None,
    ),
    RuleDocumentSeed(
        document_id="oceanpayment-threeds-developer-doc",
        scheme="OCEANPAYMENT",
        title="Oceanpayment 3DS Developer Documentation",
        publisher="Oceanpayment",
        source_url="https://dev.oceanpayment.com/en/docs/compliance-and-security/threeds/",
        source_version=None,
    ),
)


_UNVERIFIED = "UNVERIFIED_SUMMARY"
_VISA_LIMITATION = "商户指南演示摘要；适用地区、流程、责任转移与正式期限须以有效规则复核。"

RULE_VERSION_SEEDS = (
    RuleVersionSeed(
        rule_version_id="visa-10-4-demo-v1",
        document_id="visa-dispute-management-guidelines",
        scheme_reason_code="10.4",
        display_name="非本人交易（无卡环境）",
        category="FRAUD",
        region="GLOBAL",
        version_label="June 2024",
        source_section="Condition 10.4 — Other Fraud, Card-Absent Environment",
        effective_date=None,
        internal_reason_code="FRAUD_CARD_NOT_PRESENT",
        demo_role="DEMO_MAPPED",
        internal_window_days=15,
        verification_status=_UNVERIFIED,
        limitation=(
            "商户指南演示摘要；不自动判定 CE3.0、3DS 责任转移或正式申诉资格，"
            "15 天仅为原型内部准备窗口。"
        ),
    ),
    RuleVersionSeed(
        rule_version_id="visa-12-6-display-v1",
        document_id="visa-dispute-management-guidelines",
        scheme_reason_code="12.6",
        display_name="重复处理 / 其他方式付款",
        category="PROCESSING_ERROR",
        region="GLOBAL",
        version_label="June 2024",
        source_section="Condition 12.6 — Duplicate Processing/Paid by Other Means",
        effective_date=None,
        internal_reason_code="DUPLICATE_PROCESSING",
        demo_role="DISPLAY_ONLY",
        internal_window_days=None,
        verification_status=_UNVERIFIED,
        limitation=_VISA_LIMITATION,
    ),
    RuleVersionSeed(
        rule_version_id="visa-13-1-demo-v1",
        document_id="visa-dispute-management-guidelines",
        scheme_reason_code="13.1",
        display_name="商品 / 服务未收到",
        category="CONSUMER_DISPUTE",
        region="GLOBAL",
        version_label="June 2024",
        source_section="Condition 13.1 — Merchandise/Services Not Received",
        effective_date=None,
        internal_reason_code="PRODUCT_NOT_RECEIVED",
        demo_role="DEMO_MAPPED",
        internal_window_days=15,
        verification_status=_UNVERIFIED,
        limitation=("商户指南演示摘要；15 天为本原型内部准备窗口，不是 Visa 官方申诉期限。"),
    ),
    RuleVersionSeed(
        rule_version_id="visa-13-2-display-v1",
        document_id="visa-dispute-management-guidelines",
        scheme_reason_code="13.2",
        display_name="已取消的循环交易",
        category="CONSUMER_DISPUTE",
        region="GLOBAL",
        version_label="June 2024",
        source_section="Condition 13.2 — Cancelled Recurring Transaction",
        effective_date=None,
        internal_reason_code="SUBSCRIPTION_CANCELED",
        demo_role="DISPLAY_ONLY",
        internal_window_days=None,
        verification_status=_UNVERIFIED,
        limitation=_VISA_LIMITATION,
    ),
    RuleVersionSeed(
        rule_version_id="visa-13-3-display-v1",
        document_id="visa-dispute-management-guidelines",
        scheme_reason_code="13.3",
        display_name="与描述不符 / 商品或服务有缺陷",
        category="CONSUMER_DISPUTE",
        region="GLOBAL",
        version_label="June 2024",
        source_section="Condition 13.3 — Not as Described or Defective",
        effective_date=None,
        internal_reason_code="PRODUCT_NOT_AS_DESCRIBED",
        demo_role="DISPLAY_ONLY",
        internal_window_days=None,
        verification_status=_UNVERIFIED,
        limitation=_VISA_LIMITATION,
    ),
    RuleVersionSeed(
        rule_version_id="visa-13-6-display-v1",
        document_id="visa-dispute-management-guidelines",
        scheme_reason_code="13.6",
        display_name="退款未处理",
        category="CONSUMER_DISPUTE",
        region="GLOBAL",
        version_label="June 2024",
        source_section="Condition 13.6 — Credit Not Processed",
        effective_date=None,
        internal_reason_code="CREDIT_NOT_PROCESSED",
        demo_role="DISPLAY_ONLY",
        internal_window_days=None,
        verification_status=_UNVERIFIED,
        limitation=_VISA_LIMITATION,
    ),
    RuleVersionSeed(
        rule_version_id="mastercard-4853-demo-v1",
        document_id="mastercard-chargeback-guide-merchant",
        scheme_reason_code="4853",
        display_name="持卡人争议 — 商品 / 服务与描述不符",
        category="CARDHOLDER_DISPUTE",
        region="GLOBAL",
        version_label="19 May 2026",
        source_section="Cardholder Dispute Chargeback — Goods or Services Not as Described",
        effective_date=None,
        internal_reason_code="PRODUCT_NOT_AS_DESCRIBED",
        demo_role="DEMO_MAPPED",
        internal_window_days=15,
        verification_status=_UNVERIFIED,
        limitation=(
            "合成演示配置；适用地区、消息系统、阶段及正式期限仍需生产规则确认，"
            "15 天仅为原型内部准备窗口。"
        ),
    ),
    RuleVersionSeed(
        rule_version_id="amex-c04-display-v1",
        document_id="amex-merchant-regulations-international",
        scheme_reason_code="C04",
        display_name="商品 / 服务已退回或拒收",
        category="CARDMEMBER_DISPUTE",
        region="INTERNATIONAL",
        version_label=None,
        source_section="C04 — Goods/Services Returned or Refused",
        effective_date=None,
        internal_reason_code=None,
        demo_role="DISPLAY_ONLY",
        internal_window_days=None,
        verification_status=_UNVERIFIED,
        limitation=("American Express 规则演示摘要；地区、版本、适用条件及正式期限尚未核验。"),
    ),
    RuleVersionSeed(
        rule_version_id="amex-c05-display-v1",
        document_id="amex-merchant-regulations-international",
        scheme_reason_code="C05",
        display_name="商品 / 服务已取消",
        category="CARDMEMBER_DISPUTE",
        region="INTERNATIONAL",
        version_label=None,
        source_section="C05 — Goods/Services Cancelled",
        effective_date=None,
        internal_reason_code=None,
        demo_role="DISPLAY_ONLY",
        internal_window_days=None,
        verification_status=_UNVERIFIED,
        limitation=("American Express 规则演示摘要；地区、版本、适用条件及正式期限尚未核验。"),
    ),
    RuleVersionSeed(
        rule_version_id="oceanpayment-threeds-doc",
        document_id="oceanpayment-threeds-developer-doc",
        scheme_reason_code="3DS_CONTEXT",
        display_name="3DS 认证技术背景",
        category="TECHNICAL_CONTEXT",
        region="GLOBAL",
        version_label=None,
        source_section="3DS",
        effective_date=None,
        internal_reason_code=None,
        demo_role="DISPLAY_ONLY",
        internal_window_days=None,
        verification_status=_UNVERIFIED,
        limitation=(
            "仅用于解释 3DS 接入与材料留存语境；不参与卡组织争议资格、责任转移或期限判定。"
        ),
    ),
)


RULE_REQUIREMENT_SEEDS = (
    # Visa 10.4 — the four evidence rows reproduce the existing package profile.
    _requirement("visa-10-4-demo-v1", "ASSERTION", 1, "持卡人参与交易或从交易中受益"),
    _requirement("visa-10-4-demo-v1", "ASSERTION", 2, "认证、设备或网络信息能够关联争议交易"),
    _requirement("visa-10-4-demo-v1", "ASSERTION", 3, "历史无争议交易满足适用的关联条件"),
    _requirement("visa-10-4-demo-v1", "EVIDENCE", 1, "3DS 认证结果", "auth.threeds"),
    _requirement("visa-10-4-demo-v1", "EVIDENCE", 2, "设备或 IP 关联", "auth.device_ip_match"),
    _requirement(
        "visa-10-4-demo-v1",
        "EVIDENCE",
        3,
        "历史无争议交易记录",
        "history.prior_transactions",
    ),
    _requirement("visa-10-4-demo-v1", "EVIDENCE", 4, "争议交易收据", "transaction.receipt"),
    # Visa 12.6.
    _requirement("visa-12-6-display-v1", "ASSERTION", 1, "相似交易对应独立订单或独立服务"),
    _requirement("visa-12-6-display-v1", "EVIDENCE", 1, "交易收据", "transaction.receipt"),
    _requirement("visa-12-6-display-v1", "EVIDENCE", 2, "重复扣款核查", "billing.duplicate_check"),
    _requirement(
        "visa-12-6-display-v1",
        "EVIDENCE",
        3,
        "订单、发票或服务关联记录",
        "history.prior_transactions",
        necessity="RECOMMENDED",
    ),
    # Visa 13.1.
    _requirement("visa-13-1-demo-v1", "ASSERTION", 1, "商品或服务已经交付"),
    _requirement("visa-13-1-demo-v1", "ASSERTION", 2, "在约定日期前交付或可供取用"),
    _requirement("visa-13-1-demo-v1", "ASSERTION", 3, "交付至约定地点并与争议交易关联"),
    _requirement("visa-13-1-demo-v1", "EVIDENCE", 1, "争议交易收据", "transaction.receipt"),
    _requirement("visa-13-1-demo-v1", "EVIDENCE", 2, "物流跟踪号与轨迹", "fulfillment.tracking"),
    _requirement("visa-13-1-demo-v1", "EVIDENCE", 3, "收货地址匹配", "fulfillment.address_match"),
    _requirement(
        "visa-13-1-demo-v1",
        "EVIDENCE",
        4,
        "签收或妥投证明",
        "fulfillment.proof_of_delivery",
    ),
    _requirement("visa-13-1-demo-v1", "EVIDENCE", 5, "客户沟通记录", "comms.customer"),
    # Visa 13.2.
    _requirement("visa-13-2-display-v1", "ASSERTION", 1, "争议交易发生时仍存在有效循环扣款授权"),
    _requirement(
        "visa-13-2-display-v1",
        "EVIDENCE",
        1,
        "取消时间与状态记录",
        "subscription.cancellation_record",
    ),
    _requirement(
        "visa-13-2-display-v1", "EVIDENCE", 2, "循环扣款与取消条款", "policy.terms_refund"
    ),
    _requirement("visa-13-2-display-v1", "EVIDENCE", 3, "争议交易收据", "transaction.receipt"),
    _requirement(
        "visa-13-2-display-v1",
        "EVIDENCE",
        4,
        "取消确认或客户沟通",
        "comms.customer",
        necessity="RECOMMENDED",
    ),
    # Visa 13.3.
    _requirement("visa-13-3-display-v1", "ASSERTION", 1, "实际交付内容符合购买时的描述或合同"),
    _requirement("visa-13-3-display-v1", "EVIDENCE", 1, "争议交易收据", "transaction.receipt"),
    _requirement(
        "visa-13-3-display-v1", "EVIDENCE", 2, "购买时的商品或服务描述", "product.description"
    ),
    _requirement(
        "visa-13-3-display-v1",
        "EVIDENCE",
        3,
        "交付或签收记录",
        "fulfillment.proof_of_delivery",
    ),
    _requirement("visa-13-3-display-v1", "EVIDENCE", 4, "客户沟通记录", "comms.customer"),
    _requirement(
        "visa-13-3-display-v1",
        "EVIDENCE",
        5,
        "条款、退换货或退款政策",
        "policy.terms_refund",
        necessity="RECOMMENDED",
    ),
    # Visa 13.6.
    _requirement("visa-13-6-display-v1", "ASSERTION", 1, "退款已按约定发起或完成"),
    _requirement(
        "visa-13-6-display-v1", "EVIDENCE", 1, "退款流水、ARN 或退款回执", "billing.refund_record"
    ),
    _requirement("visa-13-6-display-v1", "EVIDENCE", 2, "原始交易收据", "transaction.receipt"),
    _requirement(
        "visa-13-6-display-v1",
        "EVIDENCE",
        3,
        "退款沟通记录",
        "comms.customer",
        necessity="RECOMMENDED",
    ),
    # Mastercard 4853 — scoped to not-as-described for this demo mapping.
    _requirement("mastercard-4853-demo-v1", "ASSERTION", 1, "商品或服务符合交易时的描述或合同"),
    _requirement(
        "mastercard-4853-demo-v1",
        "ASSERTION",
        2,
        "履约、维修、替换或交付记录能够对应争议交易",
    ),
    _requirement("mastercard-4853-demo-v1", "ASSERTION", 3, "商户材料逐项回应持卡人的具体主张"),
    _requirement("mastercard-4853-demo-v1", "EVIDENCE", 1, "争议交易收据", "transaction.receipt"),
    _requirement("mastercard-4853-demo-v1", "EVIDENCE", 2, "商品或服务描述", "product.description"),
    _requirement(
        "mastercard-4853-demo-v1",
        "EVIDENCE",
        3,
        "交付或签收记录",
        "fulfillment.proof_of_delivery",
    ),
    _requirement("mastercard-4853-demo-v1", "EVIDENCE", 4, "客户沟通记录", "comms.customer"),
    _requirement("mastercard-4853-demo-v1", "EVIDENCE", 5, "条款与退款政策", "policy.terms_refund"),
    # Amex C04.
    _requirement("amex-c04-display-v1", "ASSERTION", 1, "商品未实际退回或退回不符合披露政策"),
    _requirement("amex-c04-display-v1", "EVIDENCE", 1, "退货与退款政策", "policy.terms_refund"),
    _requirement(
        "amex-c04-display-v1",
        "EVIDENCE",
        2,
        "商品交付或服务使用记录",
        "fulfillment.proof_of_delivery",
    ),
    _requirement("amex-c04-display-v1", "EVIDENCE", 3, "客户沟通记录", "comms.customer"),
    _requirement(
        "amex-c04-display-v1",
        "EVIDENCE",
        4,
        "退款记录（如适用）",
        "billing.refund_record",
        necessity="RECOMMENDED",
    ),
    # Amex C05.
    _requirement("amex-c05-display-v1", "ASSERTION", 1, "取消发生在政策截止时间之后或不符合条款"),
    _requirement(
        "amex-c05-display-v1",
        "EVIDENCE",
        1,
        "取消请求时间与状态",
        "subscription.cancellation_record",
    ),
    _requirement("amex-c05-display-v1", "EVIDENCE", 2, "取消政策与披露记录", "policy.terms_refund"),
    _requirement("amex-c05-display-v1", "EVIDENCE", 3, "取消确认或客户沟通", "comms.customer"),
    _requirement(
        "amex-c05-display-v1",
        "EVIDENCE",
        4,
        "争议交易收据",
        "transaction.receipt",
        necessity="RECOMMENDED",
    ),
    # Oceanpayment 3DS product documentation — technical context only.
    _requirement(
        "oceanpayment-threeds-doc",
        "EVIDENCE",
        1,
        "保留 Synthetic 3DS 认证结果作为案件技术上下文",
        "auth.threeds",
        necessity="RECOMMENDED",
    ),
)
