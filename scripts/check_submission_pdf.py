"""Minimal structural smoke check for the generated submission PDF."""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def _default_pdf() -> Path:
    candidates = sorted((ROOT / "artifacts").glob("*.pdf"))
    if len(candidates) != 1:
        raise ValueError("expected exactly one submission PDF")
    return candidates[0]


def check_submission_pdf(path: Path) -> None:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    reader = PdfReader(path)
    if len(reader.pages) != 2:
        raise ValueError("submission PDF must contain exactly two pages")
    if any(float(page.mediabox.width) <= float(page.mediabox.height) for page in reader.pages):
        raise ValueError("submission PDF pages must use landscape orientation")
    if any(not (page.extract_text() or "").strip() for page in reader.pages):
        raise ValueError("submission PDF pages must contain extractable text")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path)
    arguments = parser.parse_args()
    check_submission_pdf(arguments.path or _default_pdf())
    print("Submission PDF structure is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
