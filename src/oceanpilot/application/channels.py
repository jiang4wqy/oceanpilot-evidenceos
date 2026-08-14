"""Channel-agnostic inbound/outbound seam (design D2 / issue #10 T1).

Decision D2: the chargeback cluster is used primarily *outside* Feishu, with
Feishu as one optional channel. So the core speaks only two normalized shapes:

* ``NormalizedInbound`` — a channel-neutral user action against the chargeback
  flow (open a case / submit evidence / read a case).
* ``Delivery`` — a channel-neutral view of the resulting case step, which each
  channel renders into its own wire format (JSON, a Feishu card, ...).

A ``Channel`` adapter is the only thing that knows a specific wire format: it
parses raw input into a ``NormalizedInbound`` and renders a ``Delivery`` back
out. The application/domain layers never import a channel, so adding or replacing
a channel touches neither. Pure application layer — stdlib + application/domain
only (kept clean by the import-boundary test).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from oceanpilot.application.chargeback_agents import CaseFacts


class InboundKind(StrEnum):
    OPEN_CASE = "OPEN_CASE"
    CONFIRM_REASON = "CONFIRM_REASON"
    SUBMIT_EVIDENCE = "SUBMIT_EVIDENCE"
    FINALIZE_EVIDENCE = "FINALIZE_EVIDENCE"
    GET_CASE = "GET_CASE"


@dataclass(frozen=True)
class NormalizedInbound:
    kind: InboundKind
    channel: str
    case_id: str | None = None
    description: str | None = None
    evidence_code: str | None = None
    # Optional reason correction supplied with a CONFIRM_REASON action; when
    # absent, the human is confirming the reason the kernel proposed.
    reason_code: str | None = None
    actor: str | None = None


@dataclass(frozen=True)
class DeliveryEvidenceItem:
    """One line of the evidence-readiness breakdown, channel-neutral."""

    code: str
    label: str
    weight: int
    critical: bool
    present: bool


@dataclass(frozen=True)
class DeliveryAssessment:
    # Legacy field name retained for API compatibility. In the synthetic
    # prototype it is an evidence-readiness score, not a measured win rate.
    win_likelihood: str
    completeness: str
    responsible_team: str
    requires_human: bool
    review_reasons: tuple[str, ...]
    explanation: str
    # Provenance of the explanation text: MODEL or FALLBACK. The numbers above
    # always come from the deterministic kernel regardless.
    explanation_source: str = "FALLBACK"
    evidence_breakdown: tuple[DeliveryEvidenceItem, ...] = ()


@dataclass(frozen=True)
class DeliveryDeadline:
    """Channel-neutral view of the evidence-window SLA."""

    phase: str
    days_remaining: int | None
    deadline_at: str | None
    overdue: bool


@dataclass(frozen=True)
class AgentActivity:
    """One line of the agent decision trace: who did what, and its source."""

    agent: str
    action: str
    source: str | None = None


@dataclass(frozen=True)
class Delivery:
    case_id: str
    phase: str
    reason_code: str | None = None
    reason_confirmed: bool = False
    collection_finalized: bool = False
    collected: tuple[str, ...] = ()
    next_evidence: str | None = None
    question: str | None = None
    missing: tuple[str, ...] | None = None
    assessment: DeliveryAssessment | None = None
    deadline: DeliveryDeadline | None = None
    facts: CaseFacts | None = None
    agent_trace: tuple[AgentActivity, ...] = ()


@runtime_checkable
class Channel(Protocol):
    name: str

    def parse_inbound(self, raw: Mapping[str, object]) -> NormalizedInbound: ...

    def render(self, delivery: Delivery) -> Mapping[str, object]: ...
