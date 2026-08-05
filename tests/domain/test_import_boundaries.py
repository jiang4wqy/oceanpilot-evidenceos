import ast
from collections.abc import Iterable
from pathlib import Path

import pytest

SRC_ROOT = Path("src")
DOMAIN_ROOT = SRC_ROOT / "oceanpilot" / "domain"
APPLICATION_ROOT = SRC_ROOT / "oceanpilot" / "application"
TASK5_APPLICATION_MODULES = tuple(
    APPLICATION_ROOT / name for name in ("commands.py", "errors.py", "ports.py")
)

DOMAIN_FORBIDDEN = (
    "fastapi",
    "sqlite3",
    "oceanpilot.api",
    "oceanpilot.application",
    "oceanpilot.adapters",
)
APPLICATION_FORBIDDEN = (
    "fastapi",
    "sqlite3",
    "oceanpilot.api",
    "oceanpilot.adapters",
)
APPLICATION_FORBIDDEN_IMPORTED_NAMES = (
    "EvidenceSource",
    "SyntheticScenario",
)


def _package_for(path: Path) -> tuple[str, ...]:
    relative = path.relative_to(SRC_ROOT).with_suffix("")
    return relative.parts[:-1]


def _import_targets(tree: ast.AST, package: tuple[str, ...]) -> tuple[str, ...]:
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module is not None:
                    targets.append(node.module)
                    targets.extend(f"{node.module}.{alias.name}" for alias in node.names)
                continue
            retained = len(package) - (node.level - 1)
            base = package[:retained]
            if node.module is not None:
                module = ".".join((*base, *node.module.split(".")))
                targets.append(module)
                targets.extend(f"{module}.{alias.name}" for alias in node.names)
            else:
                targets.extend(".".join((*base, alias.name)) for alias in node.names)
    return tuple(targets)


def _imported_names(tree: ast.AST) -> tuple[str, ...]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name.rsplit(".", 1)[-1] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.extend(alias.name for alias in node.names)
    return tuple(names)


def _is_forbidden(target: str, forbidden_roots: Iterable[str]) -> bool:
    return any(target == root or target.startswith(f"{root}.") for root in forbidden_roots)


def _boundary_violations(
    root: Path,
    forbidden_roots: tuple[str, ...],
    *,
    forbidden_names: tuple[str, ...] = (),
) -> list[str]:
    violations: list[str] = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for target in _import_targets(tree, _package_for(path)):
            if _is_forbidden(target, forbidden_roots):
                violations.append(f"{path.as_posix()}: {target}")
        for imported_name in _imported_names(tree):
            if imported_name in forbidden_names:
                violations.append(f"{path.as_posix()}: {imported_name}")
    return violations


def _class_definition_paths(root: Path, class_name: str) -> tuple[str, ...]:
    paths: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, ast.ClassDef) and node.name == class_name for node in ast.walk(tree)
        ):
            paths.append(path.relative_to(root).as_posix())
    return tuple(paths)


def _imported_symbol_paths(root: Path, symbol: str) -> tuple[str, ...]:
    paths: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if symbol in _imported_names(tree):
            paths.append(path.relative_to(root).as_posix())
    return tuple(paths)


def _imported_names_for_paths(
    paths: Iterable[Path],
    forbidden_names: tuple[str, ...],
) -> tuple[str, ...]:
    violations: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for imported_name in _imported_names(tree):
            if imported_name in forbidden_names:
                violations.append(f"{path.relative_to(SRC_ROOT).as_posix()}: {imported_name}")
    return tuple(violations)


@pytest.mark.parametrize(
    ("source", "package", "expected"),
    (
        ("import oceanpilot.adapters", ("oceanpilot", "domain"), "oceanpilot.adapters"),
        ("from oceanpilot.adapters import x", ("oceanpilot", "domain"), "oceanpilot.adapters"),
        ("from .. import adapters", ("oceanpilot", "domain"), "oceanpilot.adapters"),
        ("from ..adapters import x", ("oceanpilot", "domain"), "oceanpilot.adapters"),
        ("from . import api", ("oceanpilot", "application"), "oceanpilot.application.api"),
    ),
)
def test_ast_import_resolution_covers_absolute_and_relative_forms(
    source: str,
    package: tuple[str, ...],
    expected: str,
) -> None:
    assert expected in _import_targets(ast.parse(source), package)


@pytest.mark.parametrize(
    ("source", "package", "forbidden_root"),
    (
        ("from oceanpilot import adapters", ("oceanpilot", "domain"), "oceanpilot.adapters"),
        (
            "from oceanpilot import application",
            ("oceanpilot", "domain"),
            "oceanpilot.application",
        ),
        ("from oceanpilot import api", ("oceanpilot", "application"), "oceanpilot.api"),
    ),
)
def test_combined_absolute_imports_reach_the_boundary_predicate(
    source: str,
    package: tuple[str, ...],
    forbidden_root: str,
) -> None:
    targets = _import_targets(ast.parse(source), package)
    assert forbidden_root in targets
    assert any(_is_forbidden(target, (forbidden_root,)) for target in targets)


@pytest.mark.parametrize(
    ("source", "forbidden_name"),
    (
        (
            "from oceanpilot.domain.diagnosis import DiagnosisEngine as _Alias",
            "DiagnosisEngine",
        ),
        ("from ..domain.diagnosis import DiagnosisEngine as _Alias", "DiagnosisEngine"),
        ("from oceanpilot.application.ports import EvidenceSource as Hidden", "EvidenceSource"),
        ("from .ports import SyntheticScenario as Hidden", "SyntheticScenario"),
    ),
)
def test_imported_symbol_scan_uses_original_name_not_alias(
    source: str,
    forbidden_name: str,
) -> None:
    assert forbidden_name in _imported_names(ast.parse(source))


def test_domain_import_boundary_has_no_forbidden_dependencies() -> None:
    assert _boundary_violations(DOMAIN_ROOT, DOMAIN_FORBIDDEN) == []


def test_application_import_boundary_has_no_forbidden_dependencies() -> None:
    assert (
        _boundary_violations(
            APPLICATION_ROOT,
            APPLICATION_FORBIDDEN,
            forbidden_names=APPLICATION_FORBIDDEN_IMPORTED_NAMES,
        )
        == []
    )


def test_task_five_modules_do_not_import_outer_protocols_under_aliases() -> None:
    assert (
        _imported_names_for_paths(
            TASK5_APPLICATION_MODULES,
            ("DiagnosisEngine", "EvidenceSource", "SyntheticScenario"),
        )
        == ()
    )


def test_future_case_service_may_import_the_domain_diagnosis_engine() -> None:
    source = "from oceanpilot.domain.diagnosis import DiagnosisEngine"
    tree = ast.parse(source)
    targets = _import_targets(tree, ("oceanpilot", "application"))

    assert not any(_is_forbidden(target, APPLICATION_FORBIDDEN) for target in targets)
    assert not any(name in APPLICATION_FORBIDDEN_IMPORTED_NAMES for name in _imported_names(tree))


def test_engine_and_source_protocol_ownership_is_unique_across_src() -> None:
    assert _class_definition_paths(SRC_ROOT, "DiagnosisEngine") == (
        "oceanpilot/domain/diagnosis.py",
    )
    assert _class_definition_paths(SRC_ROOT, "EvidenceSource") == ()
    assert _imported_symbol_paths(SRC_ROOT, "EvidenceSource") == ()


def test_boundary_predicate_rejects_submodules_but_allows_domain_values() -> None:
    assert _is_forbidden("oceanpilot.adapters.persistence.sqlite", DOMAIN_FORBIDDEN)
    assert _is_forbidden("oceanpilot.api.schemas", APPLICATION_FORBIDDEN)
    assert not _is_forbidden("oceanpilot.domain.models", APPLICATION_FORBIDDEN)
