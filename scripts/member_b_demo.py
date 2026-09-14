"""Local synthetic demo lifecycle. Never overwrites an instance or resets shared data."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
DATABASES = ("core.db", "chargeback.db", "rules.db")
MARKER = "oceanpilot-member-b-synthetic-v1"


def write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    path.chmod(0o600)


def code_identity():
    paths = sorted((ROOT / "src").rglob("*")) + [
        ROOT / "pyproject.toml",
        Path(__file__),
        ROOT / "scripts/member_b_rehearsal.py",
    ]
    hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
        if p.is_file() and "__pycache__" not in p.parts
    }
    return {
        "root": str(ROOT),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
        "files": hashes,
        "python": sys.version,
        "executable": sys.executable,
        "packages": {
            name: importlib.metadata.version(name)
            for name in (
                "fastapi",
                "pydantic",
                "uvicorn",
                "httpx",
                "pytest",
                "ruff",
                "Pillow",
                "pypdfium2",
            )
        },
    }


def manifest(directory):
    value = json.loads((directory / "instance.json").read_text())
    if value.get("kind") != MARKER:
        raise ValueError("Not a Member B dedicated synthetic instance")
    return value


def free_port(port):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))


def empty_directory(path):
    path.mkdir(parents=True, exist_ok=False, mode=0o700)


def copy_database(source, target):
    if not source.is_file() or target.exists():
        raise ValueError("Backup source missing or target already exists")
    with (
        closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original,
        closing(sqlite3.connect(target)) as copied,
    ):
        original.backup(copied)
        if copied.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
    target.chmod(0o600)


def new_instance(directory, port):
    free_port(port)
    empty_directory(directory)
    from oceanpilot.v21_accounts import provision

    provision(directory / "chargeback.db", directory / "private-accounts.json")
    write_json(
        directory / "instance.json",
        {
            "kind": MARKER,
            "id": str(uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "port": port,
            "synthetic_only": True,
            "upstream": "mock",
            "model": "offline",
            "feishu": "unconfigured",
            "code": code_identity(),
        },
    )
    print(f"Created dedicated instance: {directory}\nCredentials remain in private-accounts.json")


def start(directory, *, model_config=None, model_name="deepseek-v4-flash"):
    data = manifest(directory)
    free_port(data["port"])
    current = code_identity()
    if any(current[key] != data["code"][key] for key in ("sha256", "python", "packages")):
        raise ValueError(
            "Code/runtime changed; validate the change, "
            "then explicitly pin or create a new instance"
        )
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONUNBUFFERED": "1",
        "OCEANPILOT_DEMO_ACCOUNTS": str(directory / "private-accounts.json"),
        "OCEANPILOT_DB_PATH": str(directory / "core.db"),
        "OCEANPILOT_CHARGEBACK_DB_PATH": str(directory / "chargeback.db"),
        "OCEANPILOT_RULES_DB_PATH": str(directory / "rules.db"),
        "OCEANPILOT_V2_BASE_URL": f"http://127.0.0.1:{data['port']}",
        "OCEANPILOT_CHARGEBACK_LIVE_MODEL": "0",
        "OCEANPILOT_V2_UPSTREAM_MODE": "mock",
    }
    mode = "offline"
    if model_config is not None:
        from dotenv import dotenv_values

        config = dotenv_values(model_config, interpolate=False)
        if not config.get("DEEPSEEK_API_KEY"):
            raise ValueError("Selected model config has no DEEPSEEK_API_KEY")
        # Read only model credentials; never import Feishu, tunnel or shared DB settings.
        env.update(
            {
                "OCEANPILOT_CHARGEBACK_LIVE_MODEL": "1",
                "OCEANPILOT_MODEL_PROVIDER": "deepseek",
                "DEEPSEEK_API_KEY": config["DEEPSEEK_API_KEY"],
                "DEEPSEEK_API_BASE": config.get("DEEPSEEK_API_BASE") or "https://api.deepseek.com",
                "DEEPSEEK_MODEL": model_name,
            }
        )
        mode = model_name
    write_json(
        directory / ("run-" + str(uuid4()) + ".json"),
        {
            "instance_id": data["id"],
            "started_at": datetime.now(UTC).isoformat(),
            "code_sha256": current["sha256"],
            "model": mode,
            "upstream": "mock",
        },
    )
    print(f"Starting {data['id']} at {env['OCEANPILOT_V2_BASE_URL']} — synthetic/{mode}/Mock")
    os.chdir(ROOT)
    os.execve(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "oceanpilot.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(data["port"]),
            "--no-access-log",
        ],
        env,
    )


def snapshot(source, destination, *, restoring=False, port=None):
    data = manifest(source)
    if restoring:
        if not data.get("snapshot"):
            raise ValueError("Restore requires an immutable backup snapshot")
        for name, digest in data["snapshot_hashes"].items():
            if hashlib.sha256((source / name).read_bytes()).hexdigest() != digest:
                raise ValueError("Snapshot hash mismatch")
    # Offline-only lifecycle: refuse backup/restore while its port is in use.
    free_port(port if restoring else data["port"])
    empty_directory(destination)
    for name in DATABASES:
        copy_database(source / name, destination / name)
    shutil.copyfile(source / "private-accounts.json", destination / "private-accounts.json")
    (destination / "private-accounts.json").chmod(0o600)
    hashes = {
        name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in DATABASES
    }
    write_json(
        destination / "instance.json",
        data
        | {
            "id": str(uuid4()),
            "parent_id": data["id"],
            "created_at": datetime.now(UTC).isoformat(),
            "snapshot_hashes": hashes,
            "port": port if restoring else data["port"],
            "snapshot": not restoring,
        },
    )
    print(json.dumps({"directory": str(destination), "database_hashes": hashes}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["new", "start", "status", "backup", "restore", "pin"])
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--port", type=int, default=8014)
    parser.add_argument(
        "--model-config",
        type=Path,
        help="Explicit private env file: read DeepSeek keys only; defaults offline",
    )
    parser.add_argument("--model", default="deepseek-v4-flash")
    args = parser.parse_args()
    directory = args.instance.resolve()
    if args.action == "new":
        new_instance(directory, args.port)
    elif args.action == "start":
        if manifest(directory).get("snapshot"):
            raise ValueError("Restore snapshot into a new instance before starting")
        start(directory, model_config=args.model_config, model_name=args.model)
    elif args.action == "pin":
        data = manifest(directory)
        free_port(data["port"])
        if data.get("snapshot"):
            raise ValueError("Cannot modify a backup snapshot")
        current = code_identity()
        if current != data["code"]:
            history = directory / ("build-" + str(uuid4()) + ".json")
            write_json(history, data)
            pending = directory / ("manifest-" + str(uuid4()) + ".json")
            write_json(pending, data | {"code": current})
            pending.replace(directory / "instance.json")
        print("Explicitly pinned current code and runtime; business data unchanged")
    elif args.action == "status":
        data = manifest(directory)
        print(
            json.dumps(
                {
                    "id": data["id"],
                    "directory": str(directory),
                    "port": data["port"],
                    "code_sha256": data["code"]["sha256"],
                    "code_matches": data["code"]["sha256"] == code_identity()["sha256"],
                    "databases": {n: (directory / n).exists() for n in DATABASES},
                },
                indent=2,
            )
        )
    elif args.destination is None:
        parser.error("--destination is required for backup/restore")
    else:
        snapshot(
            directory,
            args.destination.resolve(),
            restoring=args.action == "restore",
            port=args.port,
        )


if __name__ == "__main__":
    main()
