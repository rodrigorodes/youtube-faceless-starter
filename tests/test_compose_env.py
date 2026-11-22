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
