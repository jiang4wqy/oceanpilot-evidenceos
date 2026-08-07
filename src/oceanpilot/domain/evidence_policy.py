import json
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType

from oceanpilot.domain.enums import (
    EvidenceAvailability,
    EvidenceCode,
    EvidenceValueType,
    ReviewReason,
    SourceReliability,
    StopReason,
    TargetRole,
)
from oceanpilot.domain.models import (
    ActiveEvidenceSlot,
    ActiveEvidenceView,
    AwareDateTime,
    EvidenceCreate,
    EvidenceItem,
    EvidenceOrigin,
    ReadinessAssessment,
    UUID4Str,
)

EVIDENCE_SCHEMA_VERSION = "1"

ISO_COUNTRY_ALPHA2 = frozenset(
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI "  # noqa: SIM905
    "BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN "
    "CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK "
    "FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM "
    "HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN "
    "KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK "
    "ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP "
    "NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW "
    "SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF "
    "TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI "
    "VN VU WF WS YE YT ZA ZM ZW".split()
)
ISO_CURRENCY_ALPHA3 = frozenset(
    "AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV "  # noqa: SIM905
    "BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP "
    "CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF "
    "GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR "
    "KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT "
    "MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN "
    "PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE "
    "SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX "
    "USD USN UYI UYU UYW UZS VED VES VND VUV WST XAD XAF XAG XAU XBA XBB XBC "
    "XBD XCD XCG XDR XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWG".split()
)


@dataclass(frozen=True)
class _FieldPolicy:
    value_type: EvidenceValueType
    validator: Callable[[object], bool]


def _one_of(*allowed: str) -> Callable[[object], bool]:
    values = frozenset(allowed)
    return lambda value: type(value) is str and value in values


def _fullmatch(pattern: str) -> Callable[[object], bool]:
    compiled = re.compile(pattern)
    return lambda value: type(value) is str and compiled.fullmatch(value) is not None


def _member_of(values: frozenset[str]) -> Callable[[object], bool]:
    return lambda value: type(value) is str and value in values


def _aware_datetime(value: object) -> bool:
    return (
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
    )


FIELD_CATALOG: Mapping[EvidenceCode, _FieldPolicy] = MappingProxyType(
    {
        EvidenceCode.CONTEXT_ENVIRONMENT: _FieldPolicy(
            EvidenceValueType.STRING, _one_of("PROD", "SANDBOX")
        ),
        EvidenceCode.TRANSACTION_REFERENCE: _FieldPolicy(
            EvidenceValueType.STRING, _fullmatch(r"[A-Za-z0-9_.-]{1,64}")
        ),
        EvidenceCode.TRANSACTION_OCCURRED_AT: _FieldPolicy(
            EvidenceValueType.DATETIME, _aware_datetime
        ),
        EvidenceCode.TRANSACTION_COUNTRY: _FieldPolicy(
            EvidenceValueType.COUNTRY, _member_of(ISO_COUNTRY_ALPHA2)
        ),
        EvidenceCode.TRANSACTION_CURRENCY: _FieldPolicy(
            EvidenceValueType.CURRENCY, _member_of(ISO_CURRENCY_ALPHA3)
        ),
        EvidenceCode.PAYMENT_METHOD: _FieldPolicy(
            EvidenceValueType.STRING,
            _one_of("CARD", "APPLE_PAY", "GOOGLE_PAY", "KLARNA", "LOCAL_PAYMENT", "OTHER"),
        ),
        EvidenceCode.INTEGRATION_TYPE: _FieldPolicy(
            EvidenceValueType.STRING, _one_of("API", "PLUGIN")
        ),
        EvidenceCode.INTEGRATION_PLATFORM: _FieldPolicy(
            EvidenceValueType.STRING,
            _one_of("SHOPIFY", "WOOCOMMERCE", "MAGENTO", "CUSTOM"),
        ),
        EvidenceCode.INTEGRATION_PLUGIN_VERSION: _FieldPolicy(
            EvidenceValueType.STRING, _fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,31}")
        ),
        EvidenceCode.SYMPTOM_STATUS: _FieldPolicy(
            EvidenceValueType.STRING,
            _one_of("PENDING", "FAILED", "SUCCEEDED", "DECLINED", "UNKNOWN"),
        ),
        EvidenceCode.SYMPTOM_ERROR_CODE: _FieldPolicy(
            EvidenceValueType.STRING, _fullmatch(r"[A-Za-z0-9_.-]{1,64}")
        ),
        EvidenceCode.AUTHENTICATION_STATUS: _FieldPolicy(
            EvidenceValueType.STRING,
            _one_of("REQUIRED", "CHALLENGE_PENDING", "AUTHENTICATED", "FAILED", "UNKNOWN"),
        ),
        EvidenceCode.AUTHENTICATION_RESULT_CODE: _FieldPolicy(
            EvidenceValueType.STRING, _fullmatch(r"[A-Za-z0-9_.-]{1,64}")
        ),
        EvidenceCode.CALLBACK_DELIVERY_STATUS: _FieldPolicy(
            EvidenceValueType.STRING,
            _one_of("NOT_RECEIVED", "DELIVERED", "FAILED", "UNKNOWN"),
        ),
        EvidenceCode.RISK_DECISION_CODE: _FieldPolicy(
            EvidenceValueType.STRING, _fullmatch(r"[A-Za-z0-9_.-]{1,64}")
        ),
        EvidenceCode.CONFIGURATION_CHECK_RESULT: _FieldPolicy(
            EvidenceValueType.STRING,
            _one_of(
                "MERCHANT_SIDE_MISMATCH",
                "PSP_PROFILE_MISMATCH",
                "NO_MISMATCH",
                "UNKNOWN",
            ),
        ),
    }
)

_SOURCE_QUALITY = {
    SourceReliability.SYSTEM_OF_RECORD: 5,
    SourceReliability.VERIFIED_DOCUMENT: 4,
    SourceReliability.SYNTHETIC_TEST: 3,
    SourceReliability.OPERATOR_CONFIRMED: 2,
    SourceReliability.USER_REPORTED: 1,
}


def _utc_rfc3339(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical_typed_value(value: str | bool | datetime | None) -> str | bool | None:
    if isinstance(value, datetime):
        return _utc_rfc3339(value)
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    return value


def canonical_evidence_hash(request: EvidenceCreate, origin: EvidenceOrigin) -> str:
    payload = {
        "availability": request.availability.value,
        "evidence_code": request.evidence_code.value,
        "evidence_id": request.evidence_id,
        "observed_at": _utc_rfc3339(request.observed_at),
        "source_ref": request.source_ref,
        "source_reliability": origin.source_reliability.value,
        "source_type": origin.source_type.value,
        "synthetic": origin.synthetic,
        "typed_value": _canonical_typed_value(request.typed_value),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    normalized = unicodedata.normalize("NFC", encoded.decode()).encode()
    return sha256(normalized).hexdigest()


def _validate_catalog_value(request: EvidenceCreate) -> _FieldPolicy:
    policy = FIELD_CATALOG[request.evidence_code]
    if request.availability is EvidenceAvailability.CONFIRMED_UNAVAILABLE:
        if request.typed_value is not None:
            raise ValueError("confirmed unavailable evidence must not have a value")
    elif request.typed_value is None or not policy.validator(request.typed_value):
        raise ValueError("evidence value does not match field policy")
    return policy


def create_evidence_item(
    request: EvidenceCreate,
    *,
    case_id: UUID4Str,
    origin: EvidenceOrigin,
    collected_at: AwareDateTime,
) -> EvidenceItem:
    policy = _validate_catalog_value(request)
    return EvidenceItem(
        case_id=case_id,
        evidence_id=request.evidence_id,
        schema_version=EVIDENCE_SCHEMA_VERSION,
        evidence_code=request.evidence_code,
        availability=request.availability,
        value_type=policy.value_type,
        typed_value=request.typed_value,
        source_type=origin.source_type,
        source_ref=request.source_ref,
        source_reliability=origin.source_reliability,
        observed_at=request.observed_at,
        collected_at=collected_at,
        synthetic=origin.synthetic,
        content_hash=canonical_evidence_hash(request, origin),
    )


def _fold_value(value: str | bool | datetime | None) -> tuple[str, object]:
    if isinstance(value, datetime):
        return ("DATETIME", value.astimezone(UTC))
    if type(value) is str:
        return ("STRING", unicodedata.normalize("NFC", value))
    return ("BOOLEAN", value)


def build_active_evidence_view(evidence: Sequence[EvidenceItem]) -> ActiveEvidenceView:
    by_code: dict[EvidenceCode, list[EvidenceItem]] = {code: [] for code in EvidenceCode}
    for item in evidence:
        by_code[item.evidence_code].append(item)

    slots: dict[EvidenceCode, ActiveEvidenceSlot] = {}
    has_conflict = False
    for code in EvidenceCode:
        items = by_code[code]
        available = [item for item in items if item.availability is EvidenceAvailability.AVAILABLE]
        normalized_values = {_fold_value(item.typed_value) for item in available}
        conflicting = len(normalized_values) > 1
        selected = None
        if available and not conflicting:
            selected = min(
                available,
                key=lambda item: (-_SOURCE_QUALITY[item.source_reliability], item.evidence_id),
            )
        slots[code] = ActiveEvidenceSlot(
            evidence_code=code,
            selected_evidence=selected,
            known_unknown=bool(items) and not available,
            conflicting=conflicting,
        )
        has_conflict = has_conflict or conflicting

    reasons = frozenset({ReviewReason.CONFLICTING_EVIDENCE}) if has_conflict else frozenset()
    return ActiveEvidenceView(slots=slots, review_reasons=reasons)


class _AnswerState(StrEnum):
    MISSING = "MISSING"
    AVAILABLE = "AVAILABLE"
    CONFIRMED_UNKNOWN = "CONFIRMED_UNKNOWN"


@dataclass(frozen=True)
class _ReadinessRow:
    slot: str
    reason: str
    core: bool


_READINESS_ROWS = (
    _ReadinessRow("transaction.reference", "定位同一笔交易", True),
    _ReadinessRow("transaction.occurred_at", "对齐订单、回调和风控时间线", True),
    _ReadinessRow("context.environment", "区分配置与凭据环境", True),
    _ReadinessRow("symptom.signal", "确认可观察症状", True),
    _ReadinessRow("integration.type", "决定后续条件槽位", False),
    _ReadinessRow("integration.platform", "确定插件上下文", False),
    _ReadinessRow("integration.plugin_version", "排查版本差异", False),
)
_SYMPTOM_CODES = (
    EvidenceCode.SYMPTOM_STATUS,
    EvidenceCode.SYMPTOM_ERROR_CODE,
    EvidenceCode.AUTHENTICATION_STATUS,
    EvidenceCode.AUTHENTICATION_RESULT_CODE,
    EvidenceCode.CALLBACK_DELIVERY_STATUS,
    EvidenceCode.RISK_DECISION_CODE,
    EvidenceCode.CONFIGURATION_CHECK_RESULT,
)


def _slot_state(slot: ActiveEvidenceSlot) -> _AnswerState:
    if slot.selected_evidence is not None or slot.conflicting:
        return _AnswerState.AVAILABLE
    if slot.known_unknown:
        return _AnswerState.CONFIRMED_UNKNOWN
    return _AnswerState.MISSING


def _symptom_state(view: ActiveEvidenceView) -> _AnswerState:
    symptom_slots = tuple(view.slots[code] for code in _SYMPTOM_CODES)
    if any(slot.selected_evidence is not None or slot.conflicting for slot in symptom_slots):
        return _AnswerState.AVAILABLE
    if all(slot.known_unknown for slot in symptom_slots):
        return _AnswerState.CONFIRMED_UNKNOWN
    return _AnswerState.MISSING


def _row_state(view: ActiveEvidenceView, row: _ReadinessRow) -> _AnswerState:
    if row.slot == "symptom.signal":
        return _symptom_state(view)
    return _slot_state(view.slots[EvidenceCode(row.slot)])


def assess_readiness(view: ActiveEvidenceView) -> ReadinessAssessment:
    integration = view.slots[EvidenceCode.INTEGRATION_TYPE]
    plugin_active = (
        not integration.conflicting
        and integration.selected_evidence is not None
        and integration.selected_evidence.typed_value == "PLUGIN"
    )
    active_rows = _READINESS_ROWS if plugin_active else _READINESS_ROWS[:5]
    states = tuple((row, _row_state(view, row)) for row in active_rows)
    unanswered = tuple(row for row, state in states if state is _AnswerState.MISSING)
    missing_fields = tuple(
        sorted(
            row.slot
            for row, state in states
            if state is _AnswerState.MISSING
            or (row.core and state is _AnswerState.CONFIRMED_UNKNOWN)
        )
    )
    known_unknown_fields = tuple(
        sorted(
            row.slot
            for row, state in states
            if not row.core and state is _AnswerState.CONFIRMED_UNKNOWN
        )
    )

    answered_count = sum(state is not _AnswerState.MISSING for _, state in states)
    completion_ratio = (Decimal(answered_count) / Decimal(len(active_rows))).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )
    has_core_unknown = any(
        row.core and state is _AnswerState.CONFIRMED_UNKNOWN for row, state in states
    )
    if unanswered:
        stop_reason = StopReason.NEED_MORE_EVIDENCE
    elif has_core_unknown:
        stop_reason = StopReason.CONFIRMED_UNKNOWN
    else:
        stop_reason = StopReason.READY

    next_row = unanswered[0] if unanswered else None
    return ReadinessAssessment(
        ready=stop_reason is StopReason.READY,
        missing_fields=missing_fields,
        known_unknown_fields=known_unknown_fields,
        next_question=next_row.slot if next_row else None,
        question_reason=next_row.reason if next_row else None,
        target_role=TargetRole.MERCHANT_TECH if next_row else None,
        completion_ratio=completion_ratio,
        stop_reason=stop_reason,
    )
