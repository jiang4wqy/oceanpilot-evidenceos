from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from oceanpilot.adapters.diagnosis.rules import RuleDiagnosisEngine
from oceanpilot.adapters.evidence.synthetic import (
    SyntheticEvidenceSource,
    SyntheticScenario,
)
from oceanpilot.adapters.persistence.sqlite import (
    SqliteCaseStoreFactory,
    initialize_schema,
)
from oceanpilot.application.case_service import CaseService
from oceanpilot.application.commands import (
    AddEvidenceCommand,
    CreateCaseCommand,
    DiagnoseCaseCommand,
)
from oceanpilot.domain.enums import (
    CaseStatus,
    CaseType,
    DiagnosisStatus,
    EvidenceCode,
    ResponsibleTeam,
    ReviewReason,
    SourceReliability,
    SourceType,
    WriteOutcome,
)

NOW = datetime(2026, 8, 5, 4, 0, tzinfo=UTC)
REQUEST_ID = "00000000-0000-4000-8000-000000000030"
TRACE_ID = "00000000-0000-4000-8000-000000000040"

COMMON_CODES = {
    EvidenceCode.TRANSACTION_REFERENCE,
    EvidenceCode.TRANSACTION_OCCURRED_AT,
    EvidenceCode.CONTEXT_ENVIRONMENT,
    EvidenceCode.SYMPTOM_STATUS,
    EvidenceCode.INTEGRATION_TYPE,
}

EXPECTED = {
    SyntheticScenario.THREEDS_INCOMPLETE: (
        "THREEDS_INCOMPLETE_V1",
        ResponsibleTeam.TECHNICAL_SUPPORT,
        CaseStatus.DIAGNOSED,
        frozenset(),
        {
            EvidenceCode.SYMPTOM_STATUS,
            EvidenceCode.AUTHENTICATION_STATUS,
            EvidenceCode.CALLBACK_DELIVERY_STATUS,
        },
    ),
    SyntheticScenario.RISK_DECLINE: (
        "RISK_DECLINE_V1",
        ResponsibleTeam.RISK,
        CaseStatus.HUMAN_REVIEW,
        frozenset({ReviewReason.RISK_DECISION}),
        {EvidenceCode.SYMPTOM_STATUS, EvidenceCode.RISK_DECISION_CODE},
    ),
    SyntheticScenario.CONFIG_MERCHANT: (
        "CONFIG_MISMATCH_MERCHANT_V1",
        ResponsibleTeam.TECHNICAL_SUPPORT,
        CaseStatus.DIAGNOSED,
        frozenset(),
        {
            EvidenceCode.SYMPTOM_STATUS,
            EvidenceCode.CONTEXT_ENVIRONMENT,
            EvidenceCode.PAYMENT_METHOD,
            EvidenceCode.CONFIGURATION_CHECK_RESULT,
        },
    ),
    SyntheticScenario.CONFIG_PSP: (
        "CONFIG_MISMATCH_PSP_V1",
        ResponsibleTeam.PSP_SUPPORT,
        CaseStatus.DIAGNOSED,
        frozenset(),
        {
            EvidenceCode.SYMPTOM_STATUS,
            EvidenceCode.CONTEXT_ENVIRONMENT,
            EvidenceCode.PAYMENT_METHOD,
            EvidenceCode.CONFIGURATION_CHECK_RESULT,
        },
    ),
}


class _UuidFactory:
    def __init__(self) -> None:
        self._next = 1000

    def __call__(self) -> str:
        value = f"00000000-0000-4000-8000-{self._next:012d}"
        self._next += 1
        return value


def _service(db_path):
    initialize_schema(db_path)
    return CaseService(
        SqliteCaseStoreFactory(db_path),
        RuleDiagnosisEngine(),
        clock=lambda: NOW,
        uuid_factory=_UuidFactory(),
        policy_version="POLICY_V1",
        engine_version="RULES_V1",
    )


def test_source_exposes_only_closed_frozen_synthetic_scenarios():
    assert {item.value for item in SyntheticScenario} == {
        "THREEDS_INCOMPLETE",
        "RISK_DECLINE",
        "CONFIG_MERCHANT",
        "CONFIG_PSP",
    }
    source = SyntheticEvidenceSource()
    assert source.origin.source_type is SourceType.SYNTHETIC_ADAPTER
    assert source.origin.source_reliability is SourceReliability.SYNTHETIC_TEST
    assert source.origin.synthetic is True

    for scenario in SyntheticScenario:
        evidence = source.load(scenario)
        assert isinstance(evidence, tuple)
        assert COMMON_CODES.issubset(item.evidence_code for item in evidence)
        assert len({item.evidence_id for item in evidence}) == len(evidence)
        assert all(item.source_ref.startswith("synthetic:oceanpilot:") for item in evidence)
        with pytest.raises(ValidationError):
            evidence[0].typed_value = "MUTATED"  # type: ignore[misc]


@pytest.mark.parametrize("scenario", tuple(SyntheticScenario))
def test_internal_synthetic_case_runs_to_evidence_cited_diagnosis(tmp_path, scenario):
    source = SyntheticEvidenceSource()
    evidence = source.load(scenario)
    service = _service(tmp_path / f"{scenario.value.lower()}.db")
    created = service.create_case(
        CreateCaseCommand(
            case_type=CaseType.PAYMENT_INCIDENT,
            summary=f"Synthetic {scenario.value} incident",
            merchant_ref=f"merchant_{scenario.value.lower()}",
            synthetic=True,
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
        )
    )
    case_id = created.case.case_id

    for item in evidence:
        appended = service.add_evidence(
            AddEvidenceCommand(
                case_id=case_id,
                evidence=item,
                origin=source.origin,
                request_id=REQUEST_ID,
                trace_id=TRACE_ID,
            )
        )
        assert appended.outcome is WriteOutcome.CREATED

    ready = service.get_case(case_id)
    assert ready.case.status is CaseStatus.EVIDENCE_READY
    assert ready.case.readiness.ready is True
    assert all(item.source_type is SourceType.SYNTHETIC_ADAPTER for item in ready.evidence)
    assert all(
        item.source_reliability is SourceReliability.SYNTHETIC_TEST for item in ready.evidence
    )

    result = service.diagnose(
        DiagnoseCaseCommand(
            case_id=case_id,
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
        )
    )
    expected_rule, team, status, review_reasons, decisive_codes = EXPECTED[scenario]
    diagnosis = result.value.diagnosis
    hypothesis = diagnosis.hypotheses[0]
    decisive_ids = {
        item.evidence_id for item in ready.evidence if item.evidence_code in decisive_codes
    }

    assert result.outcome is WriteOutcome.CREATED
    assert result.value.case_status is status
    assert result.value.case_revision == len(evidence) + 2
    assert result.value.evidence_revision == len(evidence)
    assert diagnosis.status is DiagnosisStatus.CURRENT
    assert diagnosis.synthetic is True
    assert hypothesis.rule_id == expected_rule
    assert hypothesis.confidence_score == Decimal("0.94")
    assert set(hypothesis.evidence_refs) == decisive_ids
    assert diagnosis.review_reasons == review_reasons
    assert diagnosis.requires_human is bool(review_reasons)
    assert diagnosis.routing_decision is not None
    assert diagnosis.routing_decision.responsible_team is team
    assert set(diagnosis.routing_decision.evidence_refs) == decisive_ids
    assert diagnosis.routing_decision.review_reasons == review_reasons
    assert diagnosis.ticket_draft is not None
    assert diagnosis.ticket_draft.synthetic is True
    assert diagnosis.ticket_draft.responsible_team is team
    assert diagnosis.ticket_draft.hypotheses[0].rule_id == expected_rule

    persisted = service.get_case(case_id)
    assert persisted.case.current_diagnosis_id == diagnosis.diagnosis_id
    assert persisted.current_diagnosis == diagnosis
    replay = service.diagnose(
        DiagnoseCaseCommand(
            case_id=case_id,
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
        )
    )
    assert replay.outcome is WriteOutcome.REPLAY
    assert replay.value.case_revision == result.value.case_revision
    assert replay.value.diagnosis == diagnosis
