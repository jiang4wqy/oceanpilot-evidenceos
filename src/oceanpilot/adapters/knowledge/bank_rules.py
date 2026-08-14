"""In-memory bank-rule store with synthetic entries.

Resolves most-specific to least: (bank, network, reason) -> (network, reason) ->
a default derived from the deterministic kernel's checklist. Synthetic data only;
swap in a RAG-backed store over the company's real rules behind the same
``KnowledgeBase`` protocol.
"""

from collections.abc import Sequence

from oceanpilot.application.knowledge_base import BankRuleEntry
from oceanpilot.domain.chargeback import (
    ChargebackEvidenceCode as _C,
)
from oceanpilot.domain.chargeback import (
    DisputeReasonCode as _R,
)
from oceanpilot.domain.chargeback import (
    required_evidence_for,
)

_DEFAULT_WINDOW_DAYS = 15

# Synthetic per-bank override (illustrative).
_BANK_ENTRIES: dict[tuple[str, str, _R], BankRuleEntry] = {
    ("ACME_BANK", "VISA", _R.PRODUCT_NOT_RECEIVED): BankRuleEntry(
        reason_code=_R.PRODUCT_NOT_RECEIVED,
        required_evidence=(
            _C.PROOF_OF_DELIVERY,
            _C.DELIVERY_TRACKING,
            _C.SHIPPING_ADDRESS_MATCH,
            _C.TRANSACTION_RECEIPT,
        ),
        template_order=(
            _C.PROOF_OF_DELIVERY,
            _C.DELIVERY_TRACKING,
            _C.SHIPPING_ADDRESS_MATCH,
            _C.TRANSACTION_RECEIPT,
        ),
        submission_window_days=12,
        notes="ACME 要求签收证明列在最前，窗口更紧（12 天）。",
        source="bank",
    ),
}

_NETWORK_ENTRIES: dict[tuple[str, _R], BankRuleEntry] = {
    ("VISA", _R.PRODUCT_NOT_RECEIVED): BankRuleEntry(
        reason_code=_R.PRODUCT_NOT_RECEIVED,
        required_evidence=(
            _C.TRANSACTION_RECEIPT,
            _C.DELIVERY_TRACKING,
            _C.PROOF_OF_DELIVERY,
            _C.SHIPPING_ADDRESS_MATCH,
            _C.CUSTOMER_COMMUNICATION,
        ),
        template_order=(
            _C.TRANSACTION_RECEIPT,
            _C.DELIVERY_TRACKING,
            _C.SHIPPING_ADDRESS_MATCH,
            _C.PROOF_OF_DELIVERY,
            _C.CUSTOMER_COMMUNICATION,
        ),
        submission_window_days=_DEFAULT_WINDOW_DAYS,
        notes="Visa 13.1 演示规则：证明商品/服务按约定时间和地点交付。",
        source="network-guidance",
        scheme_reason_code="13.1",
        rule_version="June 2024",
        source_document="Dispute Management Guidelines for Visa Merchants",
        source_section="Condition 13.1 — Merchandise/Services Not Received",
        required_assertions=(
            "商品或服务已经交付",
            "在约定日期前交付或可供取用",
            "交付至约定地点并与争议交易关联",
        ),
        limitation="商户指南演示规则；15 天为本原型内部窗口，不是 Visa 官方申诉期限。",
    ),
    ("VISA", _R.FRAUD_CARD_NOT_PRESENT): BankRuleEntry(
        reason_code=_R.FRAUD_CARD_NOT_PRESENT,
        required_evidence=(
            _C.TRANSACTION_RECEIPT,
            _C.THREEDS_AUTHENTICATION,
            _C.DEVICE_OR_IP_MATCH,
            _C.PRIOR_TRANSACTION_HISTORY,
        ),
        template_order=(
            _C.THREEDS_AUTHENTICATION,
            _C.DEVICE_OR_IP_MATCH,
            _C.PRIOR_TRANSACTION_HISTORY,
            _C.TRANSACTION_RECEIPT,
        ),
        submission_window_days=_DEFAULT_WINDOW_DAYS,
        notes="Visa 10.4 演示规则：检查认证及历史交易关联，不自动声称 CE3.0 资格。",
        source="network-guidance",
        scheme_reason_code="10.4",
        rule_version="June 2024",
        source_document="Dispute Management Guidelines for Visa Merchants",
        source_section="Condition 10.4 — Other Fraud, Card-Absent Environment",
        required_assertions=(
            "持卡人参与交易或从交易中受益",
            "认证、设备或网络信息能够关联争议交易",
            "历史无争议交易满足适用的关联条件",
        ),
        limitation="商户指南演示规则；不自动判定 CE3.0 或责任转移资格。",
    ),
    ("MASTERCARD", _R.PRODUCT_NOT_AS_DESCRIBED): BankRuleEntry(
        reason_code=_R.PRODUCT_NOT_AS_DESCRIBED,
        required_evidence=(
            _C.TRANSACTION_RECEIPT,
            _C.PRODUCT_DESCRIPTION,
            _C.CUSTOMER_COMMUNICATION,
            _C.TERMS_AND_REFUND_POLICY,
            _C.PROOF_OF_DELIVERY,
        ),
        template_order=(
            _C.TRANSACTION_RECEIPT,
            _C.PRODUCT_DESCRIPTION,
            _C.PROOF_OF_DELIVERY,
            _C.CUSTOMER_COMMUNICATION,
            _C.TERMS_AND_REFUND_POLICY,
        ),
        submission_window_days=_DEFAULT_WINDOW_DAYS,
        notes="Mastercard 4853 演示规则：逐项回应不符或缺陷主张，并保留首次提交材料。",
        source="network-guidance",
        scheme_reason_code="4853",
        rule_version="19 May 2026",
        source_document="Chargeback Guide — Merchant Edition",
        source_section="Cardholder Dispute Chargeback — Goods or Services Not as Described",
        required_assertions=(
            "商品或服务符合交易时的描述或合同",
            "履约、维修、替换或交付记录能够对应争议交易",
            "商户材料逐项回应持卡人的具体主张",
        ),
        limitation="合成演示配置；适用地区、消息系统、阶段及时限仍需生产规则确认。",
    ),
    ("VISA", _R.CREDIT_NOT_PROCESSED): BankRuleEntry(
        reason_code=_R.CREDIT_NOT_PROCESSED,
        required_evidence=(
            _C.REFUND_RECORD,
            _C.TRANSACTION_RECEIPT,
            _C.TERMS_AND_REFUND_POLICY,
        ),
        template_order=(
            _C.REFUND_RECORD,
            _C.TRANSACTION_RECEIPT,
            _C.TERMS_AND_REFUND_POLICY,
        ),
        submission_window_days=14,
        notes="VISA 通用：退款凭证优先。",
        source="network",
    ),
}


class InMemoryBankRules:
    def __init__(
        self,
        bank_entries: dict[tuple[str, str, _R], BankRuleEntry] | None = None,
        network_entries: dict[tuple[str, _R], BankRuleEntry] | None = None,
    ) -> None:
        self._bank = dict(_BANK_ENTRIES if bank_entries is None else bank_entries)
        self._network = dict(_NETWORK_ENTRIES if network_entries is None else network_entries)

    def lookup(
        self,
        reason_code: _R,
        *,
        bank_id: str | None = None,
        card_network: str | None = None,
    ) -> BankRuleEntry:
        if bank_id and card_network:
            entry = self._bank.get((bank_id, card_network, reason_code))
            if entry is not None:
                return entry
        if card_network:
            entry = self._network.get((card_network, reason_code))
            if entry is not None:
                return entry
        return self._default(reason_code)

    @staticmethod
    def _default(reason_code: _R) -> BankRuleEntry:
        required: Sequence[_C] = required_evidence_for(reason_code)
        return BankRuleEntry(
            reason_code=reason_code,
            required_evidence=tuple(required),
            template_order=tuple(required),
            submission_window_days=_DEFAULT_WINDOW_DAYS,
            notes="默认模板（未匹配到银行/卡组织专属规则）。",
            source="default",
        )
