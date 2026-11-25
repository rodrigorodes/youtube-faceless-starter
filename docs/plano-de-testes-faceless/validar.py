#!/usr/bin/env python3
"""Valida a coerência do plano de testes Faceless.

Confere:
1. cada capítulo .md é exatamente o que `gerar.py` produz a partir de dados/;
2. IDs de cenário são únicos;
3. toda regra citada por um cenário existe em dados/regras.yaml;
4. toda regra do catálogo é citada por ao menos um cenário;
5. dados/funcionalidades.yaml bate com os capítulos (contagens, prefixo e arquivo).

Uso: python3 validar.py
Exit code 0 sem problemas; 1 com problemas.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DADOS = AQUI / "dados"
IGNORAR = {"funcionalidades.yaml", "regras.yaml"}

sys.path.insert(0, str(AQUI))
import gerar  # noqa: E402


def main() -> int:
    problemas: list[str] = []

    capitulos: dict[str, dict] = {}
    for caminho in sorted(p for p in DADOS.glob("*.yaml") if p.name not in IGNORAR):
        capitulos[caminho.stem] = json.loads(caminho.read_text(encoding="utf-8"))

    # 1. .md == saída do gerador
    for nome, dados in capitulos.items():
        destino = AQUI / f"{nome}.md"
        if not destino.is_file():
            problemas.append(f"{nome}: capítulo .md ausente")
            continue
        if destino.read_text(encoding="utf-8") != gerar.renderizar(dados):
            problemas.append(f"{nome}: .md diverge de gerar.py (rode python3 gerar.py)")

    # 2. IDs únicos
    vistos: dict[str, str] = {}
    for nome, dados in capitulos.items():
        for c in dados.get("cenarios", []):
            cid = c.get("id")
            if cid in vistos:
                problemas.append(f"ID duplicado {cid} em {vistos[cid]} e {nome}")
            vistos[cid] = nome

    # 3/4. regras
    catalogo = {r["id"]: r for r in json.loads((DADOS / "regras.yaml").read_text(encoding="utf-8"))}
    citadas: set[str] = set()
    for nome, dados in capitulos.items():
        for c in dados.get("cenarios", []):
            for rid in c.get("regras") or []:
                citadas.add(rid)
                if rid not in catalogo:
                    problemas.append(f"{c.get('id')}: regra inexistente {rid}")
    for rid in catalogo:
        if rid not in citadas:
            problemas.append(f"regra sem cenário: {rid}")

    # 5. funcionalidades x capítulos
    funcionalidades = json.loads((DADOS / "funcionalidades.yaml").read_text(encoding="utf-8"))
    por_arquivo = {f["arquivo"]: f for f in funcionalidades}
    for nome, dados in capitulos.items():
        func = por_arquivo.get(nome)
        if func is None:
            problemas.append(f"{nome}: ausente em dados/funcionalidades.yaml")
            continue
        if func.get("prefixo") != dados.get("prefixo"):
            problemas.append(f"{nome}: prefixo {dados.get('prefixo')} != {func.get('prefixo')}")
        if func.get("cenarios_count") != len(dados.get("cenarios") or []):
            problemas.append(f"{nome}: cenarios_count {func.get('cenarios_count')} != {len(dados.get('cenarios') or [])}")
        if func.get("regras_count") != len(dados.get("regras") or []):
            problemas.append(f"{nome}: regras_count {func.get('regras_count')} != {len(dados.get('regras') or [])}")
    for arquivo in por_arquivo:
        if arquivo not in capitulos:
            problemas.append(f"funcionalidade aponta para capítulo inexistente: {arquivo}")

    # 6. índice: cobre todos os capítulos e regras, e bate os totais
    indice = AQUI / "00-indice-e-cobertura.md"
    if not indice.is_file():
        problemas.append("00-indice-e-cobertura.md ausente")
    else:
        texto = indice.read_text(encoding="utf-8")
        for nome in capitulos:
            if f"({nome}.md)" not in texto:
                problemas.append(f"índice não linka o capítulo {nome}")
        for rid in catalogo:
            if f"`{rid}`" not in texto:
                problemas.append(f"índice não cita a regra {rid}")
        total_cenarios = sum(len(d.get("cenarios") or []) for d in capitulos.values())
        esperado = f"**{len(catalogo)}** | **{total_cenarios}**"
        if esperado not in texto:
            problemas.append(f"índice não exibe o total {esperado}")

    if problemas:
        print("\n".join(problemas))
        print(f"\n{len(problemas)} problema(s).", file=sys.stderr)
        return 1
    total = sum(len(d.get("cenarios") or []) for d in capitulos.values())
    print(f"OK: {len(capitulos)} capítulos, {len(catalogo)} regras, {total} cenários coerentes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
