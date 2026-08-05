from datetime import datetime
from pathlib import Path

import pytest

from oceanpilot.domain.enums import (
    EvidenceAvailability,
    EvidenceCode,
    EvidenceValueType,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.evidence_policy import create_evidence_item
from oceanpilot.domain.models import EvidenceCreate, EvidenceItem, EvidenceOrigin


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "oceanpilot.db"


@pytest.fixture
def valid_evidence_item() -> EvidenceItem:
    observed = datetime.fromisoformat("2026-07-18T12:00:00+08:00")
    return EvidenceItem(
        case_id="00000000-0000-4000-8000-000000000010",
        evidence_id="00000000-0000-4000-8000-000000000011",
        schema_version="1",
        evidence_code=EvidenceCode.CONTEXT_ENVIRONMENT,
        availability=EvidenceAvailability.AVAILABLE,
        value_type=EvidenceValueType.STRING,
        typed_value="PROD",
        source_type=SourceType.SYNTHETIC_ADAPTER,
        source_ref="synthetic:fixture",
        source_reliability=SourceReliability.SYNTHETIC_TEST,
        observed_at=observed,
        collected_at=observed,
        synthetic=True,
        content_hash="0" * 64,
    )


@pytest.fixture
def evidence_factory():
    def make(
        *,
        code: str = "context.environment",
        value: str | bool | datetime = "PROD",
        evidence_id: str = "00000000-0000-4000-8000-000000000011",
        reliability: SourceReliability = SourceReliability.SYNTHETIC_TEST,
        availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE,
    ) -> EvidenceItem:
        request = EvidenceCreate(
            evidence_id=evidence_id,
            evidence_code=EvidenceCode(code),
            availability=availability,
            typed_value=(value if availability is EvidenceAvailability.AVAILABLE else None),
            observed_at=datetime.fromisoformat("2026-07-18T12:00:00+08:00"),
            source_ref="synthetic:fixture",
        )
        origin = EvidenceOrigin(
            source_type=SourceType.SYNTHETIC_ADAPTER,
            source_reliability=reliability,
            synthetic=True,
        )
        return create_evidence_item(
            request,
            case_id="00000000-0000-4000-8000-000000000010",
            origin=origin,
            collected_at=datetime.fromisoformat("2026-07-18T12:00:01+08:00"),
        )

    return make
