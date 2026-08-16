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

RULE_CATALOG_DISCLAIMER = (
    "演示规则摘要；生产使用前须按卡组织、地区、版本和生效日期，"
    "以正式 Standards、后台公告及收单机构有效版本复核。"
)


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
    rule_version_id: str | None = None
    verification_status: str | None = None
    submission_window_basis: str | None = "INTERNAL_DEMO"


@runtime_checkable
class KnowledgeBase(Protocol):
    def lookup(
        self,
        reason_code: DisputeReasonCode,
        *,
        bank_id: str | None = None,
        card_network: str | None = None,
    ) -> BankRuleEntry: ...


@dataclass(frozen=True)
class RuleCatalogItem:
    rule_version_id: str
    document_id: str
    scheme: str
    scheme_reason_code: str
    display_name: str
    category: str
    region: str
    version_label: str | None
    demo_role: str
    verification_status: str
    source_document: str
    source_url: str


@dataclass(frozen=True)
class RuleDocument:
    document_id: str
    scheme: str
    title: str
    publisher: str
    source_url: str
    source_version: str | None


@dataclass(frozen=True)
class RuleRequirement:
    requirement_id: str
    requirement_type: str
    necessity: str
    sequence: int
    description_zh: str
    internal_evidence_code: str | None


@dataclass(frozen=True)
class RuleDetail:
    rule_version_id: str
    scheme: str
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
    document: RuleDocument
    assertions: tuple[RuleRequirement, ...]
    evidence: tuple[RuleRequirement, ...]


@runtime_checkable
class RuleCatalog(Protocol):
    def list_rules(
        self,
        *,
        scheme: str | None = None,
        query: str | None = None,
    ) -> tuple[RuleCatalogItem, ...]: ...

    def get_rule(self, rule_version_id: str) -> RuleDetail | None: ...
