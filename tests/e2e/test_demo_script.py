import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SCRIPT = REPOSITORY_ROOT / "examples" / "demo.ps1"


@pytest.fixture(scope="module")
def script_text() -> str:
    return DEMO_SCRIPT.read_text(encoding="utf-8")


def test_demo_declares_safe_synthetic_scope_and_http_origin(script_text: str):
    assert (
        'Write-Host "SYNTHETIC LOCAL DEMO — no Oceanpayment or Feishu connection; '
        'no payment action is executed."' in script_text
    )
    assert (
        'Write-Host "HTTP demo origin: MERCHANT / USER_REPORTED; expected review score '
        '0.87, not the internal 0.94 fixture."' in script_text
    )
    assert script_text.index("SYNTHETIC LOCAL DEMO") < script_text.index("HTTP demo origin")


def test_demo_uses_the_expected_base_url_and_real_http_flow(script_text: str):
    assert '[string]$BaseUrl = "http://127.0.0.1:8000"' in script_text
    for endpoint in (
        '"$serviceBaseUrl/health"',
        '"$serviceBaseUrl/api/v1/cases"',
        '"$serviceBaseUrl/api/v1/cases/$caseId/evidence"',
        '"$serviceBaseUrl/api/v1/cases/$caseId"',
        '"$serviceBaseUrl/api/v1/cases/$caseId/diagnose"',
    ):
        assert endpoint in script_text
    assert "501" not in script_text
    assert "FEATURE_DEFERRED" not in script_text


def test_demo_covers_three_business_groups_and_four_rules(script_text: str):
    for business_group in ("3DS / callback", "Risk decline", "Configuration mismatch"):
        assert f'BusinessGroup = "{business_group}"' in script_text

    expected_rules = {
        "THREEDS_INCOMPLETE_V1",
        "RISK_DECLINE_V1",
        "CONFIG_MISMATCH_MERCHANT_V1",
        "CONFIG_MISMATCH_PSP_V1",
    }
    declared_rules = set(re.findall(r'RuleId = "([A-Z0-9_]+)"', script_text))
    assert declared_rules == expected_rules


def test_demo_request_payloads_do_not_accept_internal_provenance_or_scores(
    script_text: str,
):
    payload_blocks = re.findall(
        r"\$\w+Payload = \[ordered\]@\{(?P<body>.*?)\n\s*\}",
        script_text,
        flags=re.DOTALL,
    )
    assert len(payload_blocks) == 2
    forbidden_fields = {
        "source_type",
        "source_reliability",
        "confidence",
        "confidence_score",
        "score",
        "policy_version",
        "engine_version",
        "status",
        "route",
        "responsible_team",
        "priority",
    }
    for block in payload_blocks:
        payload_keys = set(re.findall(r"^\s*([a-z_]+)\s*=", block, flags=re.MULTILINE))
        assert payload_keys.isdisjoint(forbidden_fields)

    assert "source_ref =" in script_text


def test_demo_fails_closed_and_prints_a_stable_summary(script_text: str):
    assert "Set-StrictMode -Version Latest" in script_text
    assert '$ErrorActionPreference = "Stop"' in script_text
    assert "function Assert-HttpStatus" in script_text
    assert "throw " in script_text

    summary_fields = {
        "business_group",
        "scenario",
        "diagnosis_http",
        "diagnosis_snapshot_status",
        "case_status",
        "readiness",
        "matched_rule_id",
        "display_confidence",
        "review_reasons",
        "responsible_team",
        "priority",
        "ticket_title",
        "next_action",
        "audit_reference",
        "synthetic",
    }
    for field in summary_fields:
        assert re.search(rf"^\s*{field}\s*=", script_text, flags=re.MULTILINE)


def test_demo_has_valid_powershell_syntax_when_powershell_is_available():
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell is not available")

    command = (
        "$errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{DEMO_SCRIPT}', "
        "[ref]$null, [ref]$errors) > $null; "
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    completed = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
