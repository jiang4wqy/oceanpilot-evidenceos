"""Start the existing local demo with explicit live/offline configuration."""

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from importlib.util import find_spec
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_launch(
    project_root: Path,
    mode: str,
    port: int,
    inherited_environment: Mapping[str, str],
) -> tuple[list[str], dict[str, str]]:
    """Prepare a command without starting a process or opening any database."""
    if mode not in ("live", "offline") or not 1 <= port <= 65535:
        raise ValueError("启动模式或端口无效。")
    try:
        from dotenv import dotenv_values
    except ImportError as exc:
        raise ValueError(
            "当前 Python 环境缺少 python-dotenv，请使用已安装项目依赖的环境。"
        ) from exc

    root = project_root.resolve()
    environment = {
        key: value for key, value in dotenv_values(root / ".env").items() if value is not None
    }
    # Explicit shell settings take precedence over .env; CLI mode always wins.
    environment.update(inherited_environment)
    if mode == "live" and not environment.get("DEEPSEEK_API_KEY", "").strip():
        raise ValueError(
            "配置未就绪：live 模式需要 DEEPSEEK_API_KEY，请在项目 .env 或环境变量中配置；"
            "也可明确选择 --mode offline。"
        )
    environment["PYTHONPATH"] = str(root / "src")
    environment["OCEANPILOT_CHARGEBACK_LIVE_MODEL"] = "1" if mode == "live" else "0"
    environment["OCEANPILOT_MODEL_PROVIDER"] = "deepseek"
    environment["OCEANPILOT_MOCK_SEND_ENABLED"] = "0"
    data_root = root / "work" / "local-demo"
    for variable, filename in (
        ("OCEANPILOT_DB_PATH", "core.db"),
        ("OCEANPILOT_CHARGEBACK_DB_PATH", "oceanpilot-chargeback.db"),
        ("OCEANPILOT_RULES_DB_PATH", "oceanpilot-rules.db"),
    ):
        if not environment.get(variable):
            environment[variable] = str(data_root / filename)
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "oceanpilot.main:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    return command, environment


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("端口必须为 1–65535 的整数。") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("端口必须为 1–65535 的整数。")
    return port


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("live", "offline"), default="offline")
    parser.add_argument("--port", type=_port, default=8026)
    args = parser.parse_args(argv)
    try:
        command, environment = build_launch(PROJECT_ROOT, args.mode, args.port, os.environ)
        if find_spec("uvicorn") is None:
            raise ValueError("当前 Python 环境缺少 uvicorn，请使用已安装项目依赖的环境。")
    except ValueError as exc:
        parser.error(str(exc))

    mode_label = (
        "DeepSeek live 配置（每次输出来源以页面为准）" if args.mode == "live" else "离线模式"
    )
    print(f"准备启动：{mode_label}", flush=True)
    print(f"用户端：http://127.0.0.1:{args.port}/demo", flush=True)
    print(f"业务端：http://127.0.0.1:{args.port}/business", flush=True)
    os.chdir(PROJECT_ROOT)
    # Replace this process so Ctrl-C reaches uvicorn directly; no background service.
    os.execvpe(command[0], command, environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
