"""Offline validator for redacted company reference-data handoffs."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from oceanpilot.adapters.ingestion.loader import (
    IngestionError,
    load_bank_rules,
    load_case_samples,
    load_reason_code_mappings,
    load_reason_policies,
    parse_json_records,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oceanpilot-validate-data",
        description="Validate redacted OceanPilot company reference data offline.",
    )
    parser.add_argument("--reason-code-mappings", type=Path)
    parser.add_argument("--reason-policies", type=Path)
    parser.add_argument("--bank-rules", type=Path)
    parser.add_argument("--case-samples", type=Path)
    return parser


def _load(path: Path) -> list[dict[str, object]]:
    try:
        return parse_json_records(path.read_bytes())
    except OSError:
        raise IngestionError() from None


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selected = (
        args.reason_code_mappings,
        args.reason_policies,
        args.bank_rules,
        args.case_samples,
    )
    if not any(selected):
        print("ERROR: select at least one data file")
        return 2

    counts: dict[str, int] = {}
    try:
        if args.reason_code_mappings:
            records = _load(args.reason_code_mappings)
            load_reason_code_mappings(records)
            counts["reason_code_mappings"] = len(records)
        if args.reason_policies:
            records = _load(args.reason_policies)
            load_reason_policies(records)
            counts["reason_policies"] = len(records)
        if args.bank_rules:
            records = _load(args.bank_rules)
            load_bank_rules(records)
            counts["bank_rules"] = len(records)
        if args.case_samples:
            records = _load(args.case_samples)
            load_case_samples(records)
            counts["case_samples"] = len(records)
    except IngestionError:
        print("ERROR: company data validation failed")
        return 1

    print(json.dumps({"status": "ok", "validated": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
