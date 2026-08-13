from pathlib import Path

from scripts.check_submission_pdf import check_submission_pdf

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_submission_pdf_has_two_readable_landscape_pages():
    path = next((REPOSITORY_ROOT / "artifacts").glob("*.pdf"))

    check_submission_pdf(path)
