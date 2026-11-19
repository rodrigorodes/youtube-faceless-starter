import ast
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[1] / "renderer" / "app" / "studio"
IO = {"fastapi", "psycopg", "httpx", "subprocess", "requests", "os", "socket", "urllib.request", "http.client", "sqlalchemy"}  # urllib.parse é puro (sem I/O) e permitido


def imports_of(layer: str, studio: Path = STUDIO) -> set[str]:
    found = set()
    for path in (studio / layer).rglob("*.py"):
        module = ".".join(("app", "studio", layer, *path.relative_to(studio / layer).with_suffix("").parts))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parent = module.split(".")[: -node.level]
                    base = ".".join(parent + ([base] if base else []))
                found.add(base)
                found |= {f"{base}.{a.name}" for a in node.names}  # "from .. import adapters" importa o submódulo
    return found


def violates(imports: set[str], forbidden: tuple[str, ...]) -> set[str]:
    return {i for i in imports if any(i == f or i.startswith(f + ".") for f in forbidden)}


def test_domain_has_no_outward_or_io_imports():
    assert violates(imports_of("domain"), ("app.studio.application", "app.studio.adapters", "app.studio.api", "app.studio.composition", *IO)) == set()


def test_application_only_imports_domain():
    assert violates(imports_of("application"), ("app.studio.adapters", "app.studio.api", "app.studio.composition", *IO)) == set()


def test_api_does_not_touch_adapters_or_database():
    assert violates(imports_of("api"), ("app.studio.adapters", "psycopg")) == set()


def test_imports_of_resolves_relative_and_named_imports(tmp_path):
    (tmp_path / "application").mkdir()
    (tmp_path / "application" / "x.py").write_text(
        "from .. import adapters\nfrom app.studio import api\nfrom ..adapters.postgres import repo\nimport os\n")
    found = imports_of("application", tmp_path)
    assert {"app.studio.adapters", "app.studio.api", "app.studio.adapters.postgres.repo", "os"} <= found
    assert violates(found, ("app.studio.adapters", "app.studio.api", "os"))
