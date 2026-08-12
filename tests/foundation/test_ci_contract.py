from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_uses_python_312_and_runs_all_release_checks():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "python-version: '3.12'" in workflow
    assert 'pip install -e ".[dev]"' in workflow
    assert "ruff check src tests examples scripts" in workflow
    assert "pytest -p no:cacheprovider -q" in workflow
    assert "compileall -q src tests examples scripts" in workflow
    assert "scripts/build_submission_pdf.py" in workflow
    assert "examples/signed_fixture_demo.py" in workflow
    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./examples/demo.ps1" in workflow
    assert "git diff --check" in workflow
    assert "secrets." not in workflow
