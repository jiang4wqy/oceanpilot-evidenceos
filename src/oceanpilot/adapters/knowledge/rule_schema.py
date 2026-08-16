"""SQLite schema for the read-only card-scheme rule catalog prototype."""

RULE_SCHEMA_VERSION = 2

RULE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rule_documents (
    document_id TEXT NOT NULL PRIMARY KEY,
    scheme TEXT NOT NULL CHECK (scheme IN ('VISA', 'MASTERCARD', 'AMEX', 'OCEANPAYMENT')),
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
    publisher TEXT NOT NULL CHECK (length(publisher) BETWEEN 1 AND 120),
    source_url TEXT NOT NULL CHECK (length(source_url) BETWEEN 1 AND 1000),
    source_version TEXT
);

CREATE TABLE IF NOT EXISTS rule_versions (
    rule_version_id TEXT NOT NULL PRIMARY KEY,
    document_id TEXT NOT NULL,
    scheme_reason_code TEXT NOT NULL CHECK (length(scheme_reason_code) BETWEEN 1 AND 64),
    display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 300),
    category TEXT NOT NULL CHECK (length(category) BETWEEN 1 AND 120),
    region TEXT NOT NULL CHECK (length(region) BETWEEN 1 AND 64),
    version_label TEXT,
    source_section TEXT,
    effective_date TEXT,
    internal_reason_code TEXT,
    demo_role TEXT NOT NULL CHECK (demo_role IN ('DEMO_MAPPED', 'DISPLAY_ONLY')),
    internal_window_days INTEGER CHECK (
        internal_window_days IS NULL OR internal_window_days BETWEEN 1 AND 120
    ),
    verification_status TEXT NOT NULL CHECK (
        verification_status IN ('UNVERIFIED_SUMMARY', 'VERIFIED_SOURCE', 'SUPERSEDED')
    ),
    limitation TEXT NOT NULL CHECK (length(limitation) BETWEEN 1 AND 1000),
    FOREIGN KEY (document_id) REFERENCES rule_documents(document_id),
    UNIQUE (document_id, scheme_reason_code, region, version_label)
);

CREATE TABLE IF NOT EXISTS rule_requirements (
    requirement_id TEXT NOT NULL PRIMARY KEY,
    rule_version_id TEXT NOT NULL,
    requirement_type TEXT NOT NULL CHECK (requirement_type IN ('ASSERTION', 'EVIDENCE')),
    necessity TEXT NOT NULL CHECK (necessity IN ('REQUIRED', 'RECOMMENDED')),
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    description_zh TEXT NOT NULL CHECK (length(description_zh) BETWEEN 1 AND 1000),
    internal_evidence_code TEXT,
    FOREIGN KEY (rule_version_id) REFERENCES rule_versions(rule_version_id),
    UNIQUE (rule_version_id, requirement_type, sequence)
);
"""

RULE_REQUIRED_TABLES = frozenset(
    {
        "rule_documents",
        "rule_versions",
        "rule_requirements",
    }
)
