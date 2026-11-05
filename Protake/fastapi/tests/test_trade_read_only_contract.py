"""Locks in the "isolated trade brain" property the architecture depends
on: a trade engine's calculate() reads approved Room/Wall/Detection
objects and returns a TradeResult — it never mutates shared geometry and
never touches the database directly. Static AST checks rather than
runtime mocking, so this can't be defeated by a code path that happens
not to run under the current test fixtures.
"""

import ast
from pathlib import Path

import pytest

TRADES_DIR = Path(__file__).parent.parent / "app" / "trades"
ENGINE_FILES = ["drywall.py", "painting.py", "flooring.py", "roofing.py"]

# Names a trade engine has no legitimate reason to import — their
# presence means the engine is reaching past its read-only geometry
# inputs into persistence, which breaks per-trade failure isolation.
FORBIDDEN_IMPORT_NAMES = {"Session", "sessionmaker"}
FORBIDDEN_IMPORT_MODULES_PREFIXES = ("app.repositories", "sqlalchemy.orm")

# Attribute names that, if assigned on any object, would indicate the
# engine is writing back onto the Room/Wall rows it was handed instead
# of only reading them.
FORBIDDEN_MUTATED_ATTRS = {
    "room_type", "floor_finish", "wall_finish", "ceiling_finish",  # Room
    "wall_type", "wall_type_code", "roof_feature", "thickness_ft",  # Wall
    "status", "confidence",  # shared on both
}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@pytest.mark.parametrize("filename", ENGINE_FILES)
def test_engine_never_imports_persistence_layer(filename):
    tree = _parse(TRADES_DIR / filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(FORBIDDEN_IMPORT_MODULES_PREFIXES):
                pytest.fail(f"{filename} imports from {module!r} — trade engines must not touch persistence directly")
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORT_NAMES:
                    pytest.fail(f"{filename} imports {alias.name!r} from {module!r} — a pure calculator has no use for a DB session")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORT_NAMES or alias.name.startswith(FORBIDDEN_IMPORT_MODULES_PREFIXES):
                    pytest.fail(f"{filename} imports {alias.name!r} — trade engines must not touch persistence directly")


@pytest.mark.parametrize("filename", ENGINE_FILES)
def test_engine_never_calls_db_write_methods(filename):
    """`db.add(...)` / `session.commit()` / `.create(...)` style calls
    would mean the engine is persisting, not just calculating.
    """
    tree = _parse(TRADES_DIR / filename)
    forbidden_calls = {"add", "commit", "flush", "merge", "create", "delete"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden_calls:
                pytest.fail(
                    f"{filename} calls .{node.func.attr}(...) — a trade engine must only read rooms/walls "
                    "and return a TradeResult, never write to the database"
                )


@pytest.mark.parametrize("filename", ENGINE_FILES)
def test_engine_never_assigns_geometry_attributes(filename):
    """Catches `wall.roof_feature = ...` / `room.room_type = ...` style
    mutation of the Room/Wall objects the engine was handed — those
    objects must be treated as read-only snapshots.
    """
    tree = _parse(TRADES_DIR / filename)
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr in FORBIDDEN_MUTATED_ATTRS:
                pytest.fail(
                    f"{filename} assigns to `.{target.attr}` — trade engines must not mutate the shared "
                    "Room/Wall rows they were handed; store any trade-owned interpretation separately"
                )
