from datetime import UTC, datetime
from hashlib import sha256
from itertools import permutations

import pytest
from pydantic import ValidationError

from oceanpilot.domain.enums import (
    EvidenceAvailability,
    EvidenceCode,
    EvidenceValueType,
    ReviewReason,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.evidence_policy import (
    EVIDENCE_SCHEMA_VERSION,
    FIELD_CATALOG,
    ISO_COUNTRY_ALPHA2,
    ISO_CURRENCY_ALPHA3,
    build_active_evidence_view,
    canonical_evidence_hash,
    create_evidence_item,
)
from oceanpilot.domain.models import EvidenceCreate, EvidenceOrigin

CASE_ID = "00000000-0000-4000-8000-000000000010"
DEFAULT_EVIDENCE_ID = "00000000-0000-4000-8000-000000000011"
OBSERVED_AT = datetime.fromisoformat("2026-07-18T12:00:00+08:00")
COLLECTED_AT = datetime.fromisoformat("2026-07-18T12:00:01+08:00")
ORIGIN = EvidenceOrigin(
    source_type=SourceType.SYNTHETIC_ADAPTER,
    source_reliability=SourceReliability.SYNTHETIC_TEST,
    synthetic=True,
)


def make_request(
    code: EvidenceCode,
    value: str | bool | datetime | None,
    *,
    availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE,
    evidence_id: str = DEFAULT_EVIDENCE_ID,
    observed_at: datetime | None = OBSERVED_AT,
    source_ref: str = "synthetic:fixture",
) -> EvidenceCreate:
    return EvidenceCreate(
        evidence_id=evidence_id,
        evidence_code=code,
        availability=availability,
        typed_value=value,
        observed_at=observed_at,
        source_ref=source_ref,
    )


def create(request: EvidenceCreate, *, collected_at: datetime = COLLECTED_AT):
    return create_evidence_item(
        request,
        case_id=CASE_ID,
        origin=ORIGIN,
        collected_at=collected_at,
    )


VALID_CATALOG_VALUES = (
    (EvidenceCode.CONTEXT_ENVIRONMENT, "PROD", EvidenceValueType.STRING),
    (EvidenceCode.TRANSACTION_REFERENCE, "txn_1-A", EvidenceValueType.STRING),
    (EvidenceCode.TRANSACTION_OCCURRED_AT, OBSERVED_AT, EvidenceValueType.DATETIME),
    (EvidenceCode.TRANSACTION_COUNTRY, "CN", EvidenceValueType.COUNTRY),
    (EvidenceCode.TRANSACTION_CURRENCY, "USD", EvidenceValueType.CURRENCY),
    (EvidenceCode.PAYMENT_METHOD, "CARD", EvidenceValueType.STRING),
    (EvidenceCode.INTEGRATION_TYPE, "API", EvidenceValueType.STRING),
    (EvidenceCode.INTEGRATION_PLATFORM, "SHOPIFY", EvidenceValueType.STRING),
    (EvidenceCode.INTEGRATION_PLUGIN_VERSION, "v1.2.3+demo", EvidenceValueType.STRING),
    (EvidenceCode.SYMPTOM_STATUS, "FAILED", EvidenceValueType.STRING),
    (EvidenceCode.SYMPTOM_ERROR_CODE, "err.code-1", EvidenceValueType.STRING),
    (EvidenceCode.AUTHENTICATION_STATUS, "FAILED", EvidenceValueType.STRING),
    (EvidenceCode.AUTHENTICATION_RESULT_CODE, "auth_1", EvidenceValueType.STRING),
    (EvidenceCode.CALLBACK_DELIVERY_STATUS, "FAILED", EvidenceValueType.STRING),
    (EvidenceCode.RISK_DECISION_CODE, "risk.1", EvidenceValueType.STRING),
    (EvidenceCode.CONFIGURATION_CHECK_RESULT, "NO_MISMATCH", EvidenceValueType.STRING),
)


def test_field_catalog_is_complete_ordered_and_externally_immutable() -> None:
    assert tuple(FIELD_CATALOG) == tuple(EvidenceCode)
    assert tuple(entry.value_type for entry in FIELD_CATALOG.values()) == tuple(
        value_type for _, _, value_type in VALID_CATALOG_VALUES
    )
    with pytest.raises(TypeError):
        FIELD_CATALOG[EvidenceCode.CONTEXT_ENVIRONMENT] = FIELD_CATALOG[
            EvidenceCode.CONTEXT_ENVIRONMENT
        ]


def test_frozen_iso_membership_counts_and_digests() -> None:
    country_payload = " ".join(sorted(ISO_COUNTRY_ALPHA2)).encode()
    currency_payload = " ".join(sorted(ISO_CURRENCY_ALPHA3)).encode()

    assert len(ISO_COUNTRY_ALPHA2) == 249
    assert sha256(country_payload).hexdigest() == (
        "e1c950d24ceb933ac49eaa44de8d1a7ffb6bf40bfe519a5a99d791cb50332197"
    )
    assert len(ISO_CURRENCY_ALPHA3) == 178
    assert sha256(currency_payload).hexdigest() == (
        "62185bf8d74197e249d7a609a697f81820def9ca894cc3e9121c82497358f453"
    )
    assert {"CN", "US"} <= ISO_COUNTRY_ALPHA2
    assert {"EUR", "USD", "XAD", "XCG", "ZWG"} <= ISO_CURRENCY_ALPHA3
    assert {"ZZ", "XK"}.isdisjoint(ISO_COUNTRY_ALPHA2)
    assert {"ZZZ", "BGN", "ZWL"}.isdisjoint(ISO_CURRENCY_ALPHA3)


@pytest.mark.parametrize(("code", "value", "value_type"), VALID_CATALOG_VALUES)
def test_every_catalog_row_accepts_a_valid_value_and_derives_type(
    code: EvidenceCode,
    value: str | datetime,
    value_type: EvidenceValueType,
) -> None:
    item = create(make_request(code, value))

    assert item.schema_version == EVIDENCE_SCHEMA_VERSION == "1"
    assert item.value_type is value_type
    assert item.typed_value == value


@pytest.mark.parametrize(
    ("code", "wrong_type"),
    tuple(
        (code, "2026-07-18T04:00:00Z")
        if code is EvidenceCode.TRANSACTION_OCCURRED_AT
        else (code, True)
        for code in EvidenceCode
    ),
)
def test_every_catalog_row_rejects_the_wrong_type(
    code: EvidenceCode,
    wrong_type: str | bool,
) -> None:
    with pytest.raises(ValueError):
        create(make_request(code, wrong_type))


INVALID_CATALOG_VALUES = (
    (EvidenceCode.CONTEXT_ENVIRONMENT, "prod"),
    (EvidenceCode.CONTEXT_ENVIRONMENT, " PROD"),
    (EvidenceCode.TRANSACTION_REFERENCE, ""),
    (EvidenceCode.TRANSACTION_REFERENCE, "has space"),
    (EvidenceCode.TRANSACTION_REFERENCE, "a" * 65),
    (EvidenceCode.TRANSACTION_COUNTRY, "cn"),
    (EvidenceCode.TRANSACTION_COUNTRY, "CN "),
    (EvidenceCode.TRANSACTION_COUNTRY, "ZZ"),
    (EvidenceCode.TRANSACTION_CURRENCY, "usd"),
    (EvidenceCode.TRANSACTION_CURRENCY, " USD"),
    (EvidenceCode.TRANSACTION_CURRENCY, "BGN"),
    (EvidenceCode.PAYMENT_METHOD, "card"),
    (EvidenceCode.PAYMENT_METHOD, "CARD "),
    (EvidenceCode.INTEGRATION_TYPE, "plugin"),
    (EvidenceCode.INTEGRATION_TYPE, " PLUGIN"),
    (EvidenceCode.INTEGRATION_PLATFORM, "shopify"),
    (EvidenceCode.INTEGRATION_PLATFORM, "SHOPIFY "),
    (EvidenceCode.INTEGRATION_PLUGIN_VERSION, ""),
    (EvidenceCode.INTEGRATION_PLUGIN_VERSION, "-1"),
    (EvidenceCode.INTEGRATION_PLUGIN_VERSION, "v 1"),
    (EvidenceCode.INTEGRATION_PLUGIN_VERSION, "v" * 33),
    (EvidenceCode.SYMPTOM_STATUS, "failed"),
    (EvidenceCode.SYMPTOM_STATUS, "FAILED "),
    (EvidenceCode.SYMPTOM_ERROR_CODE, ""),
    (EvidenceCode.SYMPTOM_ERROR_CODE, "bad code"),
    (EvidenceCode.SYMPTOM_ERROR_CODE, "e" * 65),
    (EvidenceCode.AUTHENTICATION_STATUS, "authenticated"),
    (EvidenceCode.AUTHENTICATION_STATUS, "AUTHENTICATED "),
    (EvidenceCode.AUTHENTICATION_RESULT_CODE, ""),
    (EvidenceCode.AUTHENTICATION_RESULT_CODE, "bad code"),
    (EvidenceCode.AUTHENTICATION_RESULT_CODE, "a" * 65),
    (EvidenceCode.CALLBACK_DELIVERY_STATUS, "delivered"),
    (EvidenceCode.CALLBACK_DELIVERY_STATUS, " DELIVERED"),
    (EvidenceCode.RISK_DECISION_CODE, ""),
    (EvidenceCode.RISK_DECISION_CODE, "bad code"),
    (EvidenceCode.RISK_DECISION_CODE, "r" * 65),
    (EvidenceCode.CONFIGURATION_CHECK_RESULT, "no_mismatch"),
    (EvidenceCode.CONFIGURATION_CHECK_RESULT, "NO_MISMATCH "),
)


@pytest.mark.parametrize(("code", "value"), INVALID_CATALOG_VALUES)
def test_catalog_rejects_invalid_case_whitespace_and_boundaries(
    code: EvidenceCode,
    value: str,
) -> None:
    with pytest.raises(ValueError):
        create(make_request(code, value))


def test_datetime_catalog_row_rejects_naive_values() -> None:
    with pytest.raises(ValidationError):
        make_request(EvidenceCode.TRANSACTION_OCCURRED_AT, datetime(2026, 7, 18, 12))


def test_availability_and_value_must_be_compatible() -> None:
    with pytest.raises(ValueError):
        create(make_request(EvidenceCode.CONTEXT_ENVIRONMENT, None))
    with pytest.raises(ValueError):
        create(
            make_request(
                EvidenceCode.CONTEXT_ENVIRONMENT,
                "PROD",
                availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
            )
        )

    unavailable = create(
        make_request(
            EvidenceCode.CONTEXT_ENVIRONMENT,
            None,
            availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
        )
    )
    assert unavailable.typed_value is None
    assert unavailable.value_type is EvidenceValueType.STRING


def test_canonical_hash_matches_golden_vector() -> None:
    digest = canonical_evidence_hash(
        make_request(EvidenceCode.CONTEXT_ENVIRONMENT, "PROD"),
        ORIGIN,
    )
    assert digest == "a178af8643b1b7b495070d92ccdd0edad9d9bbdd51c5c54cbbb9425aaeb2558d"


def test_canonical_hash_normalizes_offsets_and_unicode_but_not_case_or_space() -> None:
    utc_request = make_request(
        EvidenceCode.CONTEXT_ENVIRONMENT,
        "PROD",
        observed_at=datetime(2026, 7, 18, 4, tzinfo=UTC),
        source_ref="caf\u00e9",
    )
    offset_request = make_request(
        EvidenceCode.CONTEXT_ENVIRONMENT,
        "PROD",
        observed_at=OBSERVED_AT,
        source_ref="cafe\u0301",
    )

    assert canonical_evidence_hash(utc_request, ORIGIN) == canonical_evidence_hash(
        offset_request, ORIGIN
    )
    assert canonical_evidence_hash(
        make_request(EvidenceCode.CONTEXT_ENVIRONMENT, "PROD", source_ref="Ref"), ORIGIN
    ) != canonical_evidence_hash(
        make_request(EvidenceCode.CONTEXT_ENVIRONMENT, "PROD", source_ref="ref "), ORIGIN
    )


def test_datetime_typed_value_normalizes_to_the_same_hash() -> None:
    first = make_request(EvidenceCode.TRANSACTION_OCCURRED_AT, OBSERVED_AT)
    second = make_request(
        EvidenceCode.TRANSACTION_OCCURRED_AT,
        datetime(2026, 7, 18, 4, tzinfo=UTC),
    )
    assert canonical_evidence_hash(first, ORIGIN) == canonical_evidence_hash(second, ORIGIN)


def test_collected_at_is_excluded_from_content_hash() -> None:
    request = make_request(EvidenceCode.CONTEXT_ENVIRONMENT, "PROD")
    first = create(request, collected_at=COLLECTED_AT)
    second = create(
        request,
        collected_at=datetime.fromisoformat("2026-07-19T12:00:01+08:00"),
    )
    assert first.content_hash == second.content_hash


def test_empty_fold_returns_all_sixteen_slots_in_enum_order() -> None:
    view = build_active_evidence_view([])

    assert tuple(view.slots) == tuple(EvidenceCode)
    assert len(view.slots) == 16
    assert all(slot.selected_evidence is None for slot in view.slots.values())
    assert all(not slot.known_unknown for slot in view.slots.values())
    assert all(not slot.conflicting for slot in view.slots.values())
    assert view.review_reasons == frozenset()


def test_only_unavailable_is_a_known_unknown(evidence_factory) -> None:
    item = evidence_factory(availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE)
    slot = build_active_evidence_view([item]).slots[EvidenceCode.CONTEXT_ENVIRONMENT]
    assert (slot.selected_evidence, slot.known_unknown, slot.conflicting) == (
        None,
        True,
        False,
    )


def test_available_beats_unavailable_history(evidence_factory) -> None:
    unavailable = evidence_factory(
        availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
        evidence_id="00000000-0000-4000-8000-000000000001",
    )
    available = evidence_factory(evidence_id="00000000-0000-4000-8000-000000000002")
    slot = build_active_evidence_view([unavailable, available]).slots[
        EvidenceCode.CONTEXT_ENVIRONMENT
    ]
    assert slot.selected_evidence == available
    assert slot.known_unknown is False
    assert slot.conflicting is False


def test_same_value_uses_all_quality_levels_then_lowest_id(evidence_factory) -> None:
    reliability_order = (
        SourceReliability.USER_REPORTED,
        SourceReliability.OPERATOR_CONFIRMED,
        SourceReliability.SYNTHETIC_TEST,
        SourceReliability.VERIFIED_DOCUMENT,
        SourceReliability.SYSTEM_OF_RECORD,
    )
    items = [
        evidence_factory(
            reliability=reliability,
            evidence_id=f"00000000-0000-4000-8000-{index:012d}",
        )
        for index, reliability in enumerate(reliability_order, start=1)
    ]
    selected = (
        build_active_evidence_view(items).slots[EvidenceCode.CONTEXT_ENVIRONMENT].selected_evidence
    )
    assert selected is not None
    assert selected.source_reliability is SourceReliability.SYSTEM_OF_RECORD

    high_b = evidence_factory(
        reliability=SourceReliability.SYSTEM_OF_RECORD,
        evidence_id="00000000-0000-4000-8000-000000000012",
    )
    high_a = evidence_factory(
        reliability=SourceReliability.SYSTEM_OF_RECORD,
        evidence_id="00000000-0000-4000-8000-000000000010",
    )
    tied = (
        build_active_evidence_view([high_b, high_a])
        .slots[EvidenceCode.CONTEXT_ENVIRONMENT]
        .selected_evidence
    )
    assert tied == high_a


@pytest.mark.parametrize(
    ("higher", "lower"),
    (
        (SourceReliability.SYSTEM_OF_RECORD, SourceReliability.VERIFIED_DOCUMENT),
        (SourceReliability.VERIFIED_DOCUMENT, SourceReliability.SYNTHETIC_TEST),
        (SourceReliability.SYNTHETIC_TEST, SourceReliability.OPERATOR_CONFIRMED),
        (SourceReliability.OPERATOR_CONFIRMED, SourceReliability.USER_REPORTED),
    ),
)
def test_each_adjacent_quality_level_beats_the_next(
    evidence_factory,
    higher: SourceReliability,
    lower: SourceReliability,
) -> None:
    lower_id = evidence_factory(
        reliability=lower,
        evidence_id="00000000-0000-4000-8000-000000000001",
    )
    higher_id = evidence_factory(
        reliability=higher,
        evidence_id="00000000-0000-4000-8000-000000000002",
    )

    selected = (
        build_active_evidence_view([lower_id, higher_id])
        .slots[EvidenceCode.CONTEXT_ENVIRONMENT]
        .selected_evidence
    )
    assert selected == higher_id


def test_unicode_and_datetime_values_are_normalized_for_folding(evidence_factory) -> None:
    unicode_a = evidence_factory(
        code="symptom.error_code",
        value="base",
        evidence_id="00000000-0000-4000-8000-000000000001",
    ).model_copy(update={"typed_value": "caf\u00e9", "content_hash": "0" * 64})
    unicode_b = evidence_factory(
        code="symptom.error_code",
        value="base",
        evidence_id="00000000-0000-4000-8000-000000000002",
    ).model_copy(update={"typed_value": "cafe\u0301", "content_hash": "1" * 64})
    time_a = evidence_factory(
        code="transaction.occurred_at",
        value=OBSERVED_AT,
        evidence_id="00000000-0000-4000-8000-000000000003",
    )
    time_b = evidence_factory(
        code="transaction.occurred_at",
        value=datetime(2026, 7, 18, 4, tzinfo=UTC),
        evidence_id="00000000-0000-4000-8000-000000000004",
    )

    view = build_active_evidence_view([unicode_b, unicode_a, time_b, time_a])
    assert view.slots[EvidenceCode.SYMPTOM_ERROR_CODE].conflicting is False
    assert view.slots[EvidenceCode.TRANSACTION_OCCURRED_AT].conflicting is False
    assert view.slots[EvidenceCode.SYMPTOM_ERROR_CODE].selected_evidence == unicode_a


def test_boolean_fold_equality_is_exact(evidence_factory) -> None:
    true_a = evidence_factory(evidence_id="00000000-0000-4000-8000-000000000001").model_copy(
        update={"typed_value": True, "value_type": EvidenceValueType.BOOLEAN}
    )
    true_b = evidence_factory(evidence_id="00000000-0000-4000-8000-000000000002").model_copy(
        update={"typed_value": True, "value_type": EvidenceValueType.BOOLEAN}
    )
    false_b = true_b.model_copy(update={"typed_value": False})

    equal_slot = build_active_evidence_view([true_b, true_a]).slots[
        EvidenceCode.CONTEXT_ENVIRONMENT
    ]
    conflicting_slot = build_active_evidence_view([true_a, false_b]).slots[
        EvidenceCode.CONTEXT_ENVIRONMENT
    ]
    assert equal_slot.selected_evidence == true_a
    assert equal_slot.conflicting is False
    assert conflicting_slot.selected_evidence is None
    assert conflicting_slot.conflicting is True


def test_different_available_values_become_conflict(evidence_factory) -> None:
    first = evidence_factory(value="PROD", evidence_id="00000000-0000-4000-8000-000000000001")
    second = evidence_factory(value="SANDBOX", evidence_id="00000000-0000-4000-8000-000000000002")

    view = build_active_evidence_view([first, second])
    slot = view.slots[EvidenceCode.CONTEXT_ENVIRONMENT]
    assert (slot.selected_evidence, slot.known_unknown, slot.conflicting) == (
        None,
        False,
        True,
    )
    assert view.review_reasons == frozenset({ReviewReason.CONFLICTING_EVIDENCE})


def test_fold_is_invariant_to_input_permutations(evidence_factory) -> None:
    items = (
        evidence_factory(evidence_id="00000000-0000-4000-8000-000000000001"),
        evidence_factory(
            evidence_id="00000000-0000-4000-8000-000000000002",
            reliability=SourceReliability.USER_REPORTED,
        ),
        evidence_factory(
            availability=EvidenceAvailability.CONFIRMED_UNAVAILABLE,
            evidence_id="00000000-0000-4000-8000-000000000003",
        ),
    )
    expected = build_active_evidence_view(items)
    assert all(build_active_evidence_view(order) == expected for order in permutations(items))
