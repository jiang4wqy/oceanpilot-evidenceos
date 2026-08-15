import sqlite3
from pathlib import Path

import pytest

from oceanpilot.adapters.knowledge.rule_repository import (
    SqliteRuleRepository,
    initialize_rule_database,
)
from oceanpilot.adapters.persistence.sqlite import connect_sqlite
from oceanpilot.application.errors import DatabaseUnavailable
from oceanpilot.application.knowledge_base import KnowledgeBase, RuleCatalog
from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode


@pytest.fixture
def rules_path(tmp_path: Path) -> Path:
    path = tmp_path / "oceanpilot-rules.db"
    initialize_rule_database(path)
    return path


@pytest.fixture
def repository(rules_path: Path) -> SqliteRuleRepository:
    return SqliteRuleRepository(rules_path)


def test_initializer_creates_three_versioned_seed_tables(rules_path: Path) -> None:
    connection = connect_sqlite(rules_path)
    try:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert tables == {"rule_documents", "rule_versions", "rule_requirements"}
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM rule_documents").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM rule_versions").fetchone()[0] == 9
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM rule_versions WHERE demo_role = 'DEMO_MAPPED'"
            ).fetchone()[0]
            == 3
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchone() is None
    finally:
        connection.close()


def test_initializer_is_idempotent(rules_path: Path) -> None:
    initialize_rule_database(rules_path)
    connection = connect_sqlite(rules_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM rule_documents").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM rule_versions").fetchone()[0] == 9
        requirement_count = connection.execute("SELECT COUNT(*) FROM rule_requirements").fetchone()[
            0
        ]
        assert requirement_count > 20
    finally:
        connection.close()


def test_initializer_exactly_resynchronizes_stable_seed_ids(rules_path: Path) -> None:
    connection = sqlite3.connect(rules_path)
    baseline_requirement_count = connection.execute(
        "SELECT COUNT(*) FROM rule_requirements"
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO rule_documents VALUES (?, ?, ?, ?, ?, ?)",
        (
            "stale-document",
            "VISA",
            "Stale document",
            "Stale publisher",
            "https://example.com/stale",
            None,
        ),
    )
    connection.execute(
        "INSERT INTO rule_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "stale-rule",
            "stale-document",
            "99.9",
            "Stale rule",
            "STALE",
            "GLOBAL",
            "v0",
            None,
            None,
            None,
            "DISPLAY_ONLY",
            None,
            "UNVERIFIED_SUMMARY",
            "Stale rule must be removed.",
        ),
    )
    connection.execute(
        "INSERT INTO rule_requirements VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("stale-requirement", "stale-rule", "ASSERTION", "REQUIRED", 1, "Stale", None),
    )
    connection.execute(
        "INSERT INTO rule_requirements VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "rogue-requirement",
            "visa-13-1-demo-v1",
            "EVIDENCE",
            "REQUIRED",
            99,
            "Rogue evidence",
            "auth.threeds",
        ),
    )
    connection.commit()
    connection.close()

    initialize_rule_database(rules_path)

    connection = sqlite3.connect(rules_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM rule_documents").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM rule_versions").fetchone()[0] == 9
        assert (
            connection.execute("SELECT COUNT(*) FROM rule_requirements").fetchone()[0]
            == baseline_requirement_count
        )
    finally:
        connection.close()

    repository = SqliteRuleRepository(rules_path)
    assert repository.get_rule("stale-rule") is None
    entry = repository.lookup(
        DisputeReasonCode.PRODUCT_NOT_RECEIVED,
        card_network="VISA",
    )
    assert ChargebackEvidenceCode.THREEDS_AUTHENTICATION not in entry.required_evidence


def test_initializer_rejects_a_non_rule_database_without_mutating_it(tmp_path: Path) -> None:
    path = tmp_path / "wrong.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE existing_business_data (value TEXT NOT NULL)")
    connection.close()

    with pytest.raises(DatabaseUnavailable):
        initialize_rule_database(path)

    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert tables == {"existing_business_data"}
    finally:
        connection.close()


def test_repository_satisfies_both_read_ports(repository: SqliteRuleRepository) -> None:
    assert isinstance(repository, KnowledgeBase)
    assert isinstance(repository, RuleCatalog)


def test_catalog_lists_nine_rules_and_filters_without_fake_rows(
    repository: SqliteRuleRepository,
) -> None:
    all_rules = repository.list_rules()
    assert len(all_rules) == 9
    assert sum(rule.demo_role == "DEMO_MAPPED" for rule in all_rules) == 3
    assert {rule.scheme for rule in all_rules} == {"VISA", "MASTERCARD", "AMEX"}
    assert len({rule.document_id for rule in all_rules}) == 3

    visa = repository.list_rules(scheme="visa")
    assert len(visa) == 6
    assert all(rule.scheme == "VISA" for rule in visa)

    searched = repository.list_rules(query="10.4")
    assert [rule.scheme_reason_code for rule in searched] == ["10.4"]
    assert repository.list_rules(query="not-present-in-seed") == ()


def test_catalog_detail_preserves_source_and_requirement_order(
    repository: SqliteRuleRepository,
) -> None:
    detail = repository.get_rule("visa-10-4-demo-v1")
    assert detail is not None
    assert detail.scheme == "VISA"
    assert detail.scheme_reason_code == "10.4"
    assert detail.source_section.startswith("Condition 10.4")
    assert detail.document.title == "Dispute Management Guidelines for Visa Merchants"
    assert detail.document.source_url.startswith("https://")
    assert detail.verification_status == "UNVERIFIED_SUMMARY"
    assert detail.demo_role == "DEMO_MAPPED"
    assert [item.sequence for item in detail.assertions] == sorted(
        item.sequence for item in detail.assertions
    )
    assert [item.sequence for item in detail.evidence] == sorted(
        item.sequence for item in detail.evidence
    )
    assert detail.evidence[0].internal_evidence_code is not None
    assert repository.get_rule("not-a-rule") is None


def test_demo_mapped_rule_drives_existing_bank_rule_entry(repository: SqliteRuleRepository) -> None:
    entry = repository.lookup(
        DisputeReasonCode.FRAUD_CARD_NOT_PRESENT,
        card_network="VISA",
    )
    assert entry.rule_version_id == "visa-10-4-demo-v1"
    assert entry.scheme_reason_code == "10.4"
    assert entry.verification_status == "UNVERIFIED_SUMMARY"
    assert entry.submission_window_basis == "INTERNAL_DEMO"
    assert entry.template_order == (
        ChargebackEvidenceCode.THREEDS_AUTHENTICATION,
        ChargebackEvidenceCode.DEVICE_OR_IP_MATCH,
        ChargebackEvidenceCode.PRIOR_TRANSACTION_HISTORY,
        ChargebackEvidenceCode.TRANSACTION_RECEIPT,
    )


def test_bank_override_wins_before_database_network_rule(repository: SqliteRuleRepository) -> None:
    entry = repository.lookup(
        DisputeReasonCode.PRODUCT_NOT_RECEIVED,
        bank_id="ACME_BANK",
        card_network="VISA",
    )
    assert entry.source == "bank"
    assert entry.rule_version_id is None
    assert entry.submission_window_days == 12


def test_lookup_normalizes_identifiers_before_resolving_priority(
    repository: SqliteRuleRepository,
) -> None:
    bank_entry = repository.lookup(
        DisputeReasonCode.PRODUCT_NOT_RECEIVED,
        bank_id=" acme_bank ",
        card_network=" visa ",
    )
    assert bank_entry.source == "bank"

    network_entry = repository.lookup(
        DisputeReasonCode.CREDIT_NOT_PROCESSED,
        card_network=" visa ",
    )
    assert network_entry.source == "network"


def test_display_only_rule_never_drives_package(repository: SqliteRuleRepository) -> None:
    entry = repository.lookup(
        DisputeReasonCode.CREDIT_NOT_PROCESSED,
        card_network="VISA",
    )
    assert entry.source == "network"
    assert entry.rule_version_id is None


def test_unknown_match_uses_existing_internal_default(repository: SqliteRuleRepository) -> None:
    entry = repository.lookup(
        DisputeReasonCode.AUTHORIZATION_ERROR,
        card_network="MASTERCARD",
    )
    assert entry.source == "default"
    assert entry.rule_version_id is None


def test_sqlite_failure_is_not_silently_treated_as_a_rule_miss(rules_path: Path) -> None:
    repository = SqliteRuleRepository(rules_path)
    connection = sqlite3.connect(rules_path)
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute("DROP TABLE rule_requirements")
    connection.close()

    with pytest.raises(DatabaseUnavailable):
        repository.lookup(
            DisputeReasonCode.FRAUD_CARD_NOT_PRESENT,
            card_network="VISA",
        )
    connection = sqlite3.connect(rules_path)
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute("DROP TABLE rule_versions")
    connection.close()
    with pytest.raises(DatabaseUnavailable):
        repository.list_rules()


def test_missing_required_table_fails_before_catalog_miss_or_fallback(
    rules_path: Path,
) -> None:
    repository = SqliteRuleRepository(rules_path)
    connection = sqlite3.connect(rules_path)
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute("DROP TABLE rule_requirements")
    connection.close()

    with pytest.raises(DatabaseUnavailable):
        repository.list_rules()
    with pytest.raises(DatabaseUnavailable):
        repository.get_rule("not-a-rule")
    with pytest.raises(DatabaseUnavailable):
        repository.lookup(
            DisputeReasonCode.AUTHORIZATION_ERROR,
            card_network="MASTERCARD",
        )
