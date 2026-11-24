"""O Compose tem de **encaminhar** as variáveis que o código já lê (W0B.1, R1/P-07).

`docker compose config` mostrar a variável não prova proteção nenhuma — isso é o argumento da P-07.
O que este teste fixa é só o encaminhamento: o container do `renderer` precisa **receber** o guard
de orçamento (`STUDIO_BUDGET_GUARD`) e o modo de produção (`STUDIO_PRODUCTION_MODE`), com default
seguro e documentado. A proteção em si (limite por canal bloqueando a chamada paga antes do efeito
externo, inclusive sob concorrência) tem prova própria em `test_budget_guard_wiring.py`.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _service_environment(text, service):
    """Extrai o mapeamento `environment:` de um serviço do Compose, sem PyYAML (não há no container)."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip() == f"  {service}:")
    environment, inside, env_indent = {}, False, 0
    for line in lines[start + 1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= 2:  # saiu do serviço
            break
        if stripped == "environment:":
            inside, env_indent = True, indent
            continue
        if not inside:
            continue
        if indent <= env_indent:  # saiu do bloco environment
            inside = False
            continue
        key, _, value = stripped.partition(":")
        environment[key.strip()] = value.strip()
    return environment


def test_compose_forwards_the_budget_guard_and_the_production_mode():
    environment = _service_environment((ROOT / "docker-compose.yml").read_text(encoding="utf-8"), "renderer")
    assert environment["STUDIO_BUDGET_GUARD"] == "${STUDIO_BUDGET_GUARD:-1}"
    assert environment["STUDIO_PRODUCTION_MODE"] == "${STUDIO_PRODUCTION_MODE:-BUDGET_GUARDED}"


def test_env_example_documents_the_guard_the_mode_and_the_ceiling_prerequisite():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^STUDIO_BUDGET_GUARD=1$", text, flags=re.M), "o default documentado é o guard ligado"
    assert re.search(r"^STUDIO_PRODUCTION_MODE=BUDGET_GUARDED$", text, flags=re.M)
    assert "INTERACTIVE" in text and "BUDGET_GUARDED" in text, "os valores aceitos precisam estar documentados"
    assert "MAX_COST_USD_PER_VIDEO" in text, "o pré-requisito dos tetos precisa estar documentado"


def test_compose_forwards_the_provider_production_flag_and_the_secrets_root():
    """Achado 4: as duas variáveis lidas por `Settings.from_env` também precisam chegar ao container."""
    environment = _service_environment((ROOT / "docker-compose.yml").read_text(encoding="utf-8"), "renderer")
    assert environment["STUDIO_PROVIDER_PRODUCTION"] == "${STUDIO_PROVIDER_PRODUCTION:-}"
    assert environment["STUDIO_SECRETS_ROOT"] == "${STUDIO_SECRETS_ROOT:-}"


def test_env_example_documents_the_provider_production_flag():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^STUDIO_PROVIDER_PRODUCTION=$", text, flags=re.M)
    assert re.search(r"^STUDIO_SECRETS_ROOT=$", text, flags=re.M)


import re as _re
import sys

sys.path.insert(0, str(ROOT / "renderer"))

from app.studio.composition import Settings  # noqa: E402


def _resolve_compose(value, env):
    """Resolve `${VAR:-padrão}` como o Compose: vazio/ausente usa o padrão."""
    def sub(match):
        name, default = match.group(1), match.group(3) or ""
        return env.get(name) or default
    return _re.sub(r"\$\{([A-Z0-9_]+)(:-([^}]*))?\}", sub, value)


def _renderer_env(env):
    declared = _service_environment((ROOT / "docker-compose.yml").read_text(encoding="utf-8"), "renderer")
    return {key: _resolve_compose(value, env) for key, value in declared.items()}


def test_compose_forwards_the_publication_switch_with_a_safe_default():
    declared = _service_environment((ROOT / "docker-compose.yml").read_text(encoding="utf-8"), "renderer")
    assert declared["STUDIO_PUBLICATION_ENABLED"] == "${STUDIO_PUBLICATION_ENABLED:-1}"


def test_publication_default_is_never_empty_because_empty_disables_it():
    # `_flag("")` é falso: um default vazio desligaria a publicação em silêncio.
    assert Settings.from_env({"STUDIO_PUBLICATION_ENABLED": ""}).publication_enabled is False
    assert _renderer_env({})["STUDIO_PUBLICATION_ENABLED"] == "1"
    assert Settings.from_env(_renderer_env({})).publication_enabled is True


def test_env_zero_reaches_settings_through_compose_and_blocks_the_uploader(tmp_path):
    from test_publication_execution import use  # fábrica de dublês já usada nos testes F01.T04
    from app.studio.application.publication_execution import PublicationResult
    settings = Settings.from_env(_renderer_env({"STUDIO_PUBLICATION_ENABLED": "0"}))
    assert settings.publication_enabled is False
    run, pubs, uploads, tokens = use(tmp_path, enabled=settings.publication_enabled)
    assert run.execute().result is PublicationResult.BLOCKED
    assert uploads.uploads == [] and tokens.calls == 0 and pubs.calls == []


def test_env_example_documents_the_publication_switch_enabled_by_default():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert _re.search(r"^STUDIO_PUBLICATION_ENABLED=1$", text, flags=_re.M)
