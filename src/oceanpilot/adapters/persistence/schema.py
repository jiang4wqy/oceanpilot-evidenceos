SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT NOT NULL PRIMARY KEY,
    case_type TEXT NOT NULL CHECK (case_type = 'PAYMENT_INCIDENT'),
    status TEXT NOT NULL CHECK (
        status IN ('NEW','NEED_INFO','EVIDENCE_READY','DIAGNOSED','HUMAN_REVIEW')
    ),
    schema_version TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 0),
    evidence_revision INTEGER NOT NULL CHECK (evidence_revision >= 0),
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    summary TEXT NOT NULL CHECK (length(summary) BETWEEN 1 AND 500),
    merchant_ref TEXT NOT NULL CHECK (length(merchant_ref) BETWEEN 1 AND 128),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    current_diagnosis_id TEXT,
    readiness_json TEXT NOT NULL,
    FOREIGN KEY (case_id, current_diagnosis_id)
        REFERENCES diagnosis_snapshots(case_id, diagnosis_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS evidence_items (
    case_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    evidence_code TEXT NOT NULL,
    availability TEXT NOT NULL CHECK (availability IN ('AVAILABLE','CONFIRMED_UNAVAILABLE')),
    value_type TEXT NOT NULL,
    typed_value_json TEXT,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_reliability TEXT NOT NULL,
    observed_at TEXT,
    collected_at TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    PRIMARY KEY (case_id, evidence_id),
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE TABLE IF NOT EXISTS diagnosis_snapshots (
    case_id TEXT NOT NULL,
    diagnosis_id TEXT NOT NULL,
    evidence_revision INTEGER NOT NULL CHECK (evidence_revision >= 0),
    policy_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('CURRENT','SUPERSEDED')),
    routing_json TEXT,
    ticket_json TEXT,
    requires_human INTEGER NOT NULL CHECK (requires_human IN (0,1)),
    review_reasons_json TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    created_at TEXT NOT NULL,
    PRIMARY KEY (case_id, diagnosis_id),
    UNIQUE (case_id, evidence_revision, policy_version),
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE TABLE IF NOT EXISTS hypotheses (
    case_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    diagnosis_id TEXT NOT NULL,
    cause_code TEXT NOT NULL,
    explanation TEXT NOT NULL,
    confidence_score REAL NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
    confidence_method TEXT NOT NULL CHECK (confidence_method = 'HEURISTIC_V1'),
    next_verification_action TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    PRIMARY KEY (case_id, hypothesis_id),
    UNIQUE (case_id, diagnosis_id, rule_id),
    FOREIGN KEY (case_id, diagnosis_id)
        REFERENCES diagnosis_snapshots(case_id, diagnosis_id)
);

CREATE TABLE IF NOT EXISTS hypothesis_evidence_refs (
    case_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (case_id, hypothesis_id, evidence_id),
    FOREIGN KEY (case_id, hypothesis_id)
        REFERENCES hypotheses(case_id, hypothesis_id),
    FOREIGN KEY (case_id, evidence_id)
        REFERENCES evidence_items(case_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    case_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_version TEXT NOT NULL,
    request_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 0),
    evidence_revision INTEGER NOT NULL CHECK (evidence_revision >= 0),
    occurred_at TEXT NOT NULL,
    result TEXT NOT NULL,
    reason_code TEXT,
    sanitized_metadata_json TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    PRIMARY KEY (case_id, event_id),
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);
"""

REQUIRED_TABLES = frozenset(
    {
        "audit_events",
        "cases",
        "diagnosis_snapshots",
        "evidence_items",
        "hypotheses",
        "hypothesis_evidence_refs",
    }
)
