"""The build fails if the validator imports anything from this repo."""

import ast
from pathlib import Path

VALIDATE_DIR = Path(__file__).resolve().parent
REPO = VALIDATE_DIR.parent
REPO_MODULES = {p.stem for p in REPO.glob("*.py")} | {
    p.name for p in REPO.iterdir() if (p / "__init__.py").exists()
}
ALLOWED_REPO_MODULES = {"validate"}


def imported_roots(path: Path) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_validator_imports_nothing_from_the_repo():
    sources = [p for p in VALIDATE_DIR.glob("*.py") if not p.name.startswith("test_")]
    assert sources
    offenders = {p.name: sorted(imported_roots(p) & (REPO_MODULES - ALLOWED_REPO_MODULES)) for p in sources}
    offenders = {k: v for k, v in offenders.items() if v}
    assert not offenders, f"validate/ must not import repo code: {offenders}"


def test_planner_is_a_repo_module_the_check_would_catch():
    assert {"planner", "baselines", "sim", "cost_model", "scenarios"} <= REPO_MODULES
