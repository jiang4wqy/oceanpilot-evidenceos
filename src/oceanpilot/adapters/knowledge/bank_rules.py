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

# Synthetic per-bank / per-network overrides (illustrative).
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
