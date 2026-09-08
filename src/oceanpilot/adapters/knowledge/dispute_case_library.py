"""Read-only references from the repository's extracted chargeback case library.

The extraction corpus contains guideline examples, rule-derived scenarios and
sandbox examples. It is neither a portfolio of live merchant disputes nor an
executable scheme policy. Source text remains data throughout this adapter.
"""

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

_EVIDENCE_LEVELS = {"SOURCE_EXPLICIT", "RULE_DERIVED", "SYNTHETIC_DEMO"}
_VERIFICATION_STATUSES = {"VERIFIED_EXTRACTED", "NEEDS_CONFIRMATION", "CONFLICTING_SOURCES"}
_DEFAULT_DIRECTORY = files("oceanpilot.data.chargeback_case_library")
_REASON_TOKEN = re.compile(r"(?<![A-Z0-9.])(?:[A-Z]\d{2}|\d{2}\.\d(?:\.\d)?|\d{4})(?![A-Z0-9.])")
_SCHEMES = {
    "VISA": "VISA",
    "MASTERCARD": "MASTERCARD",
    "MC": "MASTERCARD",
    "AMEX": "AMEX",
    "AMERICAN EXPRESS": "AMEX",
}


class CaseLibraryError(ValueError):
    """Invalid or unavailable reference files; never silently fabricate a corpus."""


def _load(path: Traversable) -> tuple[dict, str]:
    try:
        content = path.read_bytes()
        data = json.loads(content)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CaseLibraryError(f"Cannot load case library file: {path.name}") from exc
    if not isinstance(data, dict) or data.get("schema_version") not in {"1.0", "1.1"}:
        raise CaseLibraryError(f"Unsupported case library schema: {path.name}")
    return data, hashlib.sha256(content).hexdigest()


def _scheme(value: str) -> str:
    # Ethoca/prevention content has a distinct scope; do not silently equate it
    # with Mastercard chargeback rules by removing its qualifier.
    normalized = value.strip().upper()
    return _SCHEMES.get(normalized, normalized)


def _reason_codes(value: str) -> frozenset[str]:
    # Parenthesized secondary references (e.g. representment code 2001) are not
    # the dispute reason. Preserve the full original label in every reference.
    head = re.split(r"[（(]", value, maxsplit=1)[0].strip().upper()
    return frozenset(_REASON_TOKEN.findall(head))


def _limit(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    return value


class DisputeCaseLibrary:
    """Load immutable source snapshots; callers receive independent copies.

    Production providers can implement the same ``search`` / ``manifest``
    methods. No method here creates a case or changes active workflow rules.
    ``library_path`` and ``seed_path`` permit deployment-owned data locations.
    """

    def __init__(self, library_path: str | Path | None = None, seed_path: str | Path | None = None):
        self._library_path = (
            Path(library_path)
            if library_path is not None
            else _DEFAULT_DIRECTORY / "03_case_library.json"
        )
        self._seed_path = (
            Path(seed_path)
            if seed_path is not None
            else Path(library_path).with_name("06_seed_cases.json")
            if library_path is not None
            else _DEFAULT_DIRECTORY / "06_seed_cases.json"
        )
        self._library, self._library_sha = _load(self._library_path)
        self._seeds, self._seed_sha = _load(self._seed_path)
        self._source_manifest = None
        if library_path is None and seed_path is None:
            self._source_manifest, _ = _load(_DEFAULT_DIRECTORY / "manifest.json")
            expected = {f["name"]: f["sha256"] for f in self._source_manifest["files"]}
            if expected != {
                self._library_path.name: self._library_sha,
                self._seed_path.name: self._seed_sha,
            }:
                raise CaseLibraryError("Packaged case library does not match its source manifest")
        self._validate()
        self._sources = {s["source_id"]: s for s in self._library["sources"]}
        self._cases = {c["case_template_id"]: c for c in self._library["cases"]}
        self._templates = {s["case_template_id"]: s for s in self._seeds["seed_cases"]}

    def _validate(self):
        try:
            sources = self._library["sources"]
            cases = self._library["cases"]
            seeds = self._seeds["seed_cases"]
            if not all(isinstance(value, list) for value in (sources, cases, seeds)):
                raise ValueError("collections must be lists")
            source_ids = {s["source_id"] for s in sources}
            case_ids = {c["case_template_id"] for c in cases}
            if len(source_ids) != len(sources) or len(case_ids) != len(cases):
                raise ValueError("duplicate source or case identifiers")
            for case in cases:
                for key in (
                    "case_template_id",
                    "title_cn",
                    "scenario_one_line",
                    "scheme",
                    "reason_code",
                    "data_source_type",
                ):
                    if not isinstance(case[key], str) or not case[key]:
                        raise ValueError("missing case text")
                if case["evidence_level"] not in _EVIDENCE_LEVELS:
                    raise ValueError("invalid evidence level")
                if not set(case["source_ids"]).issubset(source_ids):
                    raise ValueError("unknown source identifier")
                provenance = case["provenance"]
                if provenance["verification_status"] not in _VERIFICATION_STATUSES:
                    raise ValueError("invalid verification status")
                if type(provenance["production_eligible"]) is not bool:
                    raise ValueError("invalid source eligibility")
                if not isinstance(case["evidence_required"], list):
                    raise ValueError("evidence requirements must be a list")
            if len({s["case_template_id"] for s in seeds}) != len(seeds):
                raise ValueError("duplicate sandbox identifiers")
            levels = {c["case_template_id"]: c["evidence_level"] for c in cases}
            for seed in seeds:
                identifier = seed["case_template_id"]
                if identifier not in case_ids or levels[identifier] != seed["evidence_level"]:
                    raise ValueError("sandbox template does not match corpus")
                if seed["sandbox_flag"] is not True or seed["evidence_level"] not in {
                    "RULE_DERIVED",
                    "SYNTHETIC_DEMO",
                }:
                    raise ValueError("only explicit sandbox templates may be seeded")
        except (KeyError, TypeError, ValueError) as exc:
            raise CaseLibraryError("Invalid extracted case library or sandbox template") from exc

    def manifest(self) -> dict:
        cases = self._library["cases"]
        return deepcopy(
            {
                "provider": "REPOSITORY_CASE_LIBRARY",
                "dataset_id": "chargeback-case-library",
                "schema_version": self._library["schema_version"],
                "generated_at": self._library.get("generated_at"),
                "case_count": len(cases),
                "reference_case_count": len(cases),
                "rule_group_count": len(self._library.get("rule_provenance", [])),
                "sandbox_template_count": len(self._templates),
                "template_count": len(self._templates),
                "source_count": len(self._sources),
                "evidence_levels": dict(Counter(c["evidence_level"] for c in cases)),
                "verification_statuses": dict(
                    Counter(c["provenance"]["verification_status"] for c in cases)
                ),
                "conflict_count": len(self._library.get("conflicts", [])),
                "data_gap_count": len(self._library.get("data_gaps", [])),
                "files": [
                    {"name": self._library_path.name, "sha256": self._library_sha},
                    {"name": self._seed_path.name, "sha256": self._seed_sha},
                ],
                "sources": list(self._sources.values()),
                "source_manifest": self._source_manifest,
                "scope": "REFERENCE_KNOWLEDGE",
                "production_eligible": False,
                "boundary": (
                    "指南示例、规则还原与合成场景仅供参考；不是实际商户案件或自动生效规则。"
                ),
            }
        )

    def _reference(self, case: dict) -> dict:
        provenance = case["provenance"]
        citations = []
        for source_id in case["source_ids"]:
            source = self._sources[source_id]
            locators = [
                locator
                for locator in case["source_locations"]
                if len(case["source_ids"]) == 1
                or re.search(rf"(?<![A-Z0-9-]){re.escape(source_id)}(?![A-Z0-9-])", locator)
            ]
            citations.append(
                {
                    "source_id": source_id,
                    "title": source["document_title"],
                    "publisher": source["publisher_or_author"],
                    "rule_version": source["publish_or_version"],
                    "file_name": source["file_name"],
                    "sha256": source["sha256"],
                    # Do not attribute another document's page number to this
                    # source. Unqualified mixed-source locations stay at case level.
                    "locators": locators,
                }
            )
        return deepcopy(
            {
                "template_id": case["case_template_id"],
                "title": case["title_cn"],
                "summary": case["scenario_one_line"],
                "scheme": _scheme(case["scheme"]),
                "source_scheme": case["scheme"],
                "reason_code": case["reason_code"],
                "reason_codes": sorted(_reason_codes(case["reason_code"])),
                "evidence_level": case["evidence_level"],
                "verification_status": provenance["verification_status"],
                "source_type": "CURATED_CASE_LIBRARY",
                "source_content_type": case["data_source_type"],
                "source_ids": case["source_ids"],
                "source_locators": case["source_locations"],
                "rule_versions": provenance.get("rule_version", []),
                "effective_date": provenance.get("effective_date", "NOT_STATED"),
                "conflict_ids": provenance.get("conflict_ids", []),
                "conflict_status": provenance.get("conflict_status", "NEEDS_CONFIRMATION"),
                "citations": citations,
                "required_evidence": case["evidence_required"],
                "deadline_policy": provenance.get("deadline_policy", "NOT_STATED"),
                "source_outcome": case["outcome"],
                "derived_from_rule_ids": provenance.get("derived_from_rule_ids", []),
                "source_production_eligible": provenance["production_eligible"],
                "production_eligible": False,
                "requires_human_confirmation": True,
                "scope": "REFERENCE_KNOWLEDGE",
                "sandbox_template_available": case["case_template_id"] in self._templates,
            }
        )

    def get_reference(self, template_id: str) -> dict | None:
        case = self._cases.get(template_id)
        return self._reference(case) if case else None

    def list_references(
        self,
        *,
        scheme: str | None = None,
        evidence_level: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        _limit(limit)
        if evidence_level is not None and evidence_level not in _EVIDENCE_LEVELS:
            raise ValueError("Unknown evidence level")
        matches = []
        query = (query or "").strip().casefold()
        for case in self._cases.values():
            if scheme and _scheme(case["scheme"]) != _scheme(scheme):
                continue
            if evidence_level and case["evidence_level"] != evidence_level:
                continue
            if (
                query
                and query
                not in " ".join(
                    (
                        case["case_template_id"],
                        case["title_cn"],
                        case["scenario_one_line"],
                        case["reason_code"],
                    )
                ).casefold()
            ):
                continue
            matches.append(self._reference(case))
            if len(matches) == limit:
                break
        return matches

    def search(
        self, *, scheme: str, reason_code: str, query: str | None = None, limit: int = 5
    ) -> list[dict]:
        """Match exact scheme and dispute reason tokens, without inventing policy scope."""
        _limit(limit)
        reason_codes = _reason_codes(reason_code)
        if not reason_codes:
            return []
        candidates = self.list_references(scheme=scheme, query=query, limit=100)
        candidates = [c for c in candidates if reason_codes.intersection(c["reason_codes"])]
        levels = {"RULE_DERIVED": 0, "SOURCE_EXPLICIT": 1, "SYNTHETIC_DEMO": 2}
        candidates.sort(key=lambda c: (levels[c["evidence_level"]], c["template_id"]))
        return candidates[:limit]

    def get_template(self, template_id: str) -> dict | None:
        """Return an explicitly marked preview; NOT_STATED values remain unknown.

        No case ID, intake command, automatic decision, deadline or financial
        event is generated from template text. A separate authorized import must
        collect missing facts and apply the workflow's normal confirmation gates.
        """
        template = self._templates.get(template_id)
        if template is None:
            return None
        reference = self.get_reference(template_id)
        return deepcopy(
            {
                "template_id": template_id,
                "reference": reference,
                "template": template,
                "scope": "SANDBOX_TEMPLATE_PREVIEW",
                "requires_confirmation": True,
                "production_eligible": False,
            }
        )

    def list_templates(self) -> list[dict]:
        return [self.get_template(identifier) for identifier in self._templates]
