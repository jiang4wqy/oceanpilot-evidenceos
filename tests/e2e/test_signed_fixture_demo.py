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


def test_signed_fixture_runner_completes_mainline_callbacks_and_replays(tmp_path):
    completed, summary = _run_fixture(tmp_path / "run")

    assert completed.returncode == 0, completed.stderr
    assert summary == {
        "approval_audit_count": 1,
        "business_action_executed": False,
        "case_status": "HUMAN_REVIEW",
        "case_unchanged_by_confirmation": True,
        "confirmation_replay": True,
        "confirmation_state": "CONFIRMED",
        "display_confidence": "0.87",
        "evidence_steps": 7,
        "matched_rule_id": "THREEDS_INCOMPLETE_V1",
        "message_replay": True,
        "mode": "SIGNED_FIXTURE",
        "outbound_cards": 9,
        "priority": "MEDIUM",
        "responsible_team": "TECHNICAL_SUPPORT",
        "synthetic": True,
    }
    assert completed.stdout.splitlines()[0] == (
        "SYNTHETIC SIGNED FEISHU FIXTURE -- no external Feishu or business action"
    )
    for name in ("core.db", "feishu.db", "chargeback.db"):
        assert (tmp_path / "run" / name).is_file()


def test_signed_fixture_runner_keeps_runtime_material_out_of_surfaces(
    tmp_path,
    capsys,
    monkeypatch,
):
    work_dir = tmp_path / "safe-run"
    actual_settings = signed_fixture_demo.FeishuSettings
    captured: dict[str, str] = {}

    def capture_settings(**values):
        captured.update(
            {name: values[name] for name in ("app_secret", "verification_token", "encrypt_key")}
        )
        return actual_settings(**values)

    monkeypatch.setattr(signed_fixture_demo, "FeishuSettings", capture_settings)
    monkeypatch.setattr(sys, "argv", [str(RUNNER), "--work-dir", str(work_dir)])

    assert signed_fixture_demo.main() == 0
    captured_output = capsys.readouterr()
    surfaces = [captured_output.out.encode(), captured_output.err.encode()]
    for database in (work_dir / "core.db", work_dir / "feishu.db", work_dir / "chargeback.db"):
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
    for forbidden in signed_fixture_demo.last_sensitive_values():
        assert forbidden
        assert all(forbidden.encode() not in surface for surface in surfaces)


def test_signed_fixture_runner_fails_closed_when_work_directory_is_not_empty(tmp_path):
    work_dir = tmp_path / "occupied"
    work_dir.mkdir()
    marker = work_dir / "keep.txt"
    marker.write_text("user-owned", encoding="utf-8")

    completed, summary = _run_fixture(work_dir)

    assert completed.returncode != 0
    assert summary == {}
    assert "work directory must be empty" in completed.stderr
    assert marker.read_text(encoding="utf-8") == "user-owned"
