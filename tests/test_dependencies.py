"""
Every third-party module imported by the package or the tests is a declared dependency
(pyproject.toml), or the import is guarded (try/except ImportError, pytest.importorskip).
CI installs only the declared ones; a test importing scipy passed on a development machine
that happened to have it and failed on all three CI systems.
"""
import ast
import sys
from pathlib import Path

import pytest

import helios

# Import name -> distribution in pyproject.toml (dependencies and the dev/build/solar extras).
DECLARED = {"fastapi", "uvicorn", "pydantic", "httpx", "numpy", "pandas", "matplotlib", "spiceypy",
            "platformdirs", "webview", "cdflib", "pytest", "PIL", "PyInstaller", "sunpy", "sunkit_magex",
            # installed with a declared one: starlette, anyio (fastapi), contourpy (matplotlib),
            # astropy (sunpy, used only next to it)
            "starlette", "anyio", "contourpy", "astropy"}
GUARDS = ("ImportError", "ModuleNotFoundError", "Exception")


def _unguarded_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skipped = {n.args[0].value.split(".")[0] for n in ast.walk(tree)
               if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "importorskip"
               and n.args and isinstance(n.args[0], ast.Constant)}
    guarded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(
                any(g in ast.unparse(h.type) for g in GUARDS) for h in node.handlers if h.type is not None):
            for inner in node.body:
                guarded.update(id(n) for n in ast.walk(inner))
    for node in ast.walk(tree):
        if id(node) in guarded:
            continue
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if top not in skipped:
                yield top, node.lineno


def test_imports_are_declared_dependencies():
    roots = [Path(helios.__file__).parent, Path(__file__).parent]
    local = {p.stem for p in Path(__file__).parent.glob("*.py")} | {"helios"}
    bad = []
    for root in roots:
        for path in root.rglob("*.py"):
            for top, line in _unguarded_imports(path):
                if top in sys.stdlib_module_names or top in local or top in DECLARED:
                    continue
                bad.append(f"{path.name}:{line} {top}")
    assert not bad, "undeclared imports: " + ", ".join(bad)
