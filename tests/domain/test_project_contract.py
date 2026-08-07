import sys


def test_runtime_is_python_312() -> None:
    assert sys.version_info[:2] == (3, 12)


def test_package_exposes_version() -> None:
    from oceanpilot import __version__

    assert __version__ == "0.2.0"
