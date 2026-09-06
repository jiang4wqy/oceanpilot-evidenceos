"""Launcher configuration tests; never start a server or touch project databases."""

import sys

import pytest

from scripts import run_local_demo as launcher


def test_offline_mode_overrides_live_configuration_and_uses_persistent_local_paths(tmp_path):
    command, environment = launcher.build_launch(
        tmp_path,
        "offline",
        8026,
        {
            "OCEANPILOT_CHARGEBACK_LIVE_MODEL": "1",
            "OCEANPILOT_MODEL_PROVIDER": "claude",
            "OCEANPILOT_MOCK_SEND_ENABLED": "1",
            "PYTHONPATH": "/unrelated/project",
        },
    )
    assert command == [
        sys.executable,
        "-m",
        "uvicorn",
        "oceanpilot.main:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "8026",
    ]
    assert environment["OCEANPILOT_CHARGEBACK_LIVE_MODEL"] == "0"
    assert environment["OCEANPILOT_MODEL_PROVIDER"] == "deepseek"
    assert environment["OCEANPILOT_MOCK_SEND_ENABLED"] == "0"
    assert environment["PYTHONPATH"] == str(tmp_path / "src")
    assert environment["OCEANPILOT_DB_PATH"] == str(tmp_path / "work/local-demo/core.db")
    assert environment["OCEANPILOT_CHARGEBACK_DB_PATH"].endswith("oceanpilot-chargeback.db")
    assert environment["OCEANPILOT_RULES_DB_PATH"].endswith("oceanpilot-rules.db")
    assert not (tmp_path / "work").exists()


def test_live_loads_project_dotenv_but_preserves_explicit_shell_settings(tmp_path):
    (tmp_path / ".env").write_text(
        "DEEPSEEK_API_KEY=synthetic-test-credential\n"
        "OCEANPILOT_DB_PATH=work/saved-core.db\n"
        "OCEANPILOT_CHARGEBACK_DB_PATH=work/saved-cases.db\n",
        encoding="utf-8",
    )
    command, environment = launcher.build_launch(
        tmp_path, "live", 8123, {"OCEANPILOT_DB_PATH": "work/explicit-core.db"}
    )
    assert environment["DEEPSEEK_API_KEY"] == "synthetic-test-credential"
    assert environment["OCEANPILOT_DB_PATH"] == "work/explicit-core.db"
    assert environment["OCEANPILOT_CHARGEBACK_DB_PATH"] == "work/saved-cases.db"
    assert environment["OCEANPILOT_CHARGEBACK_LIVE_MODEL"] == "1"
    assert command[-2:] == ["--port", "8123"]
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize("key", [None, "", "   "])
def test_live_without_nonempty_key_fails_before_starting(tmp_path, key):
    environment = {} if key is None else {"DEEPSEEK_API_KEY": key}
    with pytest.raises(ValueError, match="配置未就绪.*DEEPSEEK_API_KEY"):
        launcher.build_launch(tmp_path, "live", 8026, environment)


def test_main_uses_script_root_and_calling_python_without_exposing_key(
    tmp_path, monkeypatch, capsys
):
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=synthetic-console-canary\n")
    monkeypatch.setattr(launcher, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(launcher.os, "environ", {})
    observed = {}
    monkeypatch.setattr(launcher.os, "chdir", lambda path: observed.update(cwd=path))
    monkeypatch.setattr(
        launcher.os,
        "execvpe",
        lambda executable, command, environment: observed.update(
            executable=executable, command=command, environment=environment
        ),
    )
    assert launcher.main(["--mode", "live"]) == 0
    assert observed["cwd"] == tmp_path
    assert observed["executable"] == sys.executable
    assert observed["environment"]["DEEPSEEK_API_KEY"] == "synthetic-console-canary"
    output = capsys.readouterr()
    assert "synthetic-console-canary" not in output.out + output.err
    assert "http://127.0.0.1:8026/demo" in output.out
    assert "每次输出来源以页面为准" in output.out


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_invalid_port_is_rejected_before_loading_configuration(port, monkeypatch):
    monkeypatch.setattr(
        launcher, "build_launch", lambda *_: pytest.fail("invalid input read configuration")
    )
    with pytest.raises(SystemExit) as error:
        launcher.main(["--port", port])
    assert error.value.code == 2
