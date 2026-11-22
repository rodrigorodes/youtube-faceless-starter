import ast
import re
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[1] / "renderer" / "app" / "studio"
IO = {"fastapi", "psycopg", "httpx", "subprocess", "requests", "os", "socket", "urllib.request", "http.client", "sqlalchemy"}  # urllib.parse é puro (sem I/O) e permitido
# O núcleo de render (domain + application) não pode tocar mídia nem SDK de provedor:
# é o princípio "Core não importa FFmpeg ou SDKs de IA" e o que torna o compilador do
# Render Plan puro (RP-023). Sem esta lista, a regra valeria por disciplina, não por CI.
MEDIA = {"PIL", "numpy", "cv2", "ffmpeg", "moviepy", "av"}
PROVIDER_SDKS = {"openai", "anthropic", "elevenlabs", "fal_client", "boto3", "google"}
CORE_FORBIDDEN = (*IO, *MEDIA, *PROVIDER_SDKS)


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


def test_render_core_has_no_media_or_provider_sdks():
    """O núcleo de render é puro: nada de mídia (FFmpeg/PIL/numpy) nem SDK de provedor.

    É a fronteira que sustenta o compilador puro do Render Plan (RP-023) e o princípio
    "Core não importa FFmpeg ou SDKs de IA" — precisa falhar por execução, não por disciplina.
    """
    for layer in ("domain", "application"):
        found = violates(imports_of(layer), (*IO, *MEDIA, *PROVIDER_SDKS))
        assert found == set(), f"{layer} importa mídia/SDK de provedor: {sorted(found)}"


def test_media_and_provider_guard_catches_violations(tmp_path):
    """Prova que a guarda é load-bearing: a violação tem de ser detectada, não ignorada."""
    (tmp_path / "domain").mkdir()
    (tmp_path / "domain" / "x.py").write_text("import numpy\nfrom PIL import Image\nfrom openai import OpenAI\n")
    found = imports_of("domain", tmp_path)
    media = violates(found, MEDIA)
    assert {"numpy", "PIL"} <= media, media  # "from PIL import Image" registra PIL e PIL.Image
    assert "openai" in violates(found, PROVIDER_SDKS)


def test_imports_of_resolves_relative_and_named_imports(tmp_path):
    (tmp_path / "application").mkdir()
    (tmp_path / "application" / "x.py").write_text(
        "from .. import adapters\nfrom app.studio import api\nfrom ..adapters.postgres import repo\nimport os\n")
    found = imports_of("application", tmp_path)
    assert {"app.studio.adapters", "app.studio.api", "app.studio.adapters.postgres.repo", "os"} <= found
    assert violates(found, ("app.studio.adapters", "app.studio.api", "os"))


# VE-03: o nome do fornecedor de mídia só pode aparecer no adaptador e na composição.
# A guarda de imports não pega um ``if provider == "pexels"`` escrito no núcleo; esta pega.
MEDIA_VENDOR_NAMES = ("pexels", "pixabay")


def test_domain_and_application_do_not_name_media_vendors():
    for layer in ("domain", "application"):
        for path in (STUDIO / layer).rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for vendor in MEDIA_VENDOR_NAMES:
                assert vendor not in text, f"{path} cita fornecedor de mídia {vendor!r}"


# S7: a guarda de imports não pega nome de fornecedor em string/constante/identificador.
# Esta guarda lê o AST e compara **token exato**, em minúsculas; "metadata" não é "meta" e
# "falcon" não é "fal". Docstrings são prosa e ficam de fora.
SUPPLIER_NAMES = {
    "opencode", "piper", "pexels", "pixabay", "elevenlabs", "openai", "anthropic", "veo",
    "capcut", "fal", "replicate", "stability", "minimax", "kling", "runway",
}
# Identidade do produto em `domain/youtube_identity.py` (canal e conta do produto).
PRODUCT_NAME_ALLOWLIST = {"youtube", "google"}
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_SPLIT.split(text.lower()) if token}


def _docstring_nodes(tree: ast.Module) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                found.add(id(body[0].value))
    return found


def supplier_names_in(layer: str, studio: Path = STUDIO) -> set[tuple[str, int, str]]:
    """Nomes de fornecedor citados como código (não prosa) em uma camada."""
    hits: set[tuple[str, int, str]] = set()
    for path in (studio / layer).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in docstrings:
                    continue
                values = [node.value]
            elif isinstance(node, ast.Name):
                values = [node.id]
            elif isinstance(node, ast.Attribute):
                values = [node.attr]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                values = [node.name]
            else:
                continue
            for value in values:
                for token in _tokens(value):
                    if token in SUPPLIER_NAMES and token not in PRODUCT_NAME_ALLOWLIST:
                        hits.add((str(path.relative_to(studio)), node.lineno, token))
    return hits


def test_domain_does_not_name_concrete_suppliers():
    """O domínio não conhece nome de fornecedor concreto (S1/S7 do guia de isolamento)."""
    assert supplier_names_in("domain") == set()


def test_supplier_name_guard_is_load_bearing(tmp_path):
    """Prova que a guarda morde: string, constante e identificador; e não morde prosa."""
    (tmp_path / "domain").mkdir()
    (tmp_path / "domain" / "violation.py").write_text(
        '"""Docstring pode citar piper sem virar conhecimento do domínio."""\n'
        'KNOWN = {"piper", "placeholder"}\n'
        'def route(pexels):\n'
        '    return pexels\n'
        'METADATA = "metadata"\n'
        'BIRD = "falcon"\n',
        encoding="utf-8",
    )
    found = supplier_names_in("domain", tmp_path)
    tokens = {token for _, _, token in found}
    assert {"piper", "pexels"} <= tokens
    assert "fal" not in tokens and "meta" not in tokens
