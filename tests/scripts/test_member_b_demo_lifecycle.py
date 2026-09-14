"""Safety contracts for the isolated demo lifecycle, using temporary SQLite files."""

import importlib.util
import socket
import sqlite3
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("member_b_demo", "scripts/member_b_demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_offline_snapshot_roundtrip_integrity_and_no_overwrite(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for name in demo.DATABASES:
        with sqlite3.connect(source / name) as db:
            db.execute("CREATE TABLE sentinel(value TEXT)")
            db.execute("INSERT INTO sentinel VALUES (?)", (name,))
    demo.write_json(source / "private-accounts.json", {"test": True})
    demo.write_json(
        source / "instance.json",
        {
            "kind": demo.MARKER,
            "id": "test-instance",
            "port": unused_port(),
            "code": {},
        },
    )
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    demo.snapshot(source, backup)
    demo.snapshot(backup, restored, restoring=True, port=unused_port())
    assert demo.manifest(restored)["parent_id"] == demo.manifest(backup)["id"]
    for name in demo.DATABASES:
        with sqlite3.connect(restored / name) as db:
            assert db.execute("SELECT value FROM sentinel").fetchone() == (name,)
    with pytest.raises(FileExistsError):
        demo.snapshot(source, backup)
    (backup / "core.db").write_bytes(b"altered-snapshot")
    with pytest.raises(ValueError, match="hash mismatch"):
        demo.snapshot(backup, tmp_path / "rejected", restoring=True, port=unused_port())
    assert not (tmp_path / "rejected").exists()


def test_occupied_port_never_reuses_existing_listener():
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with pytest.raises(OSError):
            demo.free_port(listener.getsockname()[1])


def test_start_checks_identity_and_excludes_shared_environment(tmp_path, monkeypatch):
    code = {"sha256": "approved", "python": "test", "packages": {}}
    demo.write_json(
        tmp_path / "instance.json",
        {
            "kind": demo.MARKER,
            "id": "test-instance",
            "port": unused_port(),
            "code": code,
        },
    )
    monkeypatch.setattr(demo, "code_identity", lambda: code | {"sha256": "changed"})
    with pytest.raises(ValueError, match="Code/runtime changed"):
        demo.start(tmp_path)
    monkeypatch.setattr(demo, "code_identity", lambda: code)
    monkeypatch.setattr(demo.os, "chdir", lambda path: None)
    monkeypatch.setenv("OCEANPILOT_FEISHU_APP_SECRET", "must-not-inherit")
    monkeypatch.setenv("OCEANPILOT_CHARGEBACK_DB_PATH", "/shared/do-not-open.db")
    calls = []
    monkeypatch.setattr(demo.os, "execve", lambda exe, args, env: calls.append((args, env)))
    demo.start(tmp_path)
    args, env = calls[0]
    assert args[args.index("--host") + 1] == "127.0.0.1"
    assert "OCEANPILOT_FEISHU_APP_SECRET" not in env
    assert Path(env["OCEANPILOT_CHARGEBACK_DB_PATH"]) == tmp_path / "chargeback.db"
    assert env["OCEANPILOT_CHARGEBACK_LIVE_MODEL"] == "0"
    assert env["OCEANPILOT_V2_UPSTREAM_MODE"] == "mock"


def test_explicit_live_model_config_copies_only_model_keys(tmp_path, monkeypatch):
    code = {"sha256": "approved", "python": "test", "packages": {}}
    demo.write_json(
        tmp_path / "instance.json",
        {
            "kind": demo.MARKER,
            "id": "test-live-instance",
            "port": unused_port(),
            "code": code,
        },
    )
    config = tmp_path / "private.env"
    config.write_text(
        "DEEPSEEK_API_KEY=test-only\nDEEPSEEK_API_BASE=https://example.invalid\nFEISHU_APP_SECRET=excluded\nOCEANPILOT_CHARGEBACK_DB_PATH=/shared/excluded.db\n"
    )
    monkeypatch.setattr(demo, "code_identity", lambda: code)
    monkeypatch.setattr(demo.os, "chdir", lambda path: None)
    calls = []
    monkeypatch.setattr(demo.os, "execve", lambda exe, args, env: calls.append(env))
    demo.start(tmp_path, model_config=config, model_name="deepseek-v4-flash")
    env = calls[0]
    assert env["DEEPSEEK_MODEL"] == "deepseek-v4-flash"
    assert env["OCEANPILOT_CHARGEBACK_LIVE_MODEL"] == "1"
    assert "FEISHU_APP_SECRET" not in env
    assert env["OCEANPILOT_CHARGEBACK_DB_PATH"] == str(tmp_path / "chargeback.db")
    assert "test-only" not in next(tmp_path.glob("run-*.json")).read_text()
