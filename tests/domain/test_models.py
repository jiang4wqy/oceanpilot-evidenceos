import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid1, uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from oceanpilot.domain.enums import (
    AuditActorType,
    AuditEventType,
    CaseCommand,
    CaseStatus,
    CaseType,
    DiagnosisStatus,
    EvidenceAvailability,
    EvidenceCode,
    EvidenceValueType,
    Priority,
    ResponsibleTeam,
    ReviewReason,
    SourceReliability,
    SourceType,
    StopReason,
    TargetRole,
    WriteOutcome,
)
from oceanpilot.domain.errors import SensitiveDataRejected as DefinedSensitiveDataRejected
from oceanpilot.domain.models import (
    ActiveEvidenceSlot,
    ActiveEvidenceView,
    AppendEvidenceResult,
    AuditEvent,
    CaseInputSnapshot,
    CaseView,
    CommandResult,
    CommitDiagnosisResult,
    ConfidenceResult,
    DiagnosisDraft,
    DiagnosisSnapshot,
    DiagnosisView,
    DomainModel,
    EvidenceCreate,
    EvidenceItem,
    EvidenceOrigin,
    FrozenDomainModel,
    Hypothesis,
    HypothesisDraft,
    MerchantSuccessCase,
    ReadinessAssessment,
    Revision,
    RoutingDecision,
    TicketDraft,
    normalize_uuid4,
)


def test_uuid4_is_normalized_and_uuid1_is_rejected() -> None:
    value = str(uuid4()).upper()
    assert normalize_uuid4(value) == value.lower()
    with pytest.raises(ValueError):
        normalize_uuid4(str(uuid1()))


def test_domain_model_configs_are_safe() -> None:
    assert DomainModel.model_config["extra"] == "forbid"
    assert DomainModel.model_config["allow_inf_nan"] is False
    assert DomainModel.model_config["hide_input_in_errors"] is True
    assert FrozenDomainModel.model_config["frozen"] is True


@pytest.mark.parametrize("value", [True, -1, "1"])
def test_revision_is_a_strict_non_negative_integer(value: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Revision).validate_python(value)


def test_evidence_create_rejects_unknown_field_and_naive_time() -> None:
    with pytest.raises(ValidationError):
        EvidenceCreate.model_validate({
            "evidence_id": str(uuid4()),
            "evidence_code": EvidenceCode.TRANSACTION_OCCURRED_AT,
            "availability": EvidenceAvailability.AVAILABLE,
            "typed_value": "2026-07-18T12:00:00",
            "observed_at": datetime(2026, 7, 18, 12, 0),
            "source_ref": "demo",
            "unexpected": True,
        })


def test_naive_observed_time_is_rejected_without_other_errors() -> None:
    with pytest.raises(ValidationError):
        EvidenceCreate.model_validate({
            "evidence_id": str(uuid4()),
            "evidence_code": EvidenceCode.CONTEXT_ENVIRONMENT,
            "availability": EvidenceAvailability.AVAILABLE,
            "typed_value": "PROD",
            "observed_at": "2026-07-18T12:00:00",
            "source_ref": "demo",
        })


def test_uuid_field_does_not_coerce_boolean() -> None:
    with pytest.raises(ValidationError):
        EvidenceCreate.model_validate({
            "evidence_id": True,
            "evidence_code": EvidenceCode.CONTEXT_ENVIRONMENT,
            "availability": EvidenceAvailability.AVAILABLE,
            "typed_value": "PROD",
            "source_ref": "demo",
        })


def test_validation_error_text_hides_rejected_input() -> None:
    sentinel = "Bearer secret-demo-token"
    with pytest.raises(ValidationError) as caught:
        EvidenceCreate.model_validate({
            "evidence_id": sentinel,
            "evidence_code": EvidenceCode.CONTEXT_ENVIRONMENT,
            "availability": EvidenceAvailability.AVAILABLE,
            "typed_value": "PROD",
            "source_ref": "demo",
        })
    assert sentinel not in str(caught.value)


def test_aware_domain_time_is_accepted() -> None:
    model = EvidenceCreate.model_validate({
        "evidence_id": str(uuid4()),
        "evidence_code": EvidenceCode.CONTEXT_ENVIRONMENT,
        "availability": EvidenceAvailability.AVAILABLE,
        "typed_value": "PROD",
        "observed_at": datetime.fromisoformat("2026-07-18T12:00:00+08:00"),
        "source_ref": "demo",
    })
    assert model.observed_at is not None
    assert model.observed_at.utcoffset() is not None


def test_json_domain_time_requires_timezone() -> None:
    payload = {
        "evidence_id": str(uuid4()),
        "evidence_code": EvidenceCode.CONTEXT_ENVIRONMENT,
        "availability": EvidenceAvailability.AVAILABLE,
        "typed_value": "PROD",
        "observed_at": "2026-07-18T12:00:00+08:00",
        "source_ref": "demo",
    }
    model = EvidenceCreate.model_validate_json(json.dumps(payload))
    assert model.observed_at is not None
    assert model.observed_at.utcoffset() is not None

    payload["observed_at"] = "2026-07-18T12:00:00"
    with pytest.raises(ValidationError):
        EvidenceCreate.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("value", [1, False, "true"])
def test_synthetic_true_rejects_bool_coercion(value: object) -> None:
    with pytest.raises(ValidationError):
        EvidenceOrigin(
            source_type=SourceType.SYNTHETIC_ADAPTER,
            source_reliability=SourceReliability.SYNTHETIC_TEST,
            synthetic=value,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_confidence_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValidationError):
        ConfidenceResult(
            raw_score=value,
            display_score=Decimal("0.50"),
            review_reasons=frozenset(),
        )


def test_evidence_item_is_frozen(valid_evidence_item: EvidenceItem) -> None:
    with pytest.raises(ValidationError):
        valid_evidence_item.typed_value = "changed"


ENUM_CONTRACTS: tuple[tuple[type[StrEnum], dict[str, str]], ...] = (
    (CaseType, {
        "PAYMENT_INCIDENT": "PAYMENT_INCIDENT",
        "ONBOARDING_RECOMMENDATION": "ONBOARDING_RECOMMENDATION",
    }),
    (CaseStatus, {
        "NEW": "NEW",
        "NEED_INFO": "NEED_INFO",
        "EVIDENCE_READY": "EVIDENCE_READY",
        "DIAGNOSED": "DIAGNOSED",
        "HUMAN_REVIEW": "HUMAN_REVIEW",
    }),
    (CaseCommand, {
        "CREATE_CASE": "CREATE_CASE",
        "ADD_EVIDENCE": "ADD_EVIDENCE",
        "DIAGNOSE": "DIAGNOSE",
    }),
    (EvidenceAvailability, {
        "AVAILABLE": "AVAILABLE",
        "CONFIRMED_UNAVAILABLE": "CONFIRMED_UNAVAILABLE",
    }),
    (EvidenceValueType, {
        "STRING": "STRING",
        "BOOLEAN": "BOOLEAN",
        "DATETIME": "DATETIME",
        "COUNTRY": "COUNTRY",
        "CURRENCY": "CURRENCY",
    }),
    (SourceType, {
        "MERCHANT": "MERCHANT",
        "INTERNAL_OPERATOR": "INTERNAL_OPERATOR",
        "SYSTEM_OF_RECORD": "SYSTEM_OF_RECORD",
        "SYNTHETIC_ADAPTER": "SYNTHETIC_ADAPTER",
    }),
    (SourceReliability, {
        "SYSTEM_OF_RECORD": "SYSTEM_OF_RECORD",
        "VERIFIED_DOCUMENT": "VERIFIED_DOCUMENT",
        "SYNTHETIC_TEST": "SYNTHETIC_TEST",
        "OPERATOR_CONFIRMED": "OPERATOR_CONFIRMED",
        "USER_REPORTED": "USER_REPORTED",
    }),
    (StopReason, {
        "READY": "READY",
        "NEED_MORE_EVIDENCE": "NEED_MORE_EVIDENCE",
        "CONFIRMED_UNKNOWN": "CONFIRMED_UNKNOWN",
        "UNSUPPORTED": "UNSUPPORTED",
        "SECURITY_BLOCKED": "SECURITY_BLOCKED",
    }),
    (TargetRole, {
        "MERCHANT_BUSINESS": "MERCHANT_BUSINESS",
        "MERCHANT_TECH": "MERCHANT_TECH",
        "INTERNAL_OPS": "INTERNAL_OPS",
        "INTERNAL_RISK": "INTERNAL_RISK",
        "INTERNAL_FINANCE": "INTERNAL_FINANCE",
    }),
    (ReviewReason, {
        "LOW_CONFIDENCE": "LOW_CONFIDENCE",
        "CONFLICTING_EVIDENCE": "CONFLICTING_EVIDENCE",
        "RISK_DECISION": "RISK_DECISION",
        "SECURITY_SIGNAL": "SECURITY_SIGNAL",
        "FINANCIAL_ACTION": "FINANCIAL_ACTION",
        "POLICY_GAP": "POLICY_GAP",
        "INSUFFICIENT_SOURCE_QUALITY": "INSUFFICIENT_SOURCE_QUALITY",
    }),
    (ResponsibleTeam, {
        "BUSINESS": "BUSINESS",
        "TECHNICAL_SUPPORT": "TECHNICAL_SUPPORT",
        "RISK": "RISK",
        "FINANCE": "FINANCE",
        "CUSTOMER_SUPPORT": "CUSTOMER_SUPPORT",
        "PSP_SUPPORT": "PSP_SUPPORT",
    }),
    (Priority, {"LOW": "LOW", "MEDIUM": "MEDIUM", "HIGH": "HIGH"}),
    (DiagnosisStatus, {"CURRENT": "CURRENT", "SUPERSEDED": "SUPERSEDED"}),
    (WriteOutcome, {"CREATED": "CREATED", "REPLAY": "REPLAY"}),
    (AuditEventType, {
        "CASE_CREATED": "CASE_CREATED",
        "EVIDENCE_ADDED": "EVIDENCE_ADDED",
        "DIAGNOSIS_SUPERSEDED": "DIAGNOSIS_SUPERSEDED",
        "DIAGNOSIS_CREATED": "DIAGNOSIS_CREATED",
        "ROUTING_PROPOSED": "ROUTING_PROPOSED",
        "STATE_TRANSITIONED": "STATE_TRANSITIONED",
    }),
    (AuditActorType, {
        "MERCHANT": "MERCHANT",
        "INTERNAL_SYSTEM": "INTERNAL_SYSTEM",
        "SYNTHETIC_ADAPTER": "SYNTHETIC_ADAPTER",
    }),
)


@pytest.mark.parametrize(("enum_type", "expected"), ENUM_CONTRACTS)
def test_closed_enum_contract(enum_type: type[StrEnum], expected: dict[str, str]) -> None:
    assert {member.name: member.value for member in enum_type} == expected
    assert set(enum_type.__members__) == set(expected)


def test_evidence_code_contract_is_exact() -> None:
    assert {member.name: member.value for member in EvidenceCode} == {
        "CONTEXT_ENVIRONMENT": "context.environment",
        "TRANSACTION_REFERENCE": "transaction.reference",
        "TRANSACTION_OCCURRED_AT": "transaction.occurred_at",
        "TRANSACTION_COUNTRY": "transaction.country",
        "TRANSACTION_CURRENCY": "transaction.currency",
        "PAYMENT_METHOD": "payment.method",
        "INTEGRATION_TYPE": "integration.type",
        "INTEGRATION_PLATFORM": "integration.platform",
        "INTEGRATION_PLUGIN_VERSION": "integration.plugin_version",
        "SYMPTOM_STATUS": "symptom.status",
        "SYMPTOM_ERROR_CODE": "symptom.error_code",
        "AUTHENTICATION_STATUS": "authentication.status",
        "AUTHENTICATION_RESULT_CODE": "authentication.result_code",
        "CALLBACK_DELIVERY_STATUS": "callback.delivery_status",
        "RISK_DECISION_CODE": "risk.decision_code",
        "CONFIGURATION_CHECK_RESULT": "configuration.check_result",
    }


MODEL_FIELD_CONTRACTS = (
    (MerchantSuccessCase, (
        "case_id", "case_type", "status", "schema_version", "case_revision",
        "evidence_revision", "synthetic", "summary", "merchant_ref", "created_at",
        "updated_at", "current_diagnosis_id", "readiness",
    )),
    (EvidenceItem, (
        "case_id", "evidence_id", "schema_version", "evidence_code", "availability",
        "value_type", "typed_value", "source_type", "source_ref", "source_reliability",
        "observed_at", "collected_at", "synthetic", "content_hash",
    )),
    (ActiveEvidenceSlot, (
        "evidence_code", "selected_evidence", "known_unknown", "conflicting",
    )),
    (ActiveEvidenceView, ("slots", "review_reasons")),
    (ReadinessAssessment, (
        "ready", "missing_fields", "known_unknown_fields", "next_question",
        "question_reason", "target_role", "completion_ratio", "stop_reason",
    )),
    (HypothesisDraft, (
        "cause_code", "explanation", "evidence_refs", "confidence_score",
        "confidence_method", "next_verification_action", "rule_id",
    )),
    (DiagnosisDraft, (
        "hypotheses", "routing_decision", "ticket_draft", "requires_human",
        "review_reasons",
    )),
    (Hypothesis, (
        "hypothesis_id", "cause_code", "explanation", "evidence_refs",
        "confidence_score", "confidence_method", "next_verification_action", "rule_id",
    )),
    (DiagnosisSnapshot, (
        "diagnosis_id", "case_id", "evidence_revision", "policy_version",
        "engine_version", "status", "hypotheses", "routing_decision", "ticket_draft",
        "requires_human", "review_reasons", "synthetic", "created_at",
    )),
    (RoutingDecision, (
        "responsible_team", "priority", "reason", "evidence_refs", "requires_human",
        "review_reasons",
    )),
    (TicketDraft, (
        "title", "summary", "evidence_summary", "missing_material", "hypotheses",
        "next_action", "responsible_team", "synthetic",
    )),
    (AuditEvent, (
        "event_id", "event_type", "event_version", "case_id", "request_id", "trace_id",
        "actor_type", "action", "from_status", "to_status", "case_revision",
        "evidence_revision", "occurred_at", "result", "reason_code",
        "sanitized_metadata", "synthetic",
    )),
    (CaseInputSnapshot, ("case", "evidence", "current_diagnosis")),
    (CaseView, ("case", "evidence", "current_diagnosis")),
    (DiagnosisView, (
        "case_id", "case_status", "case_revision", "evidence_revision", "diagnosis",
    )),
    (CommandResult, ("outcome", "value")),
    (AppendEvidenceResult, ("outcome", "case_view")),
    (CommitDiagnosisResult, ("outcome", "case_view", "diagnosis")),
)


@pytest.mark.parametrize(("model", "expected_fields"), MODEL_FIELD_CONTRACTS)
def test_model_field_contract_is_exact(model: type, expected_fields: tuple[str, ...]) -> None:
    assert tuple(model.model_fields) == expected_fields


OPTIONAL_DEFAULTS = (
    (EvidenceCreate, "typed_value"),
    (EvidenceCreate, "observed_at"),
    (MerchantSuccessCase, "current_diagnosis_id"),
    (EvidenceItem, "typed_value"),
    (EvidenceItem, "observed_at"),
    (ActiveEvidenceSlot, "selected_evidence"),
    (ReadinessAssessment, "next_question"),
    (ReadinessAssessment, "question_reason"),
    (ReadinessAssessment, "target_role"),
    (DiagnosisDraft, "routing_decision"),
    (DiagnosisDraft, "ticket_draft"),
    (DiagnosisSnapshot, "routing_decision"),
    (DiagnosisSnapshot, "ticket_draft"),
    (AuditEvent, "from_status"),
    (AuditEvent, "to_status"),
    (AuditEvent, "reason_code"),
    (CaseInputSnapshot, "current_diagnosis"),
    (CaseView, "current_diagnosis"),
)


@pytest.mark.parametrize(("model", "field_name"), OPTIONAL_DEFAULTS)
def test_optional_fields_are_omittable_with_none_default(model: type, field_name: str) -> None:
    field = model.model_fields[field_name]
    assert field.default is None
    assert field.is_required() is False


@pytest.mark.parametrize("value", [Decimal("-0.01"), Decimal("1.01")])
def test_confidence_is_bounded(value: Decimal) -> None:
    with pytest.raises(ValidationError):
        ConfidenceResult(
            raw_score=value,
            display_score=Decimal("0.50"),
            review_reasons=frozenset(),
        )


def test_evidence_schema_forbids_additional_properties() -> None:
    assert EvidenceItem.model_json_schema()["additionalProperties"] is False


def test_audit_metadata_is_copied_from_caller_input() -> None:
    metadata = {"source": {"kind": "synthetic"}}
    event = AuditEvent(
        event_id="00000000-0000-4000-8000-000000000020",
        event_type=AuditEventType.CASE_CREATED,
        event_version="1",
        case_id="00000000-0000-4000-8000-000000000010",
        request_id="00000000-0000-4000-8000-000000000021",
        trace_id="00000000-0000-4000-8000-000000000022",
        actor_type=AuditActorType.INTERNAL_SYSTEM,
        action="create case",
        case_revision=1,
        evidence_revision=0,
        occurred_at=datetime.fromisoformat("2026-07-18T12:00:00+08:00"),
        result="created",
        sanitized_metadata=metadata,
        synthetic=True,
    )

    metadata["source"]["kind"] = "changed"

    assert event.sanitized_metadata == {"source": {"kind": "synthetic"}}


def test_sensitive_error_is_defined_in_errors_module() -> None:
    from oceanpilot.domain.security import SensitiveDataRejected

    assert SensitiveDataRejected is DefinedSensitiveDataRejected
