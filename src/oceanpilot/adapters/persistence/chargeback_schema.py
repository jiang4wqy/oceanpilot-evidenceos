"""Durable schema for the chargeback agent cluster.

Kept in its own database file (separate from the foundation ``cases`` schema) so
the chargeback storage boundary can evolve independently and own its persistence
file, per the T9 issue. All rows are synthetic-only (``synthetic = 1``).
"""

CHARGEBACK_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chargeback_cases (
    case_id TEXT NOT NULL PRIMARY KEY,
    reason_code TEXT,
    card_network TEXT CHECK (card_network IN ('VISA', 'MASTERCARD', 'AMEX')),
    reason_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (reason_confirmed IN (0, 1)),
    collection_finalized INTEGER NOT NULL DEFAULT 0 CHECK (collection_finalized IN (0, 1)),
    revision INTEGER NOT NULL CHECK (revision >= 0),
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chargeback_evidence (
    case_id TEXT NOT NULL,
    evidence_code TEXT NOT NULL,
    added_at TEXT NOT NULL,
    added_at_revision INTEGER NOT NULL CHECK (added_at_revision >= 1),
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    PRIMARY KEY (case_id, evidence_code),
    FOREIGN KEY (case_id) REFERENCES chargeback_cases(case_id)
);

CREATE TABLE IF NOT EXISTS chargeback_audit (
    case_id TEXT NOT NULL,
    seq INTEGER NOT NULL CHECK (seq >= 0),
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'CASE_OPENED','REASON_CLASSIFIED','REASON_CONFIRMED','CARD_NETWORK_SELECTED',
            'EVIDENCE_ADDED','EVIDENCE_WITHDRAWN','COLLECTION_FINALIZED'
        )
    ),
    detail TEXT,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 0),
    occurred_at TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    PRIMARY KEY (case_id, seq),
    FOREIGN KEY (case_id) REFERENCES chargeback_cases(case_id)
);

CREATE TABLE IF NOT EXISTS chargeback_agent_turns (
    turn_id TEXT NOT NULL PRIMARY KEY,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 0),
    trigger TEXT NOT NULL,
    response_json TEXT NOT NULL,
    proposal_json TEXT,
    created_at TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    FOREIGN KEY (case_id) REFERENCES chargeback_cases(case_id)
);

CREATE INDEX IF NOT EXISTS idx_chargeback_agent_turns_case_revision
ON chargeback_agent_turns(case_id, case_revision, created_at);

CREATE TABLE IF NOT EXISTS chargeback_review_decisions (
    decision_id TEXT NOT NULL PRIMARY KEY,
    case_id TEXT NOT NULL,
    source_turn_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('NEEDS_MORE_INFO', 'APPROVED', 'REJECTED')),
    summary TEXT NOT NULL,
    confirmed_materials_json TEXT NOT NULL,
    citation_ids_json TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    confirmed_by TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    audit_event_id TEXT NOT NULL UNIQUE,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    FOREIGN KEY (case_id) REFERENCES chargeback_cases(case_id),
    FOREIGN KEY (source_turn_id) REFERENCES chargeback_agent_turns(turn_id)
);

CREATE TABLE IF NOT EXISTS chargeback_review_audit (
    audit_event_id TEXT NOT NULL PRIMARY KEY,
    case_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type = 'REVIEW_DECISION_CONFIRMED'),
    decision_id TEXT NOT NULL UNIQUE,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 1),
    occurred_at TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    FOREIGN KEY (case_id) REFERENCES chargeback_cases(case_id),
    FOREIGN KEY (decision_id) REFERENCES chargeback_review_decisions(decision_id)
);
"""

CHARGEBACK_REQUIRED_TABLES = frozenset(
    {
        "chargeback_cases",
        "chargeback_evidence",
        "chargeback_audit",
        "chargeback_agent_turns",
        "chargeback_review_decisions",
        "chargeback_review_audit",
    }
)
