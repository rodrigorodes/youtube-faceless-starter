import ast
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[1] / "renderer" / "app" / "studio"
IO = {"fastapi", "psycopg", "httpx", "subprocess", "requests"}


def imports_of(layer: str) -> set[str]:
    found = set()
    for path in (STUDIO / layer).rglob("*.py"):
        module = ".".join(("app", "studio", layer, *path.relative_to(STUDIO / layer).with_suffix("").parts))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parent = module.split(".")[: -node.level]
                    base = ".".join(parent + ([base] if base else []))
                found.add(base)
    return found


def violates(imports: set[str], forbidden: tuple[str, ...]) -> set[str]:
    return {i for i in imports if any(i == f or i.startswith(f + ".") for f in forbidden)}


def test_domain_has_no_outward_or_io_imports():
    assert violates(imports_of("domain"), ("app.studio.application", "app.studio.adapters", "app.studio.api", "app.studio.composition", *IO)) == set()


def test_application_only_imports_domain():
    assert violates(imports_of("application"), ("app.studio.adapters", "app.studio.api", "app.studio.composition", *IO)) == set()


def test_api_does_not_touch_adapters_or_database():
    assert violates(imports_of("api"), ("app.studio.adapters", "psycopg")) == set()


def test_detector_catches_a_violation(tmp_path):
    bad = tmp_path / "x.py"
    bad.write_text("from ..adapters import y\nimport psycopg\n")
    tree = ast.parse(bad.read_text())
    assert any(isinstance(n, ast.ImportFrom) and n.level == 2 for n in ast.walk(tree))
    assert violates({"psycopg", "app.studio.adapters.y"}, ("app.studio.adapters", "psycopg")) == {"psycopg", "app.studio.adapters.y"}
