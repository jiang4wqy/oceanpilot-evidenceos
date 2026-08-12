from pathlib import Path

from pypdf import PdfReader

from scripts.build_submission_pdf import OUTPUT_PDF, build_pdf


def _assert_current_submission_facts(path: Path) -> None:
    reader = PdfReader(path)
    assert len(reader.pages) == 2
    assert all(float(page.mediabox.width) > float(page.mediabox.height) for page in reader.pages)

    text = "\n".join(page.extract_text() for page in reader.pages)
    for expected in (
        "1034 tests",
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
