import zipfile
from pathlib import Path
from subprocess import run


def test_built_wheel_contains_all_demo_assets(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    result = run(
        [
            "py",
            "-3.12",
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(tmp_path),
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    wheel = next(tmp_path.glob("oceanpilot_evidenceos-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        packaged = set(archive.namelist())

    assert {
        "oceanpilot/static/demo/index.html",
        "oceanpilot/static/demo/case.html",
        "oceanpilot/static/demo/styles.css",
        "oceanpilot/static/demo/app.js",
    } <= packaged
