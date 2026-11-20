# Política de versionamento e compatibilidade dos contratos (RP-008)

Vale para **as duas famílias** de contrato do estúdio:

1. **Entidades persistidas** — `renderer/app/studio/domain/contracts.py`
   (`SCHEMA_VERSION = 1`) e os schemas gerados em `contracts/v1/*.schema.json`.
2. **Render Plan** — `renderer/app/studio/domain/render_plan.py` (`RenderPlan.schema_version`),
   schema gerado em `contracts/v1/renderplan.schema.json`.

Os schemas **não são escritos à mão**: são gerados por `scripts/export_contracts.py` a
partir dos modelos pydantic e travados por snapshot (`tests/test_contracts_snapshot.py`).

## 1. Duas versões, dois significados

| Campo | Onde | Significa | Não significa |
|---|---|---|---|
| `schema_version` (int) | raiz de cada documento e de cada entidade | a **forma** aceita do documento | conteúdo, revisão editorial |
| `revision` (int ≥ 1) | `RenderPlan` | revisão **editorial** do plano (muda quando o conteúdo muda) | forma do schema |
| `asset_version` / `style_snapshot.version` | `AssetReference` / `StyleSnapshot` | versão do **objeto externo** referenciado (asset, perfil de canal) | schema do plano |

Não usamos semver (`"1.0.0"`) dentro desta família: o `schema_version` é **inteiro
monotônico**, como nas demais entidades. O exemplo `"1.0.0"` do `writing-block.md` §5
não é adotado (design §7.3).

## 2. Regras de leitura e escrita

- **Escrita estrita:** um produtor só emite a versão corrente do `schema_version`.
- **Leitura fechada:** `load_versioned` (e o validador de `_Model`) recusam
  `schema_version` desconhecido — nunca adivinham nem fazem upgrade silencioso.
- **Sem campos extras:** todos os modelos usam `extra="forbid"`. Um documento com campo
  que o leitor não conhece é **rejeitado** (não ignorado).
- **Imutável na leitura:** os modelos do plano são `frozen=True`.

## 3. Classificação de mudança

| Mudança | `schema_version` | Obrigatório |
|---|---|---|
| Docstring / `title` / `description` do schema (cosmético) | **não muda** | regenerar schema + `docs/10-arquitetura.md` e commitar |
| Incluir, remover ou renomear campo | **incrementa** | regenerar e commitar |
| Mudar tipo, limite, enum ou default que altere o conjunto de documentos válidos | **incrementa** | regenerar e commitar |
| Nova validação cruzada (ex.: shot → asset existente) | **incrementa** | regenerar e commitar |
| Adicionar **campo opcional com default** | **incrementa** | ver nota abaixo |

**Nota sobre campo opcional:** com `extra="forbid"`, um leitor antigo recebe um documento
novo (que traz o campo) e o **recusa**. Como o documento trafega/serializa entre
versões do código, adicionar campo — mesmo opcional — é uma mudança de forma e
incrementa `schema_version`. Isso torna a falha explícita ("unsupported schema_version")
em vez de silenciosa.

## 4. O que dispara um bump e o que fazer

1. Alterar o modelo em `domain/*.py` e sua validação.
2. Incrementar `schema_version` (constante `SCHEMA_VERSION` para as entidades;
   `RenderPlan` herda o mesmo default de `_Model`).
3. Regenerar: `python scripts/export_contracts.py` (grava
   `contracts/v1/*.schema.json` e `docs/10-arquitetura.md`).
4. Commitar os arquivos gerados **junto** com o modelo — o snapshot
   `test_committed_contracts_match_code` falha se divergirem.
5. Verificar que **nenhum outro** schema mudou por acidente:
   `git diff --stat contracts/`.

**Migração de documentos persistidos:** um bump exige plano explícito — (a) converter os
documentos gravados para a nova versão, ou (b) manter um leitor da versão anterior que
traduz para o modelo novo. Nunca há migração destrutiva nem remoção do caminho legado na
primeira entrega (design §5.5, §11).

## 5. Família de diretório (`contracts/v1/`)

`v1` é o diretório da **representação** dos schemas. Ele só muda quando a *forma do
arquivo* muda (ex.: trocar pydantic por outra tecnologia, ou passar a publicar vários
documentos num arquivo). Mudanças de campo **não** criam `v2/`: elas incrementam o
`schema_version` inteiro dentro de `v1/`.

## 6. Invariantes do contrato do plano (v1)

Verificados por `tests/test_render_plan.py` e pelo snapshot:

- Schema inválido é rejeitado; `schema_version` desconhecido é rejeitado.
- `scene_id` é único na timeline; `shot_id` é único na cena; `asset_id`/`source_id`
  únicos no plano.
- Nenhum shot referencia asset inexistente; refs de narração/legenda resolvem.
- A duração e a resolução respeitam o formato de saída (`SIZE`/`MAX_SECONDS`).
- Round-trip `model_dump_json` ↔ `model_validate_json` sem perda.
- Ticks são inteiros estritos; segundos float não entram no plano.
