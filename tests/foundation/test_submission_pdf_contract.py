import os
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader

from scripts.build_submission_pdf import OUTPUT_PDF, build_pdf

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _assert_current_submission_facts(path: Path) -> None:
    reader = PdfReader(path)
    assert len(reader.pages) == 2
    assert all(float(page.mediabox.width) > float(page.mediabox.height) for page in reader.pages)

    text = "\n".join(page.extract_text() for page in reader.pages)
    for expected in (
        "1035 tests",
        "8 条 OpenAPI",
        "真实飞书测试群",
        "尚未验证",
        "synthetic",
    ):
        assert expected in text
    for stale in (
        "717",
        "5 条 API",
        "HTTP 501",
        "FEATURE_DEFERRED",
        "尚未接入运行时诊断",
    ):
        assert stale not in text


def test_submission_pdf_and_builder_use_current_release_facts(tmp_path):
    _assert_current_submission_facts(OUTPUT_PDF)
    _assert_current_submission_facts(build_pdf(tmp_path / "submission.pdf"))


def test_submission_pdf_cli_supports_non_utf8_windows_console():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"

    result = subprocess.run(
        [sys.executable, "-B", "scripts/build_submission_pdf.py"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Submission PDF rebuilt."
