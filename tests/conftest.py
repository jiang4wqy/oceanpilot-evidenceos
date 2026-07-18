from datetime import datetime

import pytest

from oceanpilot.domain.enums import (
    EvidenceAvailability,
    EvidenceCode,
    EvidenceValueType,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.models import EvidenceItem


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
