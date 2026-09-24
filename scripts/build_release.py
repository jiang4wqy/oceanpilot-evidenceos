"""Build a minimal, secret-scanned OceanPilot distribution ZIP."""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT.parent / "OceanPilot-可分发版.zip"
FILES = (
    ".dockerignore",
    "Dockerfile",
    "compose.yaml",
    "config.env.example",
    "pyproject.toml",
    "start.sh",
    "restart.sh",
    "stop.sh",
    "status.sh",
    "show-accounts.sh",
    "start.bat",
    "restart.bat",
    "stop.bat",
    "status.bat",
    "show-accounts.bat",
    "安装与替换接口说明.md",
)
DENY_PARTS = {".git", ".venv", "tests", "docs", "work", "__pycache__"}
SECRET_PATTERNS = (
    re.compile(rb"sk-ant-[A-Za-z0-9_-]{12,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"cli_[A-Za-z0-9]{12,}"),
    re.compile(rb"/Users/[^/\s]+/"),
)


def allowed(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return not (
        path.suffix.lower() == ".md"
        or any(part in DENY_PARTS or " 2" in part for part in relative.parts)
    )


def scan(directory: Path) -> None:
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        data = path.read_bytes()
        for pattern in SECRET_PATTERNS:
            if pattern.search(data):
                raise RuntimeError(
                    f"release secret/path scan failed: {path.relative_to(directory)}"
                )


def build(output: Path) -> Path:
    output = output.resolve()
    with tempfile.TemporaryDirectory(prefix="oceanpilot-release-") as temporary:
        stage = Path(temporary) / "OceanPilot"
        stage.mkdir()
        for name in FILES:
            shutil.copy2(ROOT / name, stage / name)
        shutil.copytree(
            ROOT / "src",
            stage / "src",
            ignore=lambda directory, names: [
                name
                for name in names
                if not allowed(Path(directory) / name) or name.endswith((".pyc", ".pyo"))
            ],
        )
        scan(stage)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        with zipfile.ZipFile(
            output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo.from_file(path, path.relative_to(stage.parent))
                    if path.suffix == ".sh":
                        info.external_attr = (0o100755 & 0xFFFF) << 16
                    with path.open("rb") as source:
                        archive.writestr(info, source.read(), compress_type=zipfile.ZIP_DEFLATED)
        return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build(args.output)
    print(result)


if __name__ == "__main__":
    main()
