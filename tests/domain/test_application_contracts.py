from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from inspect import Parameter, signature
from typing import get_type_hints

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticUndefined

import oceanpilot.application.commands as commands_module
import oceanpilot.application.errors as errors_module
import oceanpilot.application.ports as ports_module
from oceanpilot.adapters.diagnosis.rules import RuleDiagnosisEngine
from oceanpilot.application.commands import (
    AddEvidenceCommand,
    CreateCaseCommand,
    DiagnoseCaseCommand,
)
from oceanpilot.application.errors import (
    ApplicationError,
    CaseNotFound,
    CaseNotReady,
    CaseTypeNotEnabled,
    ConcurrentCaseWrite,
    DatabaseUnavailable,
    DiagnosisInputStale,
    EvidenceConflict,
    PersistenceInvariantViolation,
)
from oceanpilot.application.ports import CaseStoreFactory, CaseStoreSession
from oceanpilot.domain.diagnosis import DiagnosisEngine
from oceanpilot.domain.enums import (
    CaseStatus,
    CaseType,
    EvidenceAvailability,
    EvidenceCode,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.models import (
    AppendEvidenceResult,
    AuditEvent,
    CaseInputSnapshot,
    CaseView,
    CommitDiagnosisResult,
    DiagnosisSnapshot,
    EvidenceCreate,
    EvidenceItem,
    EvidenceOrigin,
    FrozenDomainModel,
    MerchantSuccessCase,
    ReadinessAssessment,
    Revision,
    SyntheticTrue,
    UUID4Str,
)

CASE_ID = "00000000-0000-4000-8000-000000000010"
EVIDENCE_ID = "00000000-0000-4000-8000-000000000011"
REQUEST_ID = "00000000-0000-4000-8000-000000000012"
TRACE_ID = "00000000-0000-4000-8000-000000000013"


def valid_create_payload() -> dict[str, object]:
    return {
        "case_type": CaseType.PAYMENT_INCIDENT,
        "summary": "Synthetic payment incident",
        "merchant_ref": "merchant:demo",
        "synthetic": True,
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
    }


def valid_evidence_payload() -> dict[str, object]:
    return {
        "evidence_id": EVIDENCE_ID,
        "evidence_code": EvidenceCode.CONTEXT_ENVIRONMENT,
        "availability": EvidenceAvailability.AVAILABLE,
        "typed_value": "PROD",
        "observed_at": datetime.fromisoformat("2026-07-18T12:00:00+08:00"),
        "source_ref": "synthetic:fixture",
    }


def valid_origin_payload() -> dict[str, object]:
    return {
        "source_type": SourceType.SYNTHETIC_ADAPTER,
        "source_reliability": SourceReliability.SYNTHETIC_TEST,
        "synthetic": True,
    }


def test_command_field_sets_and_order_are_exact() -> None:
    assert tuple(CreateCaseCommand.model_fields) == (
        "case_id",
        "case_type",
        "summary",
        "merchant_ref",
        "synthetic",
        "request_id",
        "trace_id",
    )
    assert tuple(AddEvidenceCommand.model_fields) == (
        "case_id",
        "evidence",
        "origin",
        "request_id",
        "trace_id",
    )
    assert tuple(DiagnoseCaseCommand.model_fields) == (
        "case_id",
        "request_id",
        "trace_id",
    )


@pytest.mark.parametrize(
    ("command_type", "field_names"),
    (
        (
            AddEvidenceCommand,
            ("case_id", "evidence", "origin", "request_id", "trace_id"),
        ),
        (DiagnoseCaseCommand, ("case_id", "request_id", "trace_id")),
    ),
)
def test_command_fields_are_required_and_constructor_is_keyword_only(
    command_type: type,
    field_names: tuple[str, ...],
) -> None:
    assert tuple(command_type.model_fields) == field_names
    assert all(field.is_required() for field in command_type.model_fields.values())
    assert all(
        field.default is PydanticUndefined
        for field in command_type.model_fields.values()
    )

    parameters = signature(command_type).parameters
    assert tuple(parameters) == field_names
    assert all(parameter.kind is Parameter.KEYWORD_ONLY for parameter in parameters.values())
    assert all(parameter.default is Parameter.empty for parameter in parameters.values())


def test_create_case_command_has_one_optional_internal_case_id() -> None:
    field_names = (
        "case_id",
        "case_type",
        "summary",
        "merchant_ref",
        "synthetic",
        "request_id",
        "trace_id",
    )
    assert tuple(CreateCaseCommand.model_fields) == field_names
    assert CreateCaseCommand.model_fields["case_id"].is_required() is False
    assert CreateCaseCommand.model_fields["case_id"].default is None
    assert all(
        CreateCaseCommand.model_fields[name].is_required()
        for name in field_names
        if name != "case_id"
    )

    parameters = signature(CreateCaseCommand).parameters
    assert tuple(parameters) == field_names
    assert all(parameter.kind is Parameter.KEYWORD_ONLY for parameter in parameters.values())
    assert parameters["case_id"].default is None
    assert all(
        parameters[name].default is Parameter.empty
        for name in field_names
        if name != "case_id"
    )


def test_command_annotations_reuse_the_frozen_domain_types() -> None:
    create_hints = get_type_hints(CreateCaseCommand, include_extras=True)
    add_hints = get_type_hints(AddEvidenceCommand, include_extras=True)
    diagnose_hints = get_type_hints(DiagnoseCaseCommand, include_extras=True)

    assert create_hints["case_id"] == UUID4Str | None
    assert create_hints["case_type"] is CaseType
    assert create_hints["synthetic"] == SyntheticTrue
    assert create_hints["request_id"] == UUID4Str
    assert create_hints["trace_id"] == UUID4Str
    assert add_hints == {
        "case_id": UUID4Str,
        "evidence": EvidenceCreate,
        "origin": EvidenceOrigin,
        "request_id": UUID4Str,
        "trace_id": UUID4Str,
    }
    assert diagnose_hints == {
        "case_id": UUID4Str,
        "request_id": UUID4Str,
        "trace_id": UUID4Str,
    }


@pytest.mark.parametrize(
    "command_type",
    (CreateCaseCommand, AddEvidenceCommand, DiagnoseCaseCommand),
)
def test_commands_inherit_the_safe_frozen_model_contract(command_type: type) -> None:
    assert issubclass(command_type, FrozenDomainModel)
    assert command_type.model_config["frozen"] is True
    assert command_type.model_config["extra"] == "forbid"


def test_create_case_constraints_are_strict_and_frozen() -> None:
    command = CreateCaseCommand.model_validate(valid_create_payload())
    assert command.summary == "Synthetic payment incident"

    with pytest.raises(ValidationError):
        command.summary = "changed"
    for field, value in (
        ("summary", ""),
        ("summary", "x" * 501),
        ("summary", 123),
        ("merchant_ref", ""),
        ("merchant_ref", "x" * 129),
        ("merchant_ref", 123),
        ("synthetic", False),
    ):
        payload = valid_create_payload()
        payload[field] = value
        with pytest.raises(ValidationError):
            CreateCaseCommand.model_validate(payload)

    payload = valid_create_payload()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        CreateCaseCommand.model_validate(payload)


def test_add_evidence_copies_nested_dicts_and_freezes_nested_values() -> None:
    evidence_input = valid_evidence_payload()
    origin_input = valid_origin_payload()
    payload = {
        "case_id": CASE_ID,
        "evidence": evidence_input,
        "origin": origin_input,
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
    }
    command = AddEvidenceCommand.model_validate(payload)

    evidence_input["typed_value"] = "SANDBOX"
    evidence_input["source_ref"] = "changed"
    origin_input["source_reliability"] = SourceReliability.USER_REPORTED
    payload["case_id"] = "00000000-0000-4000-8000-000000000099"

    assert command.case_id == CASE_ID
    assert command.evidence.typed_value == "PROD"
    assert command.evidence.source_ref == "synthetic:fixture"
    assert command.origin.source_reliability is SourceReliability.SYNTHETIC_TEST
    with pytest.raises(ValidationError):
        command.case_id = "00000000-0000-4000-8000-000000000099"
    with pytest.raises(ValidationError):
        command.evidence.typed_value = "SANDBOX"
    with pytest.raises(ValidationError):
        command.origin.source_reliability = SourceReliability.USER_REPORTED


def test_add_evidence_rejects_extra_fields_without_aliasing_model_inputs() -> None:
    evidence = EvidenceCreate.model_validate(valid_evidence_payload())
    origin = EvidenceOrigin.model_validate(valid_origin_payload())
    command = AddEvidenceCommand(
        case_id=CASE_ID,
        evidence=evidence,
        origin=origin,
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
    )
    assert command.evidence is evidence
    assert command.origin is origin
    with pytest.raises(ValidationError):
        AddEvidenceCommand.model_validate({
            "case_id": CASE_ID,
            "evidence": valid_evidence_payload(),
            "origin": valid_origin_payload(),
            "request_id": REQUEST_ID,
            "trace_id": TRACE_ID,
            "unexpected": True,
        })


def test_diagnose_command_is_strict_and_frozen() -> None:
    command = DiagnoseCaseCommand(
        case_id=CASE_ID,
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
    )
    with pytest.raises(ValidationError):
        command.trace_id = "00000000-0000-4000-8000-000000000099"
    with pytest.raises(ValidationError):
        DiagnoseCaseCommand.model_validate({
            "case_id": CASE_ID,
            "request_id": REQUEST_ID,
            "trace_id": TRACE_ID,
            "unexpected": True,
        })


ERROR_MESSAGES = {
    CaseNotFound: "case was not found",
    CaseTypeNotEnabled: "case type is not enabled",
    CaseNotReady: "case is not ready for diagnosis",
    EvidenceConflict: "evidence id conflicts with existing content",
    ConcurrentCaseWrite: "case changed during write",
    DiagnosisInputStale: "diagnosis input is stale",
    DatabaseUnavailable: "database is unavailable",
    PersistenceInvariantViolation: "persistence invariant was violated",
}
ORDINARY_ERRORS = tuple(error for error in ERROR_MESSAGES if error is not CaseNotReady)


def test_application_error_subclass_set_and_messages_are_exact() -> None:
    assert "__init__" in ApplicationError.__dict__
    assert "__str__" in ApplicationError.__dict__
    assert set(ApplicationError.__subclasses__()) == set(ERROR_MESSAGES)
    assert {error.__name__ for error in ERROR_MESSAGES} == {
        "CaseNotFound",
        "CaseTypeNotEnabled",
        "CaseNotReady",
        "EvidenceConflict",
        "ConcurrentCaseWrite",
        "DiagnosisInputStale",
        "DatabaseUnavailable",
        "PersistenceInvariantViolation",
    }
    for error_type, expected_message in ERROR_MESSAGES.items():
        assert error_type.message == expected_message


def test_ordinary_errors_inherit_constructor_and_stringification_unchanged() -> None:
    for error_type in ORDINARY_ERRORS:
        assert "__init__" not in error_type.__dict__
        assert "__str__" not in error_type.__dict__


@pytest.mark.parametrize("error_type", ORDINARY_ERRORS)
def test_ordinary_errors_reject_all_payloads(error_type: type[ApplicationError]) -> None:
    sentinel = "sqlite secret raw-input 00000000-0000-4000-8000-000000000099"
    with pytest.raises(TypeError):
        error_type(sentinel)
    with pytest.raises(TypeError):
        error_type(payload=sentinel)


@pytest.mark.parametrize("error_type", ORDINARY_ERRORS)
def test_ordinary_error_strings_ignore_args_and_instance_message(
    error_type: type[ApplicationError],
) -> None:
    sentinel = "sqlite secret raw-input 00000000-0000-4000-8000-000000000099"
    error = error_type()
    expected = ERROR_MESSAGES[error_type]
    assert str(error) == expected

    error.args = (sentinel,)
    error.message = sentinel
    assert str(error) == expected
    assert sentinel not in str(error)


def test_case_not_ready_signature_and_type_hints_are_exact() -> None:
    parameters = signature(CaseNotReady.__init__).parameters
    assert tuple(parameters) == (
        "self",
        "case_id",
        "missing_fields",
        "current_revision",
    )
    assert parameters["case_id"].kind is Parameter.KEYWORD_ONLY
    assert parameters["missing_fields"].kind is Parameter.KEYWORD_ONLY
    assert parameters["current_revision"].kind is Parameter.KEYWORD_ONLY
    assert all(
        parameter.default is Parameter.empty
        for name, parameter in parameters.items()
        if name != "self"
    )
    hints = get_type_hints(CaseNotReady.__init__, include_extras=True)
    assert hints == {
        "case_id": UUID4Str,
        "missing_fields": Sequence[str],
        "current_revision": Revision,
        "return": type(None),
    }


def test_case_not_ready_copies_fields_and_exposes_read_only_properties() -> None:
    missing = ["transaction.reference", "symptom.signal"]
    error = CaseNotReady(
        case_id=CASE_ID,
        missing_fields=missing,
        current_revision=7,
    )
    missing.append("context.environment")

    assert error.case_id == CASE_ID
    assert error.missing_fields == ("transaction.reference", "symptom.signal")
    assert error.current_revision == 7
    assert all(
        isinstance(CaseNotReady.__dict__[name], property)
        and CaseNotReady.__dict__[name].fset is None
        for name in ("case_id", "missing_fields", "current_revision")
    )
    for name, value in (
        ("case_id", "00000000-0000-4000-8000-000000000099"),
        ("missing_fields", ("changed",)),
        ("current_revision", 99),
    ):
        with pytest.raises(AttributeError):
            setattr(error, name, value)


def test_case_not_ready_is_keyword_only_and_always_uses_safe_string() -> None:
    sentinel = "sqlite secret raw-input 00000000-0000-4000-8000-000000000099"
    with pytest.raises(TypeError):
        CaseNotReady(CASE_ID, ("symptom.signal",), 7)
    with pytest.raises(TypeError):
        CaseNotReady(
            case_id=CASE_ID,
            missing_fields=("symptom.signal",),
            current_revision=7,
            payload=sentinel,
        )

    error = CaseNotReady(
        case_id=CASE_ID,
        missing_fields=("symptom.signal",),
        current_revision=7,
    )
    error.args = (sentinel,)
    error.message = sentinel
    assert str(error) == "case is not ready for diagnosis"
    assert sentinel not in str(error)


SESSION_METHODS = {
    "healthcheck",
    "get_case_view",
    "load_case_snapshot",
    "create_case_atomic",
    "append_evidence_atomic",
    "find_diagnosis",
    "commit_diagnosis_atomic",
}


def assert_parameters(method: object, expected: tuple[tuple[str, Parameter], ...]) -> None:
    actual = signature(method).parameters
    assert tuple(actual) == tuple(name for name, _ in expected)
    assert tuple(parameter.kind for parameter in actual.values()) == tuple(
        kind for _, kind in expected
    )
    assert all(
        parameter.default is Parameter.empty
        for name, parameter in actual.items()
        if name != "self"
    )


def test_store_session_has_only_the_exact_atomic_contracts() -> None:
    public_names = {name for name in CaseStoreSession.__dict__ if not name.startswith("_")}
    assert public_names == SESSION_METHODS
    assert CaseStoreSession._is_protocol is True
    for forbidden in (
        "save",
        "save_case",
        "update",
        "update_case",
        "update_evidence",
        "delete",
        "delete_case",
        "delete_evidence",
        "connection",
        "raw_connection",
    ):
        assert forbidden not in CaseStoreSession.__dict__


def test_store_session_parameter_order_and_kinds_are_exact() -> None:
    positional = Parameter.POSITIONAL_OR_KEYWORD
    keyword = Parameter.KEYWORD_ONLY
    assert_parameters(CaseStoreSession.healthcheck, (("self", positional),))
    assert_parameters(
        CaseStoreSession.get_case_view,
        (("self", positional), ("case_id", positional)),
    )
    assert_parameters(
        CaseStoreSession.load_case_snapshot,
        (("self", positional), ("case_id", positional)),
    )
    assert_parameters(
        CaseStoreSession.create_case_atomic,
        (("self", positional), ("case", keyword), ("audit", keyword)),
    )
    assert_parameters(
        CaseStoreSession.append_evidence_atomic,
        (
            ("self", positional),
            ("expected_case_revision", keyword),
            ("expected_evidence_revision", keyword),
            ("evidence", keyword),
            ("readiness", keyword),
            ("target_status", keyword),
            ("audit_events", keyword),
        ),
    )
    assert_parameters(
        CaseStoreSession.find_diagnosis,
        (
            ("self", positional),
            ("case_id", keyword),
            ("evidence_revision", keyword),
            ("policy_version", keyword),
        ),
    )
    assert_parameters(
        CaseStoreSession.commit_diagnosis_atomic,
        (
            ("self", positional),
            ("expected_case_revision", keyword),
            ("expected_evidence_revision", keyword),
            ("snapshot", keyword),
            ("target_status", keyword),
            ("audit_events", keyword),
        ),
    )


def test_store_session_annotations_and_returns_are_exact() -> None:
    assert get_type_hints(CaseStoreSession.healthcheck) == {"return": type(None)}
    assert get_type_hints(CaseStoreSession.get_case_view, include_extras=True) == {
        "case_id": UUID4Str,
        "return": CaseView | None,
    }
    assert get_type_hints(CaseStoreSession.load_case_snapshot, include_extras=True) == {
        "case_id": UUID4Str,
        "return": CaseInputSnapshot | None,
    }
    assert get_type_hints(CaseStoreSession.create_case_atomic) == {
        "case": MerchantSuccessCase,
        "audit": AuditEvent,
        "return": CaseView,
    }
    assert get_type_hints(CaseStoreSession.append_evidence_atomic) == {
        "expected_case_revision": int,
        "expected_evidence_revision": int,
        "evidence": EvidenceItem,
        "readiness": ReadinessAssessment,
        "target_status": CaseStatus,
        "audit_events": Sequence[AuditEvent],
        "return": AppendEvidenceResult,
    }
    assert get_type_hints(CaseStoreSession.find_diagnosis, include_extras=True) == {
        "case_id": UUID4Str,
        "evidence_revision": int,
        "policy_version": str,
        "return": DiagnosisSnapshot | None,
    }
    assert get_type_hints(CaseStoreSession.commit_diagnosis_atomic) == {
        "expected_case_revision": int,
        "expected_evidence_revision": int,
        "snapshot": DiagnosisSnapshot,
        "target_status": CaseStatus,
        "audit_events": Sequence[AuditEvent],
        "return": CommitDiagnosisResult,
    }


def test_store_factory_signature_is_exact() -> None:
    assert CaseStoreFactory._is_protocol is True
    contract_names = {
        name
        for name in CaseStoreFactory.__dict__
        if name == "__call__" or not name.startswith("_")
    }
    assert contract_names == {"__call__"}
    assert_parameters(CaseStoreFactory.__call__, (("self", Parameter.POSITIONAL_OR_KEYWORD),))
    assert get_type_hints(CaseStoreFactory.__call__) == {
        "return": AbstractContextManager[CaseStoreSession]
    }


def test_task_five_modules_do_not_define_or_reexport_outer_ports() -> None:
    for module in (commands_module, errors_module, ports_module):
        for forbidden in ("DiagnosisEngine", "EvidenceSource", "SyntheticScenario"):
            assert not hasattr(module, forbidden)
    assert isinstance(RuleDiagnosisEngine(), DiagnosisEngine)
