"""Bank-rule knowledge base seam.

Different issuing banks / card networks require different evidence, in different
order, within different windows. The Packager agent looks rules up through this
``KnowledgeBase`` protocol; concrete stores (in-memory synthetic now, RAG /
company data later) live in the adapter layer. Entries are shaped so the
company's real per-bank templates drop in without changing callers.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode


@dataclass(frozen=True)
class BankRuleEntry:
    reason_code: DisputeReasonCode
    required_evidence: tuple[ChargebackEvidenceCode, ...]
    template_order: tuple[ChargebackEvidenceCode, ...]
    submission_window_days: int
    notes: str
    source: str  # "bank" | "network" | "default"
    scheme_reason_code: str | None = None
    rule_version: str | None = None
    source_document: str | None = None
    source_section: str | None = None
    required_assertions: tuple[str, ...] = ()
    limitation: str | None = None


@runtime_checkable
class KnowledgeBase(Protocol):
    def lookup(
        self,
        reason_code: DisputeReasonCode,
        *,
        bank_id: str | None = None,
        card_network: str | None = None,
    ) -> BankRuleEntry: ...
