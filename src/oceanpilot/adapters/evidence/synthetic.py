from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from oceanpilot.domain.enums import (
    EvidenceAvailability,
    EvidenceCode,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.models import EvidenceCreate, EvidenceOrigin

_OBSERVED_AT: Final = datetime(2026, 8, 5, 4, 0, tzinfo=UTC)


class SyntheticScenario(StrEnum):
    THREEDS_INCOMPLETE = "THREEDS_INCOMPLETE"
    RISK_DECLINE = "RISK_DECLINE"
    CONFIG_MERCHANT = "CONFIG_MERCHANT"
    CONFIG_PSP = "CONFIG_PSP"


_SCENARIO_SEQUENCE: Final = {
    SyntheticScenario.THREEDS_INCOMPLETE: 1,
    SyntheticScenario.RISK_DECLINE: 2,
    SyntheticScenario.CONFIG_MERCHANT: 3,
    SyntheticScenario.CONFIG_PSP: 4,
}

_SCENARIO_FACTS: Final = {
    SyntheticScenario.THREEDS_INCOMPLETE: (
        (EvidenceCode.TRANSACTION_REFERENCE, "txn_threeds_001"),
        (EvidenceCode.TRANSACTION_OCCURRED_AT, _OBSERVED_AT),
        (EvidenceCode.CONTEXT_ENVIRONMENT, "PROD"),
        (EvidenceCode.SYMPTOM_STATUS, "PENDING"),
        (EvidenceCode.INTEGRATION_TYPE, "API"),
        (EvidenceCode.AUTHENTICATION_STATUS, "REQUIRED"),
        (EvidenceCode.CALLBACK_DELIVERY_STATUS, "NOT_RECEIVED"),
    ),
    SyntheticScenario.RISK_DECLINE: (
        (EvidenceCode.TRANSACTION_REFERENCE, "txn_risk_001"),
        (EvidenceCode.TRANSACTION_OCCURRED_AT, _OBSERVED_AT),
        (EvidenceCode.CONTEXT_ENVIRONMENT, "PROD"),
        (EvidenceCode.SYMPTOM_STATUS, "DECLINED"),
        (EvidenceCode.INTEGRATION_TYPE, "API"),
        (EvidenceCode.RISK_DECISION_CODE, "RISK_DECLINE"),
    ),
    SyntheticScenario.CONFIG_MERCHANT: (
        (EvidenceCode.TRANSACTION_REFERENCE, "txn_config_merchant_001"),
        (EvidenceCode.TRANSACTION_OCCURRED_AT, _OBSERVED_AT),
        (EvidenceCode.CONTEXT_ENVIRONMENT, "PROD"),
        (EvidenceCode.SYMPTOM_STATUS, "FAILED"),
        (EvidenceCode.INTEGRATION_TYPE, "API"),
        (EvidenceCode.PAYMENT_METHOD, "CARD"),
        (EvidenceCode.CONFIGURATION_CHECK_RESULT, "MERCHANT_SIDE_MISMATCH"),
    ),
    SyntheticScenario.CONFIG_PSP: (
        (EvidenceCode.TRANSACTION_REFERENCE, "txn_config_psp_001"),
        (EvidenceCode.TRANSACTION_OCCURRED_AT, _OBSERVED_AT),
        (EvidenceCode.CONTEXT_ENVIRONMENT, "PROD"),
        (EvidenceCode.SYMPTOM_STATUS, "FAILED"),
        (EvidenceCode.INTEGRATION_TYPE, "API"),
        (EvidenceCode.PAYMENT_METHOD, "CARD"),
        (EvidenceCode.CONFIGURATION_CHECK_RESULT, "PSP_PROFILE_MISMATCH"),
    ),
}


class SyntheticEvidenceSource:
    origin: Final = EvidenceOrigin(
        source_type=SourceType.SYNTHETIC_ADAPTER,
        source_reliability=SourceReliability.SYNTHETIC_TEST,
        synthetic=True,
    )

    def load(self, scenario: SyntheticScenario) -> tuple[EvidenceCreate, ...]:
        if type(scenario) is not SyntheticScenario:
            raise TypeError("scenario must be a SyntheticScenario")
        sequence = _SCENARIO_SEQUENCE[scenario]
        return tuple(
            EvidenceCreate(
                evidence_id=(
                    f"00000000-0000-4000-8000-{sequence * 100 + index:012d}"
                ),
                evidence_code=code,
                availability=EvidenceAvailability.AVAILABLE,
                typed_value=value,
                observed_at=_OBSERVED_AT,
                source_ref=(
                    f"synthetic:oceanpilot:{scenario.value.lower()}:{code.value}"
                ),
            )
            for index, (code, value) in enumerate(_SCENARIO_FACTS[scenario], start=1)
        )
