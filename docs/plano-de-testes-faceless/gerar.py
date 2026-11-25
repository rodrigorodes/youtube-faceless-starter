#!/usr/bin/env python3
"""Gera os capítulos Markdown do plano de testes Faceless a partir de dados/*.yaml.

Modelo: `.ai-analysis/GC_MVP/stg-teste/plano-de-testes-gc` (narrativo, gerado de dados).
Os arquivos .md são saída: não editar à mão. A fonte única é `dados/`.

Uso:
    python3 gerar.py            # gera todos os capítulos
    python3 gerar.py --check    # falha se algum .md estiver desatualizado
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DADOS = AQUI / "dados"
IGNORAR = {"funcionalidades.yaml", "regras.yaml"}


def _texto_regra(regra: dict) -> str:
    return str(regra.get("resumo") or regra.get("descricao") or "").strip()


def _fontes(regra: dict) -> str:
    fontes = regra.get("fontes") or []
    if isinstance(fontes, str):
        fontes = [fontes]
    return ", ".join(f"`{f}`" for f in fontes)


def _cenarios_da_regra(regra_id: str, cenarios: list[dict]) -> str:
    ids = [c["id"] for c in cenarios if regra_id in (c.get("regras") or [])]
    if not ids:
        return "—"
    return ", ".join(f"[{i}](#{i.lower().replace('.', '')})" for i in ids)


def _exemplo(exemplo) -> list[str]:
    if isinstance(exemplo, dict):
        linhas: list[str] = []
        dados = exemplo.get("dados")
        if dados:
            linhas.append(f"- **Dados:** {dados}")
        passos = exemplo.get("passos") or []
        if passos:
            linhas.append("- **Passos:**")
            linhas.extend(f"  {n}. {p}" for n, p in enumerate(passos, start=1))
        return linhas
    if isinstance(exemplo, list):
        return ["- **Passos:**"] + [f"  {n}. {p}" for n, p in enumerate(exemplo, start=1)]
    if exemplo:
        return [f"- **Dados:** {exemplo}"]
    return []


def _automacao(automacao: dict | None) -> str:
    if not automacao:
        return "—"
    camada = automacao.get("camada", "—")
    referencia = automacao.get("referencia", "—")
    return f"camada `{camada}`; referência `{referencia}`"


def renderizar(dados: dict) -> str:
    titulo = dados.get("titulo") or dados.get("capitulo") or "Capítulo"
    prefixo = dados.get("prefixo")
    regras = dados.get("regras") or []
    cenarios = dados.get("cenarios") or []

    linhas: list[str] = [f"# {titulo}", ""]
    if prefixo:
        linhas += [f"**Prefixo dos cenários:** `{prefixo}`", ""]
    linhas += [
        "> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.",
        "",
        "## Como funciona",
        "",
        str(dados.get("como_funciona") or "").strip(),
        "",
        "## Regras desta funcionalidade",
        "",
        "| Regra | O que exige | Fontes | Cenários |",
        "|---|---|---|---|",
    ]
    for regra in regras:
        rid = regra.get("id", "—")
        linhas.append(
            f"| `{rid}` | {_texto_regra(regra)} | {_fontes(regra)} | {_cenarios_da_regra(rid, cenarios)} |"
        )
    linhas += [
        "",
        "## Resumo dos cenários",
        "",
        f"Total: {len(cenarios)} cenário(s), todos documentais nesta elaboração.",
        "",
        "| ID | Cenário | Tipo | Regras | Status |",
        "|---|---|---|---|---|",
    ]
    for c in cenarios:
        linhas.append(
            f"| [{c.get('id')}](#{str(c.get('id', '')).lower().replace('.', '')}) | {c.get('titulo', '')} "
            f"| {c.get('tipo', '—')} | {', '.join(c.get('regras') or [])} | `{c.get('status', '—')}` |"
        )
    linhas += ["", "## Cenários", ""]
    for c in cenarios:
        linhas += [f"### {c.get('id')} — {c.get('titulo', '')}", ""]
        linhas.append(f"- **Tipo:** {c.get('tipo', '—')}")
        linhas.append(f"- **Regras:** {', '.join(c.get('regras') or [])}")
        linhas.append(f"- **Status:** {c.get('status', '—')}")
        linhas.append(f"- **Prioridade:** {c.get('prioridade', '—')}")
        linhas.append(f"- **Objetivo:** {c.get('objetivo', '—')}")
        pre = c.get("pre_condicoes") or []
        if isinstance(pre, str):
            pre = [pre]
        linhas.append(f"- **Pré-condições:** {'; '.join(pre) if pre else '—'}")
        linhas.extend(_exemplo(c.get("exemplo")))
        linhas.append(f"- **Esperado:** {c.get('esperado', '—')}")
        linhas.append(f"- **Limitações:** {c.get('limitacoes', '—')}")
        linhas.append(f"- **Automação:** {_automacao(c.get('automacao'))}")
        linhas.append("")
    if dados.get("resumo"):
        linhas += ["## Resumo do capítulo", "", str(dados["resumo"]).strip(), ""]
    return "\n".join(linhas).rstrip() + "\n"


def capitulos() -> list[Path]:
    return sorted(p for p in DADOS.glob("*.yaml") if p.name not in IGNORAR)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="apenas verifica se os .md estão atualizados")
    args = parser.parse_args(argv)

    desatualizados = 0
    for caminho in capitulos():
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        destino = AQUI / f"{caminho.stem}.md"
        esperado = renderizar(dados)
        atual = destino.read_text(encoding="utf-8") if destino.is_file() else None
        if args.check:
            if atual != esperado:
                print(f"desatualizado: {destino.name}")
                desatualizados += 1
            continue
        if atual != esperado:
            destino.write_text(esperado, encoding="utf-8")
            print(f"gerado: {destino.name}")
    if args.check and desatualizados:
        print(f"{desatualizados} capítulo(s) desatualizado(s). Rode python3 gerar.py.", file=sys.stderr)
        return 1
    if args.check:
        print("capítulos em dia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
