"""The uploaded extraction corpus remains reference knowledge, not live cases."""

import json
from importlib.resources import files
from pathlib import Path

import pytest

from oceanpilot.adapters.knowledge.dispute_case_library import CaseLibraryError, DisputeCaseLibrary


@pytest.fixture
def library():
    return DisputeCaseLibrary()


def test_uploaded_inventory_counts_records_not_highest_identifier(library):
    manifest = library.manifest()
    assert manifest["case_count"] == 62
    assert manifest["rule_group_count"] == 35
    assert manifest["sandbox_template_count"] == 28
    assert manifest["source_count"] == 3
    assert manifest["evidence_levels"] == {
        "SOURCE_EXPLICIT": 34,
        "RULE_DERIVED": 13,
        "SYNTHETIC_DEMO": 15,
    }
    assert manifest["verification_statuses"] == {
        "VERIFIED_EXTRACTED": 16,
        "CONFLICTING_SOURCES": 16,
        "NEEDS_CONFIRMATION": 30,
    }
    assert manifest["conflict_count"] == 15
    assert manifest["data_gap_count"] == 10
    assert manifest["files"][0]["sha256"] == (
        "bef3c63f67052d83829a0aa27158d53dc69fa34e7c977bd97cf7c37ab247be9d"
    )
    assert library.get_reference("CB-CASE-074") is not None
    assert library.get_reference("CB-CASE-035") is None


def test_preserves_source_provenance_without_promoting_extraction_to_runtime_rule(library):
    reference = library.get_reference("CB-CASE-001")
    assert reference["evidence_level"] == "SOURCE_EXPLICIT"
    assert reference["source_production_eligible"] is True
    assert reference["production_eligible"] is False
    assert reference["scope"] == "REFERENCE_KNOWLEDGE"
    assert reference["requires_human_confirmation"] is True
    assert reference["citations"][0]["source_id"] == "SRC-02"
    assert "P152" in reference["citations"][0]["locators"]
    assert len(reference["citations"][0]["sha256"]) == 64
    assert reference["required_evidence"][0]["expected_source"] == "SYSTEM_OF_RECORD"
    assert reference["source_outcome"]["result"] == "NOT_STATED"
    assert "case_id" not in reference
    assert "allowed_actions" not in reference


def test_conflicting_rule_retains_missing_deadlines_and_conflict_references(library):
    reference = library.get_reference("CB-CASE-040")
    assert reference["verification_status"] == "CONFLICTING_SOURCES"
    assert "CONFLICT-003" in reference["conflict_ids"]
    assert reference["production_eligible"] is False
    assert reference["rule_versions"]
    assert reference["source_locators"]
    assert "deadlines" not in reference
    for citation in reference["citations"]:
        assert citation["locators"]
        assert all(citation["source_id"] in locator for locator in citation["locators"])


def test_reason_search_uses_exact_codes_and_preserves_combined_source_codes(library):
    matches = library.search(scheme="visa", reason_code="10.4", limit=100)
    assert matches and all(m["scheme"] == "VISA" and "10.4" in m["reason_codes"] for m in matches)
    assert matches[0]["template_id"] == "CB-CASE-040"
    assert library.search(scheme="VISA", reason_code="10.40") == []
    assert library.search(scheme="VISA", reason_code="10") == []
    mastercard = library.search(scheme="MC", reason_code="4853", limit=100)
    assert any(m["reason_code"] == "4853/4854" for m in mastercard)
    assert library.search(scheme="MASTERCARD", reason_code="2001") == []
    assert library.search(scheme="VISA", reason_code="4853") == []


def test_seed_preview_excludes_source_examples_and_does_not_invent_missing_facts(library):
    templates = library.list_templates()
    assert len(templates) == 28
    assert all(t["template"]["sandbox_flag"] is True for t in templates)
    assert library.get_template("CB-CASE-001") is None
    preview = library.get_template("CB-CASE-041")
    assert preview["template"]["transaction_facts"]["amount"] == "NOT_STATED"
    assert preview["template"]["transaction_facts"]["transaction_id"] == "NOT_STATED"
    assert preview["scope"] == "SANDBOX_TEMPLATE_PREVIEW"
    assert preview["requires_confirmation"] is True
    assert "command" not in preview
    assert "case_id" not in preview
    assert preview["production_eligible"] is False


def test_every_read_is_detached_from_saved_corpus(library):
    reference = library.get_reference("CB-CASE-001")
    reference["citations"][0]["locators"].clear()
    reference["required_evidence"].clear()
    assert library.get_reference("CB-CASE-001")["citations"][0]["locators"]
    assert library.get_reference("CB-CASE-001")["required_evidence"]
    preview = library.get_template("CB-CASE-041")
    preview["template"]["transaction_facts"]["amount"] = "USD 999"
    assert (
        library.get_template("CB-CASE-041")["template"]["transaction_facts"]["amount"]
        == "NOT_STATED"
    )


def test_reference_list_filters_without_changing_source_classification(library):
    matches = library.list_references(scheme="VISA", evidence_level="SYNTHETIC_DEMO", query="证据")
    assert matches
    assert all(m["scheme"] == "VISA" and m["evidence_level"] == "SYNTHETIC_DEMO" for m in matches)
    assert len(library.list_references(limit=2)) == 2
    with pytest.raises(ValueError):
        library.search(scheme="VISA", reason_code="10.4", limit=True)
    with pytest.raises(ValueError):
        library.list_references(evidence_level="REAL_MERCHANT_CASE")


@pytest.mark.parametrize("mutation", ["unknown_source", "duplicate_case", "source_seed"])
def test_bad_corpus_fails_closed_without_making_replacement_examples(tmp_path, library, mutation):
    # Fixture copies deliberately corrupt one foreign key/classification boundary.
    corpus = json.loads(library._library_path.read_text())
    seeds = json.loads(library._seed_path.read_text())
    if mutation == "unknown_source":
        corpus["cases"][0]["source_ids"] = ["NOT_A_SOURCE"]
    elif mutation == "duplicate_case":
        corpus["cases"].append(corpus["cases"][0])
    else:
        seeds["seed_cases"][0]["case_template_id"] = "CB-CASE-001"
        seeds["seed_cases"][0]["evidence_level"] = "SOURCE_EXPLICIT"
    source_path = tmp_path / "03_case_library.json"
    seed_path = tmp_path / "06_seed_cases.json"
    source_path.write_text(json.dumps(corpus))
    seed_path.write_text(json.dumps(seeds))
    with pytest.raises(CaseLibraryError):
        DisputeCaseLibrary(source_path, seed_path)


def test_unavailable_file_does_not_silently_use_synthetic_fallback(tmp_path):
    with pytest.raises(CaseLibraryError):
        DisputeCaseLibrary(tmp_path / "missing.json")


def test_packaged_corpus_is_byte_identical_to_uploaded_repository_files(library):
    docs = Path(__file__).resolve().parents[2] / "docs/chargeback-case-library"
    packaged = files("oceanpilot.data.chargeback_case_library")
    for name in ("03_case_library.json", "06_seed_cases.json"):
        assert (packaged / name).read_bytes() == (docs / name).read_bytes()
    assert library.manifest()["source_manifest"]["source_commit"] == (
        "250e7d904fce451e6fe72b2192cba393b717c636"
    )


def test_packaged_hash_drift_is_rejected(tmp_path, library, monkeypatch):
    import oceanpilot.adapters.knowledge.dispute_case_library as adapter

    packaged = files("oceanpilot.data.chargeback_case_library")
    for name in ("03_case_library.json", "06_seed_cases.json", "manifest.json"):
        (tmp_path / name).write_bytes((packaged / name).read_bytes())
    corpus = tmp_path / "03_case_library.json"
    corpus.write_text(corpus.read_text() + "\n")
    monkeypatch.setattr(adapter, "_DEFAULT_DIRECTORY", tmp_path)
    with pytest.raises(CaseLibraryError, match="source manifest"):
        adapter.DisputeCaseLibrary()
