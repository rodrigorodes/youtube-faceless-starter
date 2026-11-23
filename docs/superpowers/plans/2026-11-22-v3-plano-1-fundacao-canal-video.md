# V3 - Plano 1: Fundação do Canal e do Vídeo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o suporte transacional e idempotente a canais e vídeos na plataforma Faceless Studio, adicionando as preferências de canal (`default_mode`, `default_format`), o registro de modo de produção no vídeo (`production_mode`) e o caso de uso atômico de criação de canal (`CreateChannelTransactional`).

**Architecture:** 
- Banco de dados: migração aditiva 0047 adicionando `default_mode` e `default_format` em `studio.channel_profiles`, `production_mode` em `studio.videos`, e tabela de requisições idempotentes `studio.channel_creation_requests`.
- Domínio: enum `ProductionMode` (`piloto`, `diretor`) em `contracts.py`, integrado aos modelos imutáveis `ChannelProfile` e `Video`.
- Aplicação: caso de uso transacional `CreateChannelTransactional` executando criação atômica de Projeto, Perfil de Canal, Orçamento e Configuração de Provedores em uma única transação de banco com chave de idempotência.
- API & Telas: endpoints REST atualizados (`POST /channels/transactional`, campos em `/channels` e `/videos`), e alinhamento do `panel_new_video.py` para herdar padrões do canal e enviar o modo selecionado.

**Tech Stack:** Python 3.11, PostgreSQL (psycopg 3 sem ORM), Pydantic v2, FastAPI, Pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-22-v3-decisoes-e-escopo.md` (e referências `docs/superpowers/specs/2026-11-22-persistencia-prototipo-vs-plataforma.md`).

## Global Constraints

- Nunca executar `git push`, merge de PR ou remoção via GitHub.
- Todas as migrações SQL são estritamente aditivas e compatíveis com código existente (com `DEFAULT` preenchido).
- Respeitar tipagem pura no domínio: sem I/O, sem chamadas a banco ou bibliotecas externas em `domain/`.
- Custo ausente nunca vira US$ 0,00 (`CostKind.UNKNOWN` sem montante).
- Em concorrência e idempotência, falhas devem ser tratadas de forma atômica e devolver conflito explícito (HTTP 409).

## Review Focus

1. **Tentativa de criação de canal com chave de idempotência repetida mas payload divergente**: deve rejeitar com `IdempotencyConflict` (HTTP 409), nunca sobrescrever ou retornar dados inconsistentes. (Task 5, Test: `test_create_channel_transactional_idempotency_conflict`)
2. **Falha parcial no meio da criação do canal (ex.: orçamento inválido)**: a transação inteira deve ser revertida, não deixando projeto órfão sem perfil ou sem orçamento. (Task 5, Test: `test_create_channel_transactional_rolls_back_on_error`)
3. **Canal com perfil arquivado ou sem `default_mode` explícito em registros legados**: deve adotar com segurança os padrões de fallback (`default_mode='piloto'`, `default_format='short'`). (Task 3 e 4, Test: `test_legacy_channel_profile_defaults`)
4. **Criação de vídeo sem especificar `production_mode`**: herda o `default_mode` do canal ativo se omitido, ou assume `piloto` por padrão. (Task 4 e 6, Test: `test_create_video_inherits_channel_default_mode`)
5. **Tentativa de passar valor de modo inválido (ex.: `modo_magico`)**: deve ser recusado imediatamente na fronteira com erro 422/`ValueError`, sem persistir lixo no banco. (Task 3 e 6, Test: `test_invalid_production_mode_rejected`)

---

### Task 1: Limpeza do Baseline de Testes de `panel_new_video`

**Files:**
- Modify: `tests/test_new_video_v3.py:50-115`

**Interfaces:**
- Consumes: `render_new_video_v3` de `renderer/app/studio/api/panel_new_video.py`
- Produces: Suite `tests/test_new_video_v3.py` com 18/18 testes passando no design de tela única.

- [x] **Step 1: Write the updated tests in `tests/test_new_video_v3.py`**

Substituir os 4 testes que ainda buscavam o wizard de 3 etapas (`test_new_video_has_three_steps`, `test_new_video_concept_fields`, `test_new_video_review_and_creation_panels`, `test_new_video_empty_state_without_channels`) pelos testes da tela única:

```python
def test_new_video_single_screen_form_structure():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view())
    assert '<form class="painel-form"' in html
    assert 'id="form-novo-video"' in html
    assert 'id="tema-novo"' in html
    assert 'maxlength="300"' in html
    assert 'name="formato-novo"' in html
    assert 'name="estilo-novo"' in html
    assert 'id="btn-criar-abrir"' in html


def test_new_video_empty_state_without_channels():
    from app.studio.api.panel_new_video import render_new_video_v3

    html, _ = render_new_video_v3(_view(projects=[]))
    assert "Cadastre um canal" in html
    assert re.search(r'<button[^>]*id="btn-criar-abrir"[^>]*disabled', html)
```

- [x] **Step 2: Run test to verify it passes**

Run: `PYTHONPATH=renderer python3 -m pytest tests/test_new_video_v3.py -v`
Expected: 18 passed in ~0.25s

- [x] **Step 3: Commit**

```bash
git add tests/test_new_video_v3.py
git commit -m "test(studio): alinhar testes de novo video com o layout de tela unica"
```

---

### Task 2: Migração 0047 - Preferências de Canal e Modo de Produção

**Files:**
- Create: `renderer/app/studio/adapters/postgres/migrations/0047_channel_preferences_and_production_mode.sql`
- Create: `tests/test_channel_preferences_migration.py`

**Interfaces:**
- Consumes: tabelas existentes `studio.channel_profiles`, `studio.videos`, `studio.projects`
- Produces:
  - `studio.channel_profiles.default_mode` (DEFAULT 'piloto', CHECK IN ('piloto', 'diretor'))
  - `studio.channel_profiles.default_format` (DEFAULT 'short', CHECK IN ('short', 'long'))
  - `studio.videos.production_mode` (DEFAULT 'piloto', CHECK IN ('piloto', 'diretor'))
  - `studio.channel_creation_requests` (idempotency_key PRIMARY KEY, project_id, request_hash, created_at)

- [x] **Step 1: Write the failing test in `tests/test_channel_preferences_migration.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement `0047_channel_preferences_and_production_mode.sql`**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/adapters/postgres/migrations/0047_channel_preferences_and_production_mode.sql tests/test_channel_preferences_migration.py
git commit -m "feat(db): migracao 0047 para preferencias do canal e modo de producao"
```

---

### Task 3: Modelos de Domínio - `ProductionMode`, `ChannelProfile` e `Video`

**Files:**
- Modify: `renderer/app/studio/domain/contracts.py`
- Modify: `renderer/app/studio/domain/channel.py`
- Create: `tests/test_channel_preferences_domain.py`

**Interfaces:**
- Consumes: `VideoFormat` em `domain/contracts.py`
- Produces:
  - `ProductionMode(str, Enum)`: `piloto = "piloto"`, `diretor = "diretor"`
  - `ChannelProfile.default_mode: ProductionMode` (padrão `ProductionMode.piloto`)
  - `ChannelProfile.default_format: VideoFormat` (padrão `VideoFormat.short`)
  - `Video.production_mode: ProductionMode` (padrão `ProductionMode.piloto`)
  - Validações em `domain/channel.py` (`validate_production_mode`, `validate_video_format`)

- [x] **Step 1: Write the failing domain test in `tests/test_channel_preferences_domain.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement domain types and updates**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/domain/contracts.py renderer/app/studio/domain/channel.py tests/test_channel_preferences_domain.py
git commit -m "feat(domain): adicionar ProductionMode e preferencias default no ChannelProfile e Video"
```

---

### Task 4: Extensão dos Repositórios Postgres

**Files:**
- Modify: `renderer/app/studio/adapters/postgres/channel_repo.py`
- Modify: `renderer/app/studio/adapters/postgres/repo.py`
- Create: `tests/test_channel_preferences_repo.py`

**Interfaces:**
- Consumes: Domínio atualizado de `domain/channel.py` e `domain/contracts.py`, e schema da migração 0047.
- Produces:
  - `PostgresChannelProfileRepository.create` e `.update` gravando e lendo `default_mode` e `default_format`
  - `PostgresVideoRepository.create_video` aceitando `production_mode: ProductionMode = ProductionMode.piloto` e persistindo na coluna `production_mode`

- [x] **Step 1: Write failing repository test in `tests/test_channel_preferences_repo.py`**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement repository updates**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Commit**

```bash
git add renderer/app/studio/adapters/postgres/channel_repo.py renderer/app/studio/adapters/postgres/repo.py tests/test_channel_preferences_repo.py
git commit -m "feat(repo): persistir default_mode e default_format no canal e production_mode no video"
```

---

### Task 5: Caso de Uso Transacional de Criação de Canal (`CreateChannelTransactional`)

**Files:**
- Create: `renderer/app/studio/application/channel_creation.py`
- Modify: `renderer/app/studio/application/use_cases.py`
- Modify: `renderer/app/studio/composition/wiring.py`
- Create: `tests/test_channel_creation_use_case.py`

**Interfaces:**
- Consumes: `PostgresVideoRepository`, `PostgresChannelProfileRepository`, `PostgresChannelBudgetRepository`
- Produces: `CreateChannelTransactional` executando:
  - Criação do Projeto em `studio.projects`
  - Criação do Perfil em `studio.channel_profiles`
  - Criação do Orçamento em `studio.channel_budgets`
  - Configuração opcional de provedores em `studio.projects.config`
  - Registro de idempotência em `studio.channel_creation_requests`
  - Tudo dentro de `with conn.transaction(): ...` com rollback atômico em caso de erro.

- [ ] **Step 1: Write failing use case test in `tests/test_channel_creation_use_case.py`**

```python
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

psycopg = pytest.importorskip("psycopg")
from app.studio.adapters.postgres.db import migrate
from app.studio.application.channel_creation import (
    CreateChannelTransactional,
    ChannelCreationPayload,
    IdempotencyConflict,
)
from app.studio.domain.contracts import ProductionMode, VideoFormat

@pytest.fixture()
def uc_env(conn, dsn):
    migrate(conn)
    conn.commit()
    connect = lambda: psycopg.connect(dsn)
    uc = CreateChannelTransactional(connect)
    return {"uc": uc, "conn": conn}

def test_create_channel_transactional_success(uc_env):
    payload = ChannelCreationPayload(
        name="Canal História V3",
        niche="História",
        language="pt-BR",
        strategy="Estratégia clara",
        default_mode=ProductionMode.diretor,
        default_format=VideoFormat.long,
        hard_monthly_usd=20.0,
        soft_monthly_usd=10.0,
        hard_video_usd=2.0,
        soft_video_usd=1.0,
    )
    result = uc_env["uc"].execute(payload, idempotency_key="key-001")
    assert result.project.id
    assert result.project.name == "Canal História V3"
    assert result.profile.default_mode is ProductionMode.diretor
    assert result.profile.default_format is VideoFormat.long
    assert result.budget.hard_monthly_usd == 20.0

    # Replay com a mesma chave e mesmo payload -> idempotente
    replay = uc_env["uc"].execute(payload, idempotency_key="key-001")
    assert replay.project.id == result.project.id

def test_create_channel_transactional_idempotency_conflict(uc_env):
    payload1 = ChannelCreationPayload(name="Canal 1", niche="Nicho 1")
    payload2 = ChannelCreationPayload(name="Canal 2 (divergente)", niche="Nicho 1")
    uc_env["uc"].execute(payload1, idempotency_key="key-conflict")
    with pytest.raises(IdempotencyConflict):
        uc_env["uc"].execute(payload2, idempotency_key="key-conflict")

def test_create_channel_transactional_rolls_back_on_error(uc_env):
    payload = ChannelCreationPayload(
        name="Canal que vai falhar",
        hard_monthly_usd=-50.0,  # Orçamento negativo viola constraint e causa erro
    )
    with pytest.raises(Exception):
        uc_env["uc"].execute(payload)
    
    # Verifica que não criou projeto no banco
    rows = uc_env["conn"].execute("SELECT id FROM studio.projects WHERE name='Canal que vai falhar'").fetchall()
    assert len(rows) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=renderer python3 -m pytest tests/test_channel_creation_use_case.py -v`
Expected: FAIL (cannot import `CreateChannelTransactional`)

- [ ] **Step 3: Implement `CreateChannelTransactional` in `renderer/app/studio/application/channel_creation.py`**

Implementar a classe `CreateChannelTransactional` que recebe `connect: Callable[[], psycopg.Connection]`.
No método `execute(self, payload: ChannelCreationPayload, idempotency_key: str | None = None)`:
- Se `idempotency_key`:
  - Calcula hash SHA-256 do payload canônico.
  - Verifica se já existe em `studio.channel_creation_requests`:
    - Se mesmo hash: lê e retorna o projeto, perfil e budget existentes.
    - Se hash divergente: lança `IdempotencyConflict("Idempotency key already used with different payload")`.
- Abre conexão e `with conn.transaction():`:
  - Insere em `studio.projects`
  - Insere em `studio.channel_profiles` e snapshot em `studio.channel_profile_revisions`
  - Insere em `studio.channel_budgets`
  - Se `provider_config`: atualiza `config` no projeto
  - Se `idempotency_key`: insere em `studio.channel_creation_requests`
- Registra o caso de uso em `use_cases.py` e injeta em `wiring.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=renderer python3 -m pytest tests/test_channel_creation_use_case.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/application/channel_creation.py renderer/app/studio/application/use_cases.py renderer/app/studio/composition/wiring.py tests/test_channel_creation_use_case.py
git commit -m "feat(application): caso de uso transacional e idempotente CreateChannelTransactional"
```

---

### Task 6: Rotas da API para Criação Transacional e Preferências

**Files:**
- Modify: `renderer/app/studio/api/routes.py`
- Create: `tests/test_channel_preferences_api.py`

**Interfaces:**
- Consumes: `CreateChannelTransactional` da Task 5, modelos Pydantic
- Produces:
  - `POST /channels/transactional` (status 201, header `Idempotency-Key` opcional)
  - Campos `default_mode` e `default_format` em `ChannelProfileIn`, `ChannelUpdateIn`, `ChannelProfileOut`
  - Campo `production_mode` em `VideoIn` e `VideoOut`

- [ ] **Step 1: Write failing API test in `tests/test_channel_preferences_api.py`**

```python
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.main import app

def test_api_channel_transactional_creation(client):
    body = {
        "name": "Canal API Transacional",
        "niche": "Negócios",
        "default_mode": "diretor",
        "default_format": "long",
        "hard_monthly_usd": 30.0,
        "soft_monthly_usd": 15.0,
    }
    resp = client.post("/studio/channels/transactional", json=body, headers={"Idempotency-Key": "api-key-1"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["project"]["name"] == "Canal API Transacional"
    assert data["profile"]["default_mode"] == "diretor"
    assert data["profile"]["default_format"] == "long"
    assert data["budget"]["hard_monthly_usd"] == 30.0

def test_api_video_creation_with_production_mode(client):
    # Criar projeto e canal primeiro
    c_resp = client.post("/studio/channels/transactional", json={"name": "Canal Video Mode"})
    p_id = c_resp.json()["project"]["id"]

    v_resp = client.post(f"/studio/projects/{p_id}/videos", json={
        "topic": "Vídeo no modo diretor",
        "format": "short",
        "production_mode": "diretor",
    })
    assert v_resp.status_code == 201
    assert v_resp.json()["production_mode"] == "diretor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=renderer python3 -m pytest tests/test_channel_preferences_api.py -v`
Expected: FAIL (404 Not Found em `/studio/channels/transactional` ou 422 Unprocessable Entity)

- [ ] **Step 3: Implement endpoints and schema updates in `renderer/app/studio/api/routes.py`**

1. Em `ChannelProfileIn`, `ChannelUpdateIn`, `ChannelProfileOut`: adicionar `default_mode: ProductionMode = ProductionMode.piloto`, `default_format: VideoFormat = VideoFormat.short`.
2. Em `VideoIn`, `VideoOut`: adicionar `production_mode: ProductionMode = ProductionMode.piloto`.
3. Adicionar rota `POST /channels/transactional`:
   - Extrai header `Idempotency-Key` (se fornecido).
   - Executa `uc.create_channel_transactional.execute(...)`.
   - Se ocorrer `IdempotencyConflict`: levanta `HTTPException(409, detail="Idempotency conflict")`.
   - Retorna status 201 com JSON `{project: ..., profile: ..., budget: ...}`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=renderer python3 -m pytest tests/test_channel_preferences_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/routes.py tests/test_channel_preferences_api.py
git commit -m "feat(api): endpoint /channels/transactional e suporte a production_mode em videos"
```

---

### Task 7: Conexão no `panel_new_video.py`

**Files:**
- Modify: `renderer/app/studio/api/panel_new_video.py`
- Test: `tests/test_new_video_v3.py`

**Interfaces:**
- Consumes: `view.channel_profile.default_mode`, `view.channel_profile.default_format`
- Produces: HTML do formulário de novo vídeo renderizando o modo (`piloto` vs `diretor`) e formato com base nas preferências do canal ativo, enviando `production_mode` no payload JSON do `fetch`.

- [ ] **Step 1: Write test for channel preset inheritance in `tests/test_new_video_v3.py`**

```python
def test_new_video_inherits_channel_mode_and_format_defaults():
    from app.studio.api.panel_new_video import render_new_video_v3
    from app.studio.domain.contracts import ProductionMode, VideoFormat

    profile = _channel_profile(default_mode=ProductionMode.diretor, default_format=VideoFormat.long)
    html, _ = render_new_video_v3(_view(channel_profile=profile))

    # O formato "long" deve vir checked por padrão
    assert re.search(r'name="formato-novo"[^>]*value="long"[^>]*checked', html)
    # Deve conter seletor de modo com diretor selecionado
    assert re.search(r'name="modo-producao"[^>]*value="diretor"[^>]*checked', html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=renderer python3 -m pytest tests/test_new_video_v3.py -k test_new_video_inherits_channel_mode_and_format_defaults -v`
Expected: FAIL

- [ ] **Step 3: Update `renderer/app/studio/api/panel_new_video.py`**

Adicionar as opções de modo de produção no formulário (`name="modo-producao"`, valores `piloto` e `diretor`), respeitando `channel_profile.default_mode` para a seleção inicial.
No script inline que envia a requisição POST para `/studio/projects/{id}/videos`, incluir `production_mode` no corpo JSON.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=renderer python3 -m pytest tests/test_new_video_v3.py -v`
Expected: PASS (todos os 19 testes passando)

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/panel_new_video.py tests/test_new_video_v3.py
git commit -m "feat(studio): herdar modo e formato do canal ativo na tela de novo video"
```

---

### Task 8: Verificação de Regressão da Suite Completa

**Files:**
- Test: Todas as suítes unitárias e Playwright E2E

- [ ] **Step 1: Run unit test suite**

Run: `PYTHONPATH=renderer python3 -m pytest tests/test_channel_*.py tests/test_new_video_v3.py -v`
Expected: Todos passando com zero erros.

- [ ] **Step 2: Run complete studio unit tests**

Run: `PYTHONPATH=renderer python3 -m pytest tests/test_channels_page.py tests/test_channel_repo.py tests/test_channel_domain.py -v`
Expected: Todos passando.

- [ ] **Step 3: Commit final integration milestone**

```bash
git commit --allow-empty -m "chore: marco do plano 1 - fundacao de canal e video concluida"
```

---
