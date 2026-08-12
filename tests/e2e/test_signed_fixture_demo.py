import json
import os
import subprocess
import sys
from pathlib import Path

from examples import signed_fixture_demo

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "examples" / "signed_fixture_demo.py"


def _run_fixture(work_dir: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "--work-dir", str(work_dir)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    lines = completed.stdout.splitlines()
    summary = json.loads(lines[-1]) if lines else {}
    return completed, summary


def test_signed_fixture_runner_completes_real_callback_confirmation_and_cockpit(tmp_path):
    completed, summary = _run_fixture(tmp_path / "run")

    assert completed.returncode == 0, completed.stderr
    assert summary == {
        "mode": "SIGNED_FIXTURE",
        "synthetic": True,
        "message_http": 200,
        "evidence_steps": 7,
        "cockpit_http": 200,
        "case_status": "HUMAN_REVIEW",
        "matched_rule_id": "THREEDS_INCOMPLETE_V1",
        "display_confidence": "0.87",
        "responsible_team": "TECHNICAL_SUPPORT",
        "priority": "MEDIUM",
        "confirmation_state": "CONFIRMED",
        "case_unchanged_by_confirmation": True,
        "approval_audit_count": 1,
        "business_action_executed": False,
    }
    assert "SYNTHETIC SIGNED FEISHU FIXTURE -- no external Feishu or business action" in (
        completed.stdout
    )
    assert (tmp_path / "run" / "core.db").is_file()
    assert (tmp_path / "run" / "feishu.db").is_file()


def test_signed_fixture_runner_keeps_credentials_out_of_output_and_sqlite(
    tmp_path,
    capsys,
    monkeypatch,
):
    work_dir = tmp_path / "safe-run"
    actual_settings = signed_fixture_demo.FeishuSettings
    captured_signing_materials: list[str] = []

    def capture_settings(**values):
        captured_signing_materials.extend(
            values[name] for name in ("app_secret", "verification_token", "encrypt_key")
        )
        return actual_settings(**values)

    monkeypatch.setattr(
        signed_fixture_demo,
        "FeishuSettings",
        capture_settings,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [str(RUNNER), "--work-dir", str(work_dir)],
    )

    assert signed_fixture_demo.main() == 0
    assert len(captured_signing_materials) == 3
    captured = capsys.readouterr()
    surfaces = [
        captured.out.encode(),
        captured.err.encode(),
    ]
    for database in (work_dir / "core.db", work_dir / "feishu.db"):
        surfaces.extend(
            candidate.read_bytes()
            for candidate in (
                database,
                Path(f"{database}-journal"),
                Path(f"{database}-wal"),
                Path(f"{database}-shm"),
            )
            if candidate.is_file()
        )
    for forbidden in (
        *(value.encode() for value in captured_signing_materials),
        b"ou_fixture_reviewer",
        b"ou_fixture_merchant",
        b"tenant_fixture",
        b"oc_fixture_demo",
        b"om_fixture_thread_001",
    ):
        assert all(forbidden not in surface for surface in surfaces)


def test_signed_fixture_runner_fails_closed_when_work_directory_is_not_empty(tmp_path):
    work_dir = tmp_path / "occupied"
    work_dir.mkdir()
    (work_dir / "keep.txt").write_text("user-owned", encoding="utf-8")

    completed, summary = _run_fixture(work_dir)

    assert completed.returncode != 0
    assert summary == {}
    assert "work directory must be empty" in completed.stderr
    assert (work_dir / "keep.txt").read_text(encoding="utf-8") == "user-owned"
