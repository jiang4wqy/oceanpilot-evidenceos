import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPOSITORY_ROOT / "pyproject.toml"


def _job(workflow: str, name: str) -> str:
    marker = f"  {name}:\n"
    start = workflow.index(marker) + len(marker)
    lines = workflow[start:].splitlines(keepends=True)
    end = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":")
        ),
        len(lines),
    )
    return "".join(lines[:end])


def test_ci_preserves_linux_main_gate_and_adds_release_checks():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    linux = _job(workflow, "test")

    assert "runs-on: ubuntu-latest" in linux
    assert 'python-version: "3.12"' in linux or "python-version: '3.12'" in linux
    for capability in (
        "pip install --upgrade pip setuptools wheel",
        'pip install -e ".[dev]"',
        "ruff check src tests examples scripts",
        "ruff format --check src tests examples scripts",
        "compileall -q src tests examples scripts",
        "pytest -p no:cacheprovider -q",
        "pip check",
        "examples/signed_fixture_demo.py",
        "pip wheel . --no-deps --no-build-isolation",
        "python -I",
        "git diff --check",
    ):
        assert capability in linux


def test_ci_adds_dependent_windows_demo_and_pdf_gate():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    windows = _job(workflow, "release-windows")

    assert "needs: test" in windows
    assert "runs-on: windows-latest" in windows
    for capability in (
        "scripts/build_submission_pdf.py",
        "scripts/check_submission_pdf.py",
        "examples/signed_fixture_demo.py",
        "Start-Process",
        "examples/demo.ps1",
        "Stop-Process",
        "git diff --exit-code -- artifacts",
        "git diff --check",
    ):
        assert capability in windows


def test_ci_is_read_only_and_uses_no_repository_secrets():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "permissions:\n  contents: read" in workflow
    assert "secrets." not in workflow


def test_pdf_dependencies_are_pinned_without_changing_mainline_contracts():
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    assert project["project"]["version"] == "0.2.1"
    assert {
        "anthropic==0.120.2",
        "fastapi==0.139.2",
        "pydantic==2.13.4",
        "uvicorn==0.51.0",
    }.issubset(project["project"]["dependencies"])
    assert {"pypdf==6.15.0", "reportlab==4.4.9"}.issubset(
        project["project"]["optional-dependencies"]["dev"]
    )
    assert project["tool"]["ruff"]["lint"]["per-file-ignores"]["src/oceanpilot/api/demo.py"] == [
        "E501"
    ]
