"""Immutable startup metadata for identifying the code and isolated data instance."""

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from oceanpilot import __version__


def runtime_manifest(db_path):
    package = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for source in sorted(package.rglob("*")):
        if source.is_file() and source.suffix in {".py", ".js", ".css", ".html", ".json"}:
            digest.update(str(source.relative_to(package)).encode())
            digest.update(source.read_bytes())
    revision, dirty = None, None
    try:
        repo = package.parents[1]
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            revision = result.stdout.strip()
            result = subprocess.run(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--untracked-files=normal",
                    "--",
                    "src",
                    "pyproject.toml",
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            dirty = bool(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {
        "version": __version__,
        "started_at": datetime.now(UTC).isoformat(),
        "git_revision": revision,
        "working_tree_modified": dirty,
        "source_sha256": digest.hexdigest(),
        "data_instance_id": hashlib.sha256(str(Path(db_path).resolve()).encode()).hexdigest()[:16],
        "authentication": "SERVER_SESSION_AND_CASE_PARTICIPANTS",
        "production_eligible": False,
    }
