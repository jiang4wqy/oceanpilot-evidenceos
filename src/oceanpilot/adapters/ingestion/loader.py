"""Loaders from redacted import records to the kernel tables / knowledge base.

Turns validated ``schema`` records (parsed JSON) into the structures callers
already consume — most importantly an ``InMemoryBankRules`` behind the existing
``KnowledgeBase`` protocol, so when the company's real (redacted) data arrives it
drops in without changing the Packager or any other caller. Reason-code policies
and case samples are validated into ready-to-wire structures.

Every failure raises the fixed ``IngestionError`` — raw record content (which may
be sensitive) is never echoed.
"""

import json
from collections.abc import Iterable, Mapping

from pydantic import BaseModel, ValidationError

from oceanpilot.adapters.ingestion.schema import (
    BankRuleRecord,
    CaseSampleRecord,
    ReasonCodeMappingRecord,
    ReasonPolicyRecord,
)
from oceanpilot.adapters.knowledge.bank_rules import InMemoryBankRules
from oceanpilot.application.knowledge_base import BankRuleEntry
from oceanpilot.domain.chargeback import DisputeReasonCode
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.security import assert_no_sensitive_data


class IngestionError(Exception):
    def __init__(self) -> None:
        super().__init__("ingestion record is invalid")


def parse_json_records(text: str | bytes) -> list[dict[str, object]]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise IngestionError() from None
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise IngestionError()
    return data


def _validate[T: BaseModel](model: type[T], records: Iterable[Mapping[str, object]]) -> list[T]:
    validated: list[T] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise IngestionError()
        try:
            validated.append(model.model_validate(dict(record)))
        except ValidationError:
            raise IngestionError() from None
    return validated


def load_reason_policies(
    records: Iterable[Mapping[str, object]],
) -> dict[DisputeReasonCode, ReasonPolicyRecord]:
    result: dict[DisputeReasonCode, ReasonPolicyRecord] = {}
    for record in _validate(ReasonPolicyRecord, records):
        if record.reason_code in result:
            raise IngestionError()  # duplicate reason_code
        result[record.reason_code] = record
    return result


def load_reason_code_mappings(
    records: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], DisputeReasonCode]:
    """Validate external reason-code mappings and key them case-insensitively."""

    result: dict[tuple[str, str], DisputeReasonCode] = {}
    for record in _validate(ReasonCodeMappingRecord, records):
        _assert_safe_text(record.card_network, record.network_reason_code, record.notes)
        key = (
            record.card_network.strip().upper(),
            record.network_reason_code.strip().upper(),
        )
        if key in result:
            raise IngestionError()
        result[key] = record.reason_code
    return result


def load_bank_rules(records: Iterable[Mapping[str, object]]) -> InMemoryBankRules:
    bank_entries: dict[tuple[str, str, DisputeReasonCode], BankRuleEntry] = {}
    network_entries: dict[tuple[str, DisputeReasonCode], BankRuleEntry] = {}
    for record in _validate(BankRuleRecord, records):
        _assert_safe_text(record.card_network, record.bank_id or "", record.notes)
        entry = BankRuleEntry(
            reason_code=record.reason_code,
            required_evidence=tuple(record.required_evidence),
            template_order=tuple(record.template_order),
            submission_window_days=record.submission_window_days,
            notes=record.notes,
            source=record.source,
        )
        if record.source == "bank":
            assert record.bank_id is not None  # guaranteed by schema validator
            bank_key = (record.bank_id, record.card_network, record.reason_code)
            if bank_key in bank_entries:
                raise IngestionError()
            bank_entries[bank_key] = entry
        else:
            network_key = (record.card_network, record.reason_code)
            if network_key in network_entries:
                raise IngestionError()
            network_entries[network_key] = entry
    return InMemoryBankRules(bank_entries=bank_entries, network_entries=network_entries)


def load_case_samples(
    records: Iterable[Mapping[str, object]],
) -> tuple[CaseSampleRecord, ...]:
    validated = _validate(CaseSampleRecord, records)
    for record in validated:
        _assert_safe_text(record.case_ref, record.notes)
    return tuple(validated)


def _assert_safe_text(*values: str) -> None:
    try:
        assert_no_sensitive_data({"values": list(values)})
    except SensitiveDataRejected:
        raise IngestionError() from None
