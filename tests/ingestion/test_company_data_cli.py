import json
from pathlib import Path

from oceanpilot.adapters.ingestion.cli import main
from oceanpilot.adapters.ingestion.samples import (
    SYNTHETIC_BANK_RULES,
    SYNTHETIC_CASE_SAMPLES,
    SYNTHETIC_REASON_CODE_MAPPINGS,
    SYNTHETIC_REASON_POLICIES,
)


def _write(path: Path, records: tuple[dict[str, object], ...]) -> Path:
    path.write_text(json.dumps(list(records)), encoding="utf-8")
    return path


def test_cli_validates_all_handoff_files_without_echoing_records(tmp_path, capsys):
    paths = {
        "--reason-code-mappings": _write(
            tmp_path / "mappings.json", SYNTHETIC_REASON_CODE_MAPPINGS
        ),
        "--reason-policies": _write(tmp_path / "policies.json", SYNTHETIC_REASON_POLICIES),
        "--bank-rules": _write(tmp_path / "banks.json", SYNTHETIC_BANK_RULES),
        "--case-samples": _write(tmp_path / "cases.json", SYNTHETIC_CASE_SAMPLES),
    }
    args = [part for flag, path in paths.items() for part in (flag, str(path))]

    assert main(args) == 0
    output = capsys.readouterr().out
    assert '"status": "ok"' in output
    assert '"reason_code_mappings": 2' in output
    assert "13.1" not in output
    assert "SYN-CASE-0001" not in output


def test_cli_failure_is_fixed_and_does_not_echo_sensitive_record(tmp_path, capsys):
    sentinel = "authorization=Bearer-CLI-SECRET"
    bad = ({**SYNTHETIC_REASON_CODE_MAPPINGS[0], "notes": sentinel},)
    path = _write(tmp_path / "bad.json", bad)

    assert main(["--reason-code-mappings", str(path)]) == 1
    output = capsys.readouterr().out
    assert output == "ERROR: company data validation failed\n"
    assert sentinel not in output


def test_cli_requires_at_least_one_file(capsys):
    assert main([]) == 2
    assert capsys.readouterr().out == "ERROR: select at least one data file\n"
