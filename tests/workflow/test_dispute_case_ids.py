"""Derived case IDs avoid card-number false positives without bypassing screening."""

import re
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.disputes import DisputeError, DisputeService
from oceanpilot.domain.dispute import fingerprint
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.security import assert_no_sensitive_data

OP = {"role": "OPERATOR", "actor_id": "case-id-operator"}
NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)
FALSE_POSITIVE_COMMAND_ID = "generated-case-id-regression-1318"


@pytest.fixture
def service(tmp_path):
    return DisputeService(SQLiteDisputeStore(tmp_path / "case-ids.db"), clock=lambda: NOW)


def intake(command_id):
    return {
        "command_id": command_id,
        "action": "INTAKE",
        "confirmed": True,
        "data": {
            "merchant_id": "case-id-merchant",
            "transaction_id": "synthetic-case-id-transaction",
            "scheme": "VISA",
            "channel": "MOCK",
            "reason_code": "13.1",
            "amount_minor": 12800,
            "currency": "USD",
            "event_id": "case-id-upstream-event",
        },
    }


def save_legacy_case(service, payload):
    """The pre-upgrade canonical command had this exact derived case_id field."""
    old_canonical = deepcopy(payload)
    old_canonical["case_id"] = f"OPV2-{fingerprint(payload['command_id'])[:16]}"
    return service.execute(old_canonical, OP)


def test_real_legacy_hash_false_positive_intake_succeeds_with_screened_new_id(service):
    payload = intake(FALSE_POSITIVE_COMMAND_ID)
    legacy_id = f"OPV2-{fingerprint(payload['command_id'])[:16]}"
    assert legacy_id == "OPV2-97d4952829113545"
    with pytest.raises(SensitiveDataRejected):
        assert_no_sensitive_data(legacy_id)
    result = service.execute(payload, OP)
    case_id = result["case"]["id"]
    assert case_id.startswith("OPV2-")
    assert case_id != legacy_id
    assert all(len(match.group()) < 13 for match in re.finditer(r"[\d\s-]+", case_id))
    assert_no_sensitive_data(case_id)
    assert service.store.get_case(legacy_id) is None
    assert len(service.list_cases(OP)) == 1
    replay = service.execute(payload, OP)
    assert replay["replayed"] is True
    assert replay["case"] == result["case"]
    assert replay["receipt"] == result["receipt"]
    assert "case_id" not in payload


def test_legacy_persisted_intake_replays_same_command_after_service_restart(service):
    payload = intake("already-committed-before-case-id-upgrade")
    first = save_legacy_case(service, payload)
    restarted = DisputeService(SQLiteDisputeStore(service.store.db_path), clock=lambda: NOW)
    replay = restarted.execute(payload, OP)
    assert replay["replayed"] is True
    assert replay["case"] == first["case"]
    assert replay["receipt"] == first["receipt"]
    assert len(restarted.list_cases(OP)) == 1
    assert len(replay["case"]["audit"]) == 1


@pytest.mark.parametrize("duplicate_kind", ["EVENT", "UPSTREAM_CASE"])
def test_legacy_duplicate_notification_receipt_replays_without_derived_case_row(
    service, duplicate_kind
):
    original = intake("legacy-notice-primary")
    original["data"]["upstream_case_id"] = "legacy-shared-upstream-case"
    save_legacy_case(service, original)
    notification = deepcopy(original)
    notification["command_id"] = "legacy-notice-alias"
    if duplicate_kind == "UPSTREAM_CASE":
        notification["data"]["event_id"] = "legacy-second-notice-event"
    first = save_legacy_case(service, notification)
    alias_id = f"OPV2-{fingerprint(notification['command_id'])[:16]}"
    assert service.store.get_case(alias_id) is None
    before = service.list_cases(OP)
    restarted = DisputeService(SQLiteDisputeStore(service.store.db_path), clock=lambda: NOW)
    replay = restarted.execute(notification, OP)
    assert replay["replayed"] is True
    assert replay["case"] == first["case"]
    assert replay["receipt"] == first["receipt"]
    assert restarted.list_cases(OP) == before
    changed = deepcopy(notification)
    changed["data"]["amount_minor"] += 1
    with pytest.raises(DisputeError) as failure:
        restarted.execute(changed, OP)
    assert failure.value.status == 409
    with pytest.raises(DisputeError) as failure:
        restarted.execute(notification, OP | {"actor_id": "different-legacy-notice-actor"})
    assert failure.value.status == 409
    assert restarted.list_cases(OP) == before


@pytest.mark.parametrize("change", ["payload", "actor", "role"])
def test_legacy_id_compatibility_keeps_command_content_and_identity_checks(service, change):
    payload = intake("legacy-case-must-keep-command-authorization")
    first = save_legacy_case(service, payload)
    altered = deepcopy(payload)
    identity = dict(OP)
    if change == "payload":
        altered["data"]["amount_minor"] += 1
    elif change == "actor":
        identity["actor_id"] = "another-operator"
    else:
        identity["role"] = "AGENT"
    with pytest.raises(DisputeError) as failure:
        service.execute(altered, identity)
    assert failure.value.status == (403 if change == "role" else 409)
    assert service.store.get_case(first["case"]["id"]) == first["case"]
    assert len(service.list_cases(OP)) == 1


def test_explicit_case_id_is_preserved_verbatim(service):
    payload = intake("explicit-case-id-command")
    payload["case_id"] = "OPV2-existing-external-case-name"
    first = service.execute(payload, OP)
    assert first["case"]["id"] == payload["case_id"]
    assert service.execute(payload, OP)["replayed"] is True


def test_existing_legacy_looking_case_does_not_select_legacy_format_without_matching_receipt(
    service,
):
    payload = intake("new-command-with-unrelated-legacy-looking-case")
    legacy_id = f"OPV2-{fingerprint(payload['command_id'])[:16]}"
    unrelated = intake("unrelated-explicit-case-command")
    unrelated["case_id"] = legacy_id
    unrelated["data"]["event_id"] = "unrelated-upstream-event"
    existing = service.execute(unrelated, OP)
    created = service.execute(payload, OP)
    assert created["case"]["id"] != legacy_id
    assert service.store.get_case(legacy_id) == existing["case"]
    assert service.execute(payload, OP)["replayed"] is True
    assert len(service.list_cases(OP)) == 2


def test_explicit_sensitive_id_and_sensitive_free_text_are_still_rejected(service):
    payload = intake(FALSE_POSITIVE_COMMAND_ID)
    payload["case_id"] = f"OPV2-{fingerprint(payload['command_id'])[:16]}"
    with pytest.raises(DisputeError) as failure:
        service.execute(payload, OP)
    assert failure.value.code == "SENSITIVE_DATA_REJECTED"
    clean_id = intake("new-id-does-not-exempt-sensitive-payload")
    clean_id["data"]["transaction_id"] = "card 4111 1111 1111 1111"
    with pytest.raises(DisputeError) as failure:
        service.execute(clean_id, OP)
    assert failure.value.code == "SENSITIVE_DATA_REJECTED"
    assert service.list_cases(OP) == []
