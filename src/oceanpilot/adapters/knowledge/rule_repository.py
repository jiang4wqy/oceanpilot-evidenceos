"""SQLite-backed card-scheme rule catalog and package lookup adapter."""

import sqlite3
from collections.abc import Callable
from pathlib import Path

from oceanpilot.adapters.knowledge.bank_rules import InMemoryBankRules
from oceanpilot.adapters.knowledge.rule_schema import (
    RULE_REQUIRED_TABLES,
    RULE_SCHEMA_SQL,
    RULE_SCHEMA_VERSION,
)
from oceanpilot.adapters.knowledge.rule_seed import (
    RULE_DOCUMENT_SEEDS,
    RULE_REQUIREMENT_SEEDS,
    RULE_VERSION_SEEDS,
)
from oceanpilot.adapters.persistence.sqlite import connect_sqlite, immediate_transaction
from oceanpilot.application.errors import DatabaseUnavailable, PersistenceInvariantViolation
from oceanpilot.application.knowledge_base import (
    BankRuleEntry,
    RuleCatalogItem,
    RuleDetail,
    RuleDocument,
    RuleRequirement,
)
from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode

_DEMO_MAPPED = "DEMO_MAPPED"
_ASSERTION = "ASSERTION"
_EVIDENCE = "EVIDENCE"
_REQUIRED = "REQUIRED"
_SCHEMES = frozenset({"VISA", "MASTERCARD", "AMEX", "OCEANPAYMENT"})
_DEMO_ROLES = frozenset({_DEMO_MAPPED, "DISPLAY_ONLY"})
_VERIFICATION_STATUSES = frozenset({"UNVERIFIED_SUMMARY", "VERIFIED_SOURCE", "SUPERSEDED"})
_REQUIREMENT_TYPES = frozenset({_ASSERTION, _EVIDENCE})
_NECESSITIES = frozenset({_REQUIRED, "RECOMMENDED"})


def _require_text(raw: object) -> str:
    if type(raw) is not str:
        raise PersistenceInvariantViolation()
    return raw


def _optional_text(raw: object) -> str | None:
    if raw is None:
        return None
    return _require_text(raw)


def _require_int(raw: object) -> int:
    if type(raw) is not int:
        raise PersistenceInvariantViolation()
    return raw


def _optional_int(raw: object) -> int | None:
    if raw is None:
        return None
    return _require_int(raw)


def _choice(raw: object, allowed: frozenset[str]) -> str:
    value = _require_text(raw)
    if value not in allowed:
        raise PersistenceInvariantViolation()
    return value


def _normalize_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _database_call[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (DatabaseUnavailable, PersistenceInvariantViolation):
        raise
    except sqlite3.Error:
        raise DatabaseUnavailable() from None
    except (ValueError, TypeError, KeyError, IndexError, UnicodeError, OverflowError):
        raise PersistenceInvariantViolation() from None


def _table_names(connection: sqlite3.Connection) -> frozenset[str]:
    return frozenset(
        _require_text(row["name"])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        )
    )


def _validate_rule_database(connection: sqlite3.Connection) -> None:
    if _table_names(connection) != RULE_REQUIRED_TABLES:
        raise DatabaseUnavailable()
    version_row = connection.execute("PRAGMA user_version").fetchone()
    if (
        version_row is None
        or type(version_row[0]) is not int
        or version_row[0] != RULE_SCHEMA_VERSION
    ):
        raise DatabaseUnavailable()
    for table in RULE_REQUIRED_TABLES:
        connection.execute(f"SELECT * FROM {table} LIMIT 0").fetchone()
    quick_check = connection.execute("PRAGMA quick_check").fetchone()
    if quick_check is None or quick_check[0] != "ok":
        raise DatabaseUnavailable()
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise DatabaseUnavailable()


def _delete_unseeded_rows(connection: sqlite3.Connection) -> None:
    requirement_ids = tuple(seed.requirement_id for seed in RULE_REQUIREMENT_SEEDS)
    requirement_placeholders = ", ".join("?" for _ in requirement_ids)
    connection.execute(
        f"DELETE FROM rule_requirements WHERE requirement_id NOT IN ({requirement_placeholders})",
        requirement_ids,
    )

    rule_ids = tuple(seed.rule_version_id for seed in RULE_VERSION_SEEDS)
    rule_placeholders = ", ".join("?" for _ in rule_ids)
    connection.execute(
        f"DELETE FROM rule_versions WHERE rule_version_id NOT IN ({rule_placeholders})",
        rule_ids,
    )

    document_ids = tuple(seed.document_id for seed in RULE_DOCUMENT_SEEDS)
    document_placeholders = ", ".join("?" for _ in document_ids)
    connection.execute(
        f"DELETE FROM rule_documents WHERE document_id NOT IN ({document_placeholders})",
        document_ids,
    )


def _seed(connection: sqlite3.Connection) -> None:
    _delete_unseeded_rows(connection)
    for document in RULE_DOCUMENT_SEEDS:
        connection.execute(
            """
            INSERT INTO rule_documents (
                document_id, scheme, title, publisher, source_url, source_version
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                scheme = excluded.scheme,
                title = excluded.title,
                publisher = excluded.publisher,
                source_url = excluded.source_url,
                source_version = excluded.source_version
            """,
            (
                document.document_id,
                document.scheme,
                document.title,
                document.publisher,
                document.source_url,
                document.source_version,
            ),
        )
    for rule in RULE_VERSION_SEEDS:
        connection.execute(
            """
            INSERT INTO rule_versions (
                rule_version_id, document_id, scheme_reason_code, display_name,
                category, region, version_label, source_section, effective_date,
                internal_reason_code, demo_role, internal_window_days,
                verification_status, limitation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_version_id) DO UPDATE SET
                document_id = excluded.document_id,
                scheme_reason_code = excluded.scheme_reason_code,
                display_name = excluded.display_name,
                category = excluded.category,
                region = excluded.region,
                version_label = excluded.version_label,
                source_section = excluded.source_section,
                effective_date = excluded.effective_date,
                internal_reason_code = excluded.internal_reason_code,
                demo_role = excluded.demo_role,
                internal_window_days = excluded.internal_window_days,
                verification_status = excluded.verification_status,
                limitation = excluded.limitation
            """,
            (
                rule.rule_version_id,
                rule.document_id,
                rule.scheme_reason_code,
                rule.display_name,
                rule.category,
                rule.region,
                rule.version_label,
                rule.source_section,
                rule.effective_date,
                rule.internal_reason_code,
                rule.demo_role,
                rule.internal_window_days,
                rule.verification_status,
                rule.limitation,
            ),
        )
    for requirement in RULE_REQUIREMENT_SEEDS:
        connection.execute(
            """
            INSERT INTO rule_requirements (
                requirement_id, rule_version_id, requirement_type, necessity,
                sequence, description_zh, internal_evidence_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(requirement_id) DO UPDATE SET
                rule_version_id = excluded.rule_version_id,
                requirement_type = excluded.requirement_type,
                necessity = excluded.necessity,
                sequence = excluded.sequence,
                description_zh = excluded.description_zh,
                internal_evidence_code = excluded.internal_evidence_code
            """,
            (
                requirement.requirement_id,
                requirement.rule_version_id,
                requirement.requirement_type,
                requirement.necessity,
                requirement.sequence,
                requirement.description_zh,
                requirement.internal_evidence_code,
            ),
        )


def initialize_rule_database(path: Path) -> None:
    """Create and deterministically seed the dedicated rules database."""

    connection: sqlite3.Connection | None = None
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect_sqlite(path)
        existing_tables = _table_names(connection)
        if not existing_tables.issubset(RULE_REQUIRED_TABLES):
            raise DatabaseUnavailable()
        version_row = connection.execute("PRAGMA user_version").fetchone()
        if version_row is None:
            raise DatabaseUnavailable()
        schema_version = _require_int(version_row[0])
        if schema_version not in (0, 1, RULE_SCHEMA_VERSION):
            raise DatabaseUnavailable()
        if schema_version == 1:
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                DROP TABLE IF EXISTS rule_requirements;
                DROP TABLE IF EXISTS rule_versions;
                DROP TABLE IF EXISTS rule_documents;
                COMMIT;
                """
            )
        connection.executescript(f"BEGIN IMMEDIATE;\n{RULE_SCHEMA_SQL}\nCOMMIT;")
        with immediate_transaction(connection):
            _seed(connection)
            connection.execute(f"PRAGMA user_version={RULE_SCHEMA_VERSION}")

        _validate_rule_database(connection)
        if (
            connection.execute("SELECT COUNT(*) FROM rule_documents").fetchone()[0]
            != len(RULE_DOCUMENT_SEEDS)
            or connection.execute("SELECT COUNT(*) FROM rule_versions").fetchone()[0]
            != len(RULE_VERSION_SEEDS)
            or connection.execute("SELECT COUNT(*) FROM rule_requirements").fetchone()[0]
            != len(RULE_REQUIREMENT_SEEDS)
        ):
            raise DatabaseUnavailable()
    except (OSError, sqlite3.Error, DatabaseUnavailable, PersistenceInvariantViolation):
        if connection is not None and connection.in_transaction:
            connection.execute("ROLLBACK")
        raise DatabaseUnavailable() from None
    finally:
        if connection is not None:
            connection.close()


def _decode_catalog_item(row: sqlite3.Row) -> RuleCatalogItem:
    return RuleCatalogItem(
        rule_version_id=_require_text(row["rule_version_id"]),
        document_id=_require_text(row["document_id"]),
        scheme=_choice(row["scheme"], _SCHEMES),
        scheme_reason_code=_require_text(row["scheme_reason_code"]),
        display_name=_require_text(row["display_name"]),
        category=_require_text(row["category"]),
        region=_require_text(row["region"]),
        version_label=_optional_text(row["version_label"]),
        demo_role=_choice(row["demo_role"], _DEMO_ROLES),
        verification_status=_choice(row["verification_status"], _VERIFICATION_STATUSES),
        source_document=_require_text(row["source_document"]),
        source_url=_require_text(row["source_url"]),
    )


def _decode_requirement(row: sqlite3.Row) -> RuleRequirement:
    return RuleRequirement(
        requirement_id=_require_text(row["requirement_id"]),
        requirement_type=_choice(row["requirement_type"], _REQUIREMENT_TYPES),
        necessity=_choice(row["necessity"], _NECESSITIES),
        sequence=_require_int(row["sequence"]),
        description_zh=_require_text(row["description_zh"]),
        internal_evidence_code=_optional_text(row["internal_evidence_code"]),
    )


_BASE_RULE_SELECT = """
SELECT
    rv.rule_version_id,
    rv.document_id,
    d.scheme,
    rv.scheme_reason_code,
    rv.display_name,
    rv.category,
    rv.region,
    rv.version_label,
    rv.demo_role,
    rv.verification_status,
    d.title AS source_document,
    d.source_url
FROM rule_versions AS rv
JOIN rule_documents AS d ON d.document_id = rv.document_id
"""


class SqliteRuleRepository:
    def __init__(
        self,
        path: Path,
        *,
        fallback: InMemoryBankRules | None = None,
    ) -> None:
        self._path = Path(path)
        self._fallback = fallback or InMemoryBankRules()

    def list_rules(
        self,
        *,
        scheme: str | None = None,
        query: str | None = None,
    ) -> tuple[RuleCatalogItem, ...]:
        def operation() -> tuple[RuleCatalogItem, ...]:
            clauses: list[str] = []
            parameters: list[str] = []
            if scheme is not None and scheme.strip():
                clauses.append("d.scheme = ?")
                parameters.append(scheme.strip().upper())
            if query is not None and query.strip():
                escaped = (
                    query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                pattern = f"%{escaped}%"
                clauses.append(
                    "(rv.scheme_reason_code LIKE ? ESCAPE '\\' "
                    "OR rv.display_name LIKE ? ESCAPE '\\' "
                    "OR rv.category LIKE ? ESCAPE '\\' "
                    "OR d.scheme LIKE ? ESCAPE '\\' "
                    "OR d.title LIKE ? ESCAPE '\\')"
                )
                parameters.extend((pattern,) * 5)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            connection = connect_sqlite(self._path)
            try:
                _validate_rule_database(connection)
                rows = connection.execute(
                    f"""
                    {_BASE_RULE_SELECT}
                    {where}
                    ORDER BY
                        CASE d.scheme
                            WHEN 'VISA' THEN 1
                            WHEN 'MASTERCARD' THEN 2
                            WHEN 'AMEX' THEN 3
                        END,
                        rv.scheme_reason_code,
                        rv.rule_version_id
                    """,
                    tuple(parameters),
                ).fetchall()
            finally:
                connection.close()
            return tuple(_decode_catalog_item(row) for row in rows)

        return _database_call(operation)

    def get_rule(self, rule_version_id: str) -> RuleDetail | None:
        def operation() -> RuleDetail | None:
            connection = connect_sqlite(self._path)
            try:
                _validate_rule_database(connection)
                row = connection.execute(
                    """
                    SELECT
                        rv.rule_version_id, rv.scheme_reason_code, rv.display_name,
                        rv.category, rv.region, rv.version_label, rv.source_section,
                        rv.effective_date, rv.internal_reason_code, rv.demo_role,
                        rv.internal_window_days, rv.verification_status, rv.limitation,
                        d.document_id, d.scheme, d.title, d.publisher, d.source_url,
                        d.source_version
                    FROM rule_versions AS rv
                    JOIN rule_documents AS d ON d.document_id = rv.document_id
                    WHERE rv.rule_version_id = ?
                    """,
                    (rule_version_id,),
                ).fetchone()
                if row is None:
                    return None
                requirement_rows = connection.execute(
                    """
                    SELECT requirement_id, requirement_type, necessity, sequence,
                           description_zh, internal_evidence_code
                    FROM rule_requirements
                    WHERE rule_version_id = ?
                    ORDER BY requirement_type, sequence, requirement_id
                    """,
                    (rule_version_id,),
                ).fetchall()
            finally:
                connection.close()

            requirements = tuple(_decode_requirement(item) for item in requirement_rows)
            assertions = tuple(item for item in requirements if item.requirement_type == _ASSERTION)
            evidence = tuple(item for item in requirements if item.requirement_type == _EVIDENCE)
            return RuleDetail(
                rule_version_id=_require_text(row["rule_version_id"]),
                scheme=_choice(row["scheme"], _SCHEMES),
                scheme_reason_code=_require_text(row["scheme_reason_code"]),
                display_name=_require_text(row["display_name"]),
                category=_require_text(row["category"]),
                region=_require_text(row["region"]),
                version_label=_optional_text(row["version_label"]),
                source_section=_optional_text(row["source_section"]),
                effective_date=_optional_text(row["effective_date"]),
                internal_reason_code=_optional_text(row["internal_reason_code"]),
                demo_role=_choice(row["demo_role"], _DEMO_ROLES),
                internal_window_days=_optional_int(row["internal_window_days"]),
                verification_status=_choice(row["verification_status"], _VERIFICATION_STATUSES),
                limitation=_require_text(row["limitation"]),
                document=RuleDocument(
                    document_id=_require_text(row["document_id"]),
                    scheme=_choice(row["scheme"], _SCHEMES),
                    title=_require_text(row["title"]),
                    publisher=_require_text(row["publisher"]),
                    source_url=_require_text(row["source_url"]),
                    source_version=_optional_text(row["source_version"]),
                ),
                assertions=assertions,
                evidence=evidence,
            )

        return _database_call(operation)

    def lookup(
        self,
        reason_code: DisputeReasonCode,
        *,
        bank_id: str | None = None,
        card_network: str | None = None,
    ) -> BankRuleEntry:
        def operation() -> BankRuleEntry:
            connection = connect_sqlite(self._path)
            try:
                _validate_rule_database(connection)
                normalized_bank_id = _normalize_identifier(bank_id)
                normalized_card_network = _normalize_identifier(card_network)
                fallback = self._fallback.lookup(
                    reason_code,
                    bank_id=normalized_bank_id,
                    card_network=normalized_card_network,
                )
                if fallback.source == "bank" or normalized_card_network is None:
                    return fallback
                mapped = self._lookup_demo_rule(
                    connection,
                    normalized_card_network,
                    reason_code,
                )
                return mapped if mapped is not None else fallback
            finally:
                connection.close()

        return _database_call(operation)

    def _lookup_demo_rule(
        self,
        connection: sqlite3.Connection,
        scheme: str,
        reason_code: DisputeReasonCode,
    ) -> BankRuleEntry | None:
        rows = connection.execute(
            """
            SELECT
                rv.rule_version_id, rv.scheme_reason_code, rv.display_name,
                rv.version_label, rv.source_section, rv.internal_window_days,
                rv.verification_status, rv.limitation, d.title AS source_document
            FROM rule_versions AS rv
            JOIN rule_documents AS d ON d.document_id = rv.document_id
            WHERE d.scheme = ?
              AND rv.internal_reason_code = ?
              AND rv.demo_role = 'DEMO_MAPPED'
            """,
            (scheme, reason_code.value),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise PersistenceInvariantViolation()
        row = rows[0]
        requirement_rows = connection.execute(
            """
            SELECT requirement_type, necessity, sequence, description_zh,
                   internal_evidence_code
            FROM rule_requirements
            WHERE rule_version_id = ?
            ORDER BY requirement_type, sequence
            """,
            (_require_text(row["rule_version_id"]),),
        ).fetchall()

        required_assertions: list[str] = []
        ordered_evidence: list[ChargebackEvidenceCode] = []
        for requirement in requirement_rows:
            requirement_type = _choice(requirement["requirement_type"], _REQUIREMENT_TYPES)
            necessity = _choice(requirement["necessity"], _NECESSITIES)
            if necessity != _REQUIRED:
                continue
            if requirement_type == _ASSERTION:
                required_assertions.append(_require_text(requirement["description_zh"]))
                continue
            evidence_code = _optional_text(requirement["internal_evidence_code"])
            if evidence_code is not None:
                ordered_evidence.append(ChargebackEvidenceCode(evidence_code))

        evidence_tuple = tuple(ordered_evidence)
        if not evidence_tuple or len(set(evidence_tuple)) != len(evidence_tuple):
            raise PersistenceInvariantViolation()
        window = _optional_int(row["internal_window_days"])
        if window is None:
            raise PersistenceInvariantViolation()
        return BankRuleEntry(
            reason_code=reason_code,
            required_evidence=evidence_tuple,
            template_order=evidence_tuple,
            submission_window_days=window,
            notes=(
                f"{scheme} {_require_text(row['scheme_reason_code'])} "
                f"{_require_text(row['display_name'])}（演示摘要）。"
            ),
            source="network-guidance",
            scheme_reason_code=_require_text(row["scheme_reason_code"]),
            rule_version=_optional_text(row["version_label"]),
            source_document=_require_text(row["source_document"]),
            source_section=_optional_text(row["source_section"]),
            required_assertions=tuple(required_assertions),
            limitation=_require_text(row["limitation"]),
            rule_version_id=_require_text(row["rule_version_id"]),
            verification_status=_choice(row["verification_status"], _VERIFICATION_STATUSES),
            submission_window_basis="INTERNAL_DEMO",
        )
