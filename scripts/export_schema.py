"""Modelo de dados e DDL consolidado do schema ``studio`` (artefatos versionados).

Gera, de forma reproduzível, dois artefatos:

* ``docs/schema/studio.sql`` — o **DDL completo**: as migrações em ordem, *verbatim*.
  É literalmente o que cria o schema, então não há parser nem risco de divergir do
  código (a verdade está no arquivo, não numa interpretação dele).
* ``docs/22-modelo-de-dados.md`` — o **modelo**: diagrama entidade-relacionamento
  (Mermaid), colunas/chaves/índices **lidos do banco real** (introspecção do catálogo,
  não leitura de texto) e o histórico de migrações.

O DDL é gerado **sem banco**; o modelo exige conexão, porque é introspecção — e a regra
da casa é não inventar dado. Nada aqui altera dados: no máximo aplica as migrações
pendentes (idempotente) quando ``--build`` é passado, e só no banco apontado.

Uso::

    python scripts/export_schema.py --dsn postgresql://... --build   # escreve os arquivos
    python scripts/export_schema.py --dsn postgresql://... --check   # confere divergência (CI)
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderer"))

MIGRATIONS_DIR = ROOT / "renderer" / "app" / "studio" / "adapters" / "postgres" / "migrations"
DDL_REL = "docs/schema/studio.sql"
DOC_REL = "docs/22-modelo-de-dados.md"

# --------------------------------------------------------------------------- SQL

_TABLES = """
SELECT c.relname
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'studio' AND c.relkind = 'r'
ORDER BY c.relname
"""

_COLUMNS = """
SELECT c.relname, a.attname,
       format_type(a.atttypid, a.atttypmod),
       a.attnotnull,
       pg_get_expr(d.adbin, d.adrelid)
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
WHERE n.nspname = 'studio' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""

_PRIMARY_KEYS = """
SELECT c.relname, a.attname
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
WHERE n.nspname = 'studio' AND con.contype = 'p'
ORDER BY c.relname, k.ord
"""

_CONSTRAINTS = """
SELECT c.relname, con.conname, con.contype, pg_get_constraintdef(con.oid)
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'studio' AND con.contype IN ('p', 'u', 'c')
ORDER BY c.relname, con.contype, con.conname
"""

_FOREIGN_KEYS = """
SELECT c.relname AS child, cf.relname AS parent, con.conname,
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum) AS child_cols,
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(con.confkey) WITH ORDINALITY AS k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum) AS parent_cols,
       EXISTS (SELECT 1 FROM pg_attribute a
                WHERE a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
                  AND NOT a.attnotnull) AS nullable
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_class cf ON cf.oid = con.confrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'studio' AND con.contype = 'f'
ORDER BY c.relname, con.conname
"""

_INDEXES = """
SELECT tablename, indexname, indexdef
FROM pg_indexes WHERE schemaname = 'studio'
ORDER BY tablename, indexname
"""


# ------------------------------------------------------------------- utilitários

def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(Path(directory).glob("[0-9][0-9][0-9][0-9]_*.sql"))


def _rows(conn, sql: str) -> list[tuple]:
    return conn.execute(sql).fetchall()


def _mermaid_type(sql_type: str) -> str:
    """O Mermaid exige um tipo de uma palavra: ``timestamp with time zone`` → ``timestamp_with_time_zone``."""
    return re.sub(r"[^A-Za-z0-9_\[\]]", "_", sql_type)


def _cols(value) -> str:
    return ", ".join(value) if value else ""


# ------------------------------------------------------------------------ DDL

def render_ddl(directory: Path = MIGRATIONS_DIR) -> str:
    files = migration_files(directory)
    head = [
        "-- ===========================================================================",
        "-- Faceless Studio — DDL consolidado do schema `studio`",
        "--",
        "-- Gerado por scripts/export_schema.py a partir de migrations/*.sql. NÃO EDITE À MÃO.",
        "-- As migrações aparecem em ordem de aplicação e VERBATIM: este é o SQL que cria o",
        "-- schema, na mesma ordem em que db.migrate() o executa (uma transação por arquivo).",
        "--",
        f"-- Migrações: {len(files)} ({files[0].stem if files else '—'} … {files[-1].stem if files else '—'})",
        "-- ===========================================================================",
        "",
    ]
    body: list[str] = []
    for path in files:
        rule = "-" * 75
        body.append(f"-- {rule}")
        body.append(f"-- {path.name}")
        body.append(f"-- {rule}")
        body.append(path.read_text(encoding="utf-8").rstrip("\n"))
        body.append("")
    return "\n".join(head + body)


# ----------------------------------------------------------------- introspecção

def introspect(conn) -> dict:
    model = {
        "tables": [r[0] for r in _rows(conn, _TABLES)],
        "columns": [dict(table=r[0], name=r[1], type=r[2], not_null=r[3], default=r[4])
                    for r in _rows(conn, _COLUMNS)],
        "primary_keys": defaultdict(list),
        "constraints": [dict(table=r[0], name=r[1], kind=r[2], definition=r[3])
                        for r in _rows(conn, _CONSTRAINTS)],
        "foreign_keys": [dict(child=r[0], parent=r[1], name=r[2], child_cols=r[3],
                              parent_cols=r[4], nullable=r[5]) for r in _rows(conn, _FOREIGN_KEYS)],
        "indexes": [dict(table=r[0], name=r[1], definition=r[2]) for r in _rows(conn, _INDEXES)],
    }
    for table, column in _rows(conn, _PRIMARY_KEYS):
        model["primary_keys"][table].append(column)
    return model


# ------------------------------------------------------------------ documento

_KIND = {"p": "PK", "u": "único", "c": "check"}


def render_doc(model: dict, directory: Path = MIGRATIONS_DIR) -> str:
    tables = model["tables"]
    cols_by: dict[str, list] = defaultdict(list)
    for c in model["columns"]:
        cols_by[c["table"]].append(c)
    cons_by: dict[str, list] = defaultdict(list)
    for c in model["constraints"]:
        cons_by[c["table"]].append(c)
    idx_by: dict[str, list] = defaultdict(list)
    for i in model["indexes"]:
        idx_by[i["table"]].append(i)
    fks_by: dict[str, list] = defaultdict(list)
    for f in model["foreign_keys"]:
        fks_by[f["child"]].append(f)
    pks = model["primary_keys"]

    files = migration_files(directory)
    # tabelas citadas por migração (busca literal por `studio.<tabela>`) e o inverso
    migrations_by_table: dict[str, list[str]] = defaultdict(list)
    tables_by_migration: list[tuple[str, list[str]]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        cited = sorted(t for t in tables if f"studio.{t}" in text)
        tables_by_migration.append((path.stem, cited))
        for t in cited:
            migrations_by_table[t].append(path.stem)

    out: list[str] = [
        "# Modelo de dados (gerado)",
        "",
        "> Gerado por `scripts/export_schema.py`. Não edite à mão.",
        f"> Fonte: `renderer/app/studio/adapters/postgres/migrations/` — {len(files)} migrações",
        f"> (`{files[0].stem if files else '—'}` … `{files[-1].stem if files else '—'}`).",
        "> DDL consolidado e executável: `docs/schema/studio.sql`.",
        "> As colunas, chaves e índices abaixo vêm da **introspecção do banco real** após aplicar",
        "> as migrações — não de leitura de texto —, para não documentar algo que o banco não tem.",
        "",
        "## Visão geral",
        "",
        f"- Tabelas: **{len(tables)}**",
        f"- Chaves estrangeiras: **{len(model['foreign_keys'])}**",
        f"- Índices: **{len(model['indexes'])}**",
        "",
        "## Diagrama de relacionamentos",
        "",
        "Cada seta é uma chave estrangeira. `||` = exatamente um; `o{` = zero ou mais",
        "(coluna anulável); `|{` = um ou mais (coluna obrigatória).",
        "",
        "```mermaid",
        "erDiagram",
    ]

    for table in tables:
        attrs: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        pk = set(pks.get(table, []))
        fk_cols = {col for f in fks_by[table] for col in (f["child_cols"] or [])}
        for c in cols_by[table]:
            marks = []
            if c["name"] in pk:
                marks.append("PK")
            if c["name"] in fk_cols:
                marks.append("FK")
            if not marks:
                continue
            seen.add(c["name"])
            attrs.append((_mermaid_type(c["type"]), c["name"], ",".join(marks)))
        if not attrs:
            continue
        out.append(f"    {table} {{")
        for sql_type, name, mark in attrs:
            out.append(f"        {sql_type} {name} {mark}".rstrip())
        out.append("    }")

    for f in model["foreign_keys"]:
        child_card = "o{" if f["nullable"] else "|{"
        out.append(f'    {f["parent"]} ||--{child_card} {f["child"]} : "{f["name"]}"')
    out += ["```", ""]

    out += [
        "## Relações (chaves estrangeiras)",
        "",
        "| Filho (colunas) | → | Pai (colunas) | Regra | FK |",
        "| --- | --- | --- | --- | --- |",
    ]
    for f in model["foreign_keys"]:
        rule = "opcional" if f["nullable"] else "obrigatória"
        out.append(f"| `{f['child']}` ({_cols(f['child_cols'])}) | → | "
                   f"`{f['parent']}` ({_cols(f['parent_cols'])}) | {rule} | `{f['name']}` |")
    out.append("")

    out += ["## Tabelas e colunas", ""]
    for table in tables:
        out.append(f"### `studio.{table}`")
        out.append("")
        out.append("| Coluna | Tipo | Nulo | Padrão |")
        out.append("| --- | --- | --- | --- |")
        for c in cols_by[table]:
            nullable = "não" if c["not_null"] else "sim"
            default = f"`{c['default']}`" if c["default"] else "—"
            out.append(f"| `{c['name']}` | `{c['type']}` | {nullable} | {default} |")
        out.append("")
        pk = pks.get(table, [])
        if pk:
            out.append(f"**Chave primária:** {', '.join(f'`{c}`' for c in pk)}")
            out.append("")
        if cons_by[table]:
            out.append("**Restrições:**")
            out.append("")
            for c in cons_by[table]:
                out.append(f"- `{c['name']}` ({_KIND.get(c['kind'], c['kind'])}): `{c['definition']}`")
            out.append("")
        if fks_by[table]:
            out.append("**Chaves estrangeiras:**")
            out.append("")
            for f in fks_by[table]:
                out.append(f"- `{f['name']}`: ({_cols(f['child_cols'])}) → "
                           f"`{f['parent']}` ({_cols(f['parent_cols'])})")
            out.append("")
        if idx_by[table]:
            out.append("**Índices:**")
            out.append("")
            for i in idx_by[table]:
                out.append(f"- `{i['name']}`: `{i['definition']}`")
            out.append("")
        if migrations_by_table.get(table):
            out.append(f"**Migrações que citam esta tabela:** "
                       f"{', '.join(migrations_by_table[table])}")
            out.append("")

    out += ["## Histórico de migrações", "",
            "Tabelas citadas por cada migração (busca literal por `studio.<tabela>`).", "",
            "| Migração | Tabelas citadas |", "| --- | --- |"]
    for version, cited in tables_by_migration:
        out.append(f"| `{version}` | {', '.join('`' + t + '`' for t in cited) if cited else '—'} |")
    out.append("")

    out += [
        "## Como regenerar",
        "",
        "```bash",
        "python scripts/export_schema.py --dsn \"$STUDIO_TEST_DSN\" --build   # escreve os dois arquivos",
        "python scripts/export_schema.py --dsn \"$STUDIO_TEST_DSN\" --check   # confere divergência (CI)",
        "```",
        "",
        "",
    ]
    return "\n".join(out)


def render_all(conn=None, directory: Path = MIGRATIONS_DIR) -> dict[str, str]:
    files = {"docs/schema/studio.sql": render_ddl(directory)}
    if conn is not None:
        files["docs/22-modelo-de-dados.md"] = render_doc(introspect(conn), directory)
    return files


# ------------------------------------------------------------------------- main

def main(*, check: bool = False, dsn: str | None = None, build: bool = False,
         root: Path = ROOT) -> int:
    conn = None
    if dsn:
        import psycopg
        conn = psycopg.connect(dsn)
        if build:
            from app.studio.adapters.postgres.db import migrate
            applied = migrate(conn)
            conn.commit()
            print(f"migrações aplicadas agora: {applied or 'nenhuma (já estava em dia)'}")
    else:
        print("sem --dsn: só o DDL é gerado/verificado; o modelo exige conexão")

    files = render_all(conn, MIGRATIONS_DIR)
    if conn is not None:
        conn.close()

    drift: list[str] = []
    for rel, content in files.items():
        target = root / rel
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if check:
            if current != content:
                drift.append(rel)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            print(f"escrito: {rel}")

    if check:
        if drift:
            print("divergente (rode scripts/export_schema.py --build): " + ", ".join(drift))
            return 1
        print("tudo em dia: " + ", ".join(files))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="Gera modelo de dados e DDL do schema studio.")
    parser.add_argument("--dsn", default=None, help="DSN do Postgres (necessário para o modelo)")
    parser.add_argument("--build", action="store_true", help="aplica as migrações pendentes antes")
    parser.add_argument("--check", action="store_true", help="confere divergência e não escreve")
    args = parser.parse_args()
    raise SystemExit(main(check=args.check, dsn=args.dsn, build=args.build))
