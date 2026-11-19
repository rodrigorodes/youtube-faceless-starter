# P00 + P01: Contratos, estados, persistência e infraestrutura — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao starter entidades persistidas com contratos JSON versionados, máquina de estados com transição atômica, política de custo/QA, layout de storage e ferramentas de operação (`doctor`, backup), validado no Lenovo.

**Architecture:** Novo pacote `renderer/app/studio/` (contratos, estados, política, storage, banco, repositório) ao lado do código atual, **sem alterar o comportamento dos endpoints `/videos` existentes**. O serviço `renderer` é o único escritor do schema `studio` no Postgres já existente; o n8n continua só orquestrando por HTTP.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, `psycopg[binary]` 3, PostgreSQL 16, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-19-faceless-studio-design.md`

## Global Constraints

- Upload no YouTube sempre `private` por padrão; `selfDeclaredMadeForKids=false`; `containsSyntheticMedia=true`; idioma pt-BR.
- Só modelos `:free` por padrão; `MAX_COST_USD_PER_VIDEO` padrão **0**.
- Não usar o projeto GCP `cerc2-book-stg-01`.
- Nunca imprimir segredos (valores de `.env`, tokens, senhas) em logs, saída de `doctor` ou testes.
- Documentar para macOS **e** Windows; scripts novos só com biblioteca padrão do Python, sem shell específico de SO.
- Preservar comportamento existente: os 48 testes atuais continuam passando sem alteração de assertion; `/videos`, `/videos/{id}`, `/videos/{id}/file` e o workflow V2 seguem funcionando.
- IDs são `uuid4().hex` (32 caracteres hexadecimais minúsculos).
- `git push` é feito pelo humano; as tarefas só fazem commit local.

## Review Focus

1. **ID malicioso em caminho de arquivo** (`../x`, vazio, maiúsculas, 33 chars): storage recusa, nunca monta caminho.
2. **Duas transições concorrentes do mesmo vídeo:** exatamente uma vence; a outra recebe `False`/HTTP 409.
3. **Migração rodada duas vezes, ou que falha no meio:** segunda execução não faz nada; falha reverte tudo (transacional) e não marca como aplicada.
4. **JSON persistido com `schema_version` desconhecido:** é rejeitado com erro claro, não interpretado.
5. **`.env` ausente ou com segredo em branco no `doctor`:** reporta falha por nome da variável, sem imprimir valor.
6. **Custo negativo, `NaN` ou ausente na política:** recusado, nunca tratado como zero.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `renderer/app/studio/__init__.py` | Marca o pacote (vazio) |
| `renderer/app/studio/contracts.py` | Enums e modelos Pydantic das entidades; `SCHEMA_VERSION = 1` |
| `renderer/app/studio/states.py` | Transições válidas e `to_mermaid()` |
| `renderer/app/studio/policy.py` | `check_cost`, `evaluate_qa` |
| `renderer/app/studio/storage.py` | Layout de pastas e `asset_cache_key`, com validação de ID |
| `renderer/app/studio/db.py` | Conexão, `migrate()` |
| `renderer/app/studio/migrations/0001_init.sql` | Schema `studio` completo |
| `renderer/app/studio/repo.py` | `create_project`, `create_video`, `get_video`, `transition_video` |
| `renderer/app/studio/api.py` | `APIRouter` `/studio/*` |
| `contracts/v1/*.schema.json` | Schemas exportados (gerados, versionados) |
| `scripts/export_contracts.py` | Gera schemas e `docs/10-arquitetura.md` |
| `scripts/doctor.py`, `scripts/backup.py` | Operação |
| `docker-compose.test.yml` | Postgres descartável para testes de banco |
| `tests/test_contracts.py`, `test_states.py`, `test_policy.py`, `test_storage.py`, `test_db.py`, `test_repo.py`, `test_studio_api.py`, `test_doctor.py`, `test_backup.py` | Testes |

---

## FASE P00 — Contratos

### Task 1: Entidades e contratos

**Files:**
- Create: `renderer/app/studio/__init__.py`, `renderer/app/studio/contracts.py`
- Test: `tests/test_contracts.py`

**Interfaces:**
- Produces:
  - `SCHEMA_VERSION: int = 1`
  - `class VideoStatus(str, Enum)`: `IDEA, SCRIPTED, FACT_CHECKED, STORYBOARDED, ASSETS_READY, RENDERED, AWAITING_APPROVAL, APPROVED, PUBLISHED, REJECTED, FAILED`
  - `class VideoFormat(str, Enum)`: `short, long`
  - `class AssetKind(str, Enum)`: `image, voice, music, clip, thumbnail`
  - `class JobStatus(str, Enum)`: `QUEUED, RUNNING, SUCCEEDED, FAILED`
  - Modelos Pydantic v2 com `schema_version: int = SCHEMA_VERSION` e `model_config = ConfigDict(extra="forbid")`: `Project`, `Video`, `Script`, `Scene`, `Asset`, `RenderJob`, `Publication`, `UsageEntry`, `QaReport`
  - `Asset` exige `license: str` (não vazio) e `cost_usd: float >= 0`
  - `UsageEntry`: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens` (todos `int | None`, `>= 0`), `cost_usd: float >= 0`
  - `Video.privacy` padrão `"private"`, valores aceitos `private|unlisted|public`
  - `def load_versioned(model: type[T], data: dict) -> T` — levanta `ValueError` se `data["schema_version"] != SCHEMA_VERSION`

- [ ] **Step 1: Write the failing tests** em `tests/test_contracts.py`

```python
def test_video_defaults_are_private_and_new():
    v = Video(id="a"*32, project_id="b"*32, topic="ADE 2026", format=VideoFormat.short)
    assert v.privacy == "private" and v.status == VideoStatus.IDEA and v.schema_version == 1

def test_asset_requires_license():
    with pytest.raises(ValidationError):
        Asset(id="a"*32, kind=AssetKind.image, cache_key="c"*64, path="x", provider="p", model="m", license="", cost_usd=0)

def test_usage_rejects_negative_and_nan_cost():
    for bad in (-0.01, float("nan")):
        with pytest.raises(ValidationError):
            UsageEntry(step="script", provider="p", model="m", cost_usd=bad)

def test_usage_keeps_cache_tokens_separate_and_nullable():
    u = UsageEntry(step="script", provider="p", model="m", input_tokens=10, output_tokens=5, cost_usd=0)
    assert u.cache_read_tokens is None and u.cache_write_tokens is None

def test_load_versioned_rejects_unknown_version():
    with pytest.raises(ValueError, match="schema_version"):
        load_versioned(Project, {"schema_version": 2, "id": "a"*32, "name": "x"})

def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        Project(id="a"*32, name="x", surprise=1)
```

- [ ] **Step 2: Run** `pytest tests/test_contracts.py -v` — Expected: FAIL (`ModuleNotFoundError: app.studio`)
- [ ] **Step 3: Implement** `contracts.py` conforme Interfaces. `nan` é barrado com `Field(ge=0, allow_inf_nan=False)`.
- [ ] **Step 4: Run** `pytest tests/test_contracts.py -v` — Expected: 6 passed
- [ ] **Step 5: Commit** — `git add renderer/app/studio tests/test_contracts.py && git commit -m "feat(studio): contratos das entidades (P00)"`

### Task 2: Máquina de estados

**Files:**
- Create: `renderer/app/studio/states.py`
- Test: `tests/test_states.py`

**Interfaces:**
- Consumes: `VideoStatus` (Task 1)
- Produces:
  - `VIDEO_TRANSITIONS: dict[VideoStatus, frozenset[VideoStatus]]`
  - `def can_transition(old: VideoStatus, new: VideoStatus) -> bool`
  - `class InvalidTransition(ValueError)`; `def assert_transition(old, new) -> None`
  - `def to_mermaid() -> str` (diagrama `stateDiagram-v2`, ordem determinística)

Regras: avanço linear `IDEA→SCRIPTED→FACT_CHECKED→STORYBOARDED→ASSETS_READY→RENDERED→AWAITING_APPROVAL→APPROVED→PUBLISHED`; `AWAITING_APPROVAL→REJECTED`; qualquer estado não terminal `→FAILED`; `FAILED→` o estado de onde falhou é tratado na P06 (aqui: `FAILED→` qualquer estado não terminal é **permitido**, a validação de "onde" entra na P06); `PUBLISHED` e `REJECTED` são terminais; **não há** caminho de `PUBLISHED` a nada, nem pular `AWAITING_APPROVAL` para `APPROVED`.

- [ ] **Step 1: Write the failing tests**

```python
def test_cannot_publish_without_approval():
    assert not can_transition(VideoStatus.RENDERED, VideoStatus.APPROVED)
    assert not can_transition(VideoStatus.AWAITING_APPROVAL, VideoStatus.PUBLISHED)

def test_only_awaiting_approval_can_be_approved_or_rejected():
    for s in VideoStatus:
        assert can_transition(s, VideoStatus.APPROVED) == (s == VideoStatus.AWAITING_APPROVAL)
        assert can_transition(s, VideoStatus.REJECTED) == (s == VideoStatus.AWAITING_APPROVAL)

def test_terminal_states_have_no_exit():
    assert VIDEO_TRANSITIONS[VideoStatus.PUBLISHED] == frozenset()
    assert VIDEO_TRANSITIONS[VideoStatus.REJECTED] == frozenset()

def test_assert_transition_raises():
    with pytest.raises(InvalidTransition):
        assert_transition(VideoStatus.IDEA, VideoStatus.PUBLISHED)

def test_mermaid_mentions_every_status():
    text = to_mermaid()
    assert all(s.value in text for s in VideoStatus)
```

- [ ] **Step 2: Run** `pytest tests/test_states.py -v` — Expected: FAIL
- [ ] **Step 3: Implement** `states.py`
- [ ] **Step 4: Run** — Expected: 5 passed
- [ ] **Step 5: Commit** — `git commit -m "feat(studio): máquina de estados do vídeo (P00)"`

### Task 3: Política de custo e QA

**Files:**
- Create: `renderer/app/studio/policy.py`
- Test: `tests/test_policy.py`

**Interfaces:**
- Consumes: `QaReport`, `VideoFormat` (Task 1)
- Produces:
  - `class CostRefused(ValueError)`
  - `def check_cost(estimated_usd: float | None, spent_usd: float, cap_usd: float) -> None` — recusa se `estimated_usd` for `None`, negativo ou `NaN`; recusa se `spent_usd + estimated_usd > cap_usd`; com `cap_usd == 0`, só aceita estimativa exatamente `0.0`
  - `def evaluate_qa(m: QaMetrics, fmt: VideoFormat) -> QaReport` — `QaMetrics` é dataclass com `duration_s`, `width`, `height`, `loudness_lufs: float | None`, `max_silence_s`, `max_black_s`, `has_audio: bool`, `disclosure_in_video: bool`, `disclosure_in_description: bool`, `unsourced_claims: int`, `paid_assets_without_cap: int`
  - `QaReport.passed: bool` e `QaReport.failures: list[str]` (códigos estáveis: `duration`, `resolution`, `loudness`, `silence`, `black`, `no_audio`, `disclosure`, `unsourced_claim`, `paid_asset`)
  - Limites: Short ≤ 175 s, 1080×1920; long ≤ 1800 s, 1920×1080; loudness −16 ± 1,5; silêncio > 4 s e quadro preto > 2 s reprovam

- [ ] **Step 1: Write the failing tests** — `check_cost(0.0, 0.0, 0.0)` passa; `check_cost(0.01, 0.0, 0.0)` levanta; `check_cost(None, 0, 5)`, `-1` e `nan` levantam; `check_cost(1.0, 4.5, 5.0)` levanta; `evaluate_qa` com vídeo ideal passa; um caso por código de falha (parametrizado) retorna exatamente aquele código; vídeo mudo (`has_audio=False`) falha `no_audio`.
- [ ] **Step 2: Run** `pytest tests/test_policy.py -v` — Expected: FAIL
- [ ] **Step 3: Implement** `policy.py`
- [ ] **Step 4: Run** — Expected: todos passam
- [ ] **Step 5: Commit** — `git commit -m "feat(studio): política de custo e critérios de QA (P00)"`

### Task 4: Schemas exportados e diagramas

**Files:**
- Create: `scripts/export_contracts.py`, `contracts/v1/*.schema.json` (gerados), `docs/10-arquitetura.md` (gerado)
- Test: `tests/test_contracts_snapshot.py`

**Interfaces:**
- Consumes: modelos (Task 1), `to_mermaid()` (Task 2)
- Produces: `def render_all() -> dict[str, str]` em `scripts/export_contracts.py` (caminho relativo → conteúdo); `main()` grava; `main(check=True)` retorna `1` se algum arquivo divergir

- [ ] **Step 1: Write the failing test**

```python
def test_committed_contracts_match_code():
    for rel, content in export_contracts.render_all().items():
        assert (ROOT / rel).read_text(encoding="utf-8") == content, f"{rel} desatualizado: rode scripts/export_contracts.py"
```

- [ ] **Step 2: Run** — Expected: FAIL (arquivos inexistentes)
- [ ] **Step 3: Implement** `export_contracts.py` (JSON com `sort_keys=True, indent=2, ensure_ascii=False`; `docs/10-arquitetura.md` com o diagrama de estados e a tabela de entidades). Rodar `python scripts/export_contracts.py` para gerar os arquivos.
- [ ] **Step 4: Run** `pytest tests/test_contracts_snapshot.py -v` — Expected: PASS; depois mudar um campo de propósito e confirmar que FALHA, e reverter.
- [ ] **Step 5: Commit** — `git add contracts docs/10-arquitetura.md scripts/export_contracts.py tests/test_contracts_snapshot.py && git commit -m "feat(studio): schemas JSON versionados e diagrama gerado (P00)"`

**Marco P00:** `pytest -q` completo verde (48 antigos + novos), schemas versionados no repositório.

---

## FASE P01 — Persistência e infraestrutura

### Task 5: Layout de storage e chave de cache

**Files:**
- Create: `renderer/app/studio/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Produces:
  - `class InvalidId(ValueError)`
  - `def video_dir(root: Path, project_id: str, video_id: str) -> Path` → `root/projects/<p>/videos/<v>`
  - `def cache_path(root: Path, cache_key: str) -> Path` → `root/cache/<2 primeiros>/<cache_key>`
  - `def asset_cache_key(kind: str, provider: str, model: str, prompt: str, params: dict) -> str` — sha256 hex de JSON canônico (`sort_keys`), estável entre execuções
  - IDs válidos: `^[0-9a-f]{32}$`; `cache_key`: `^[0-9a-f]{64}$`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("bad", ["", "../x", "A"*32, "a"*33, "a"*31+"/", "a"*32+"\n"])
def test_video_dir_rejects_bad_ids(tmp_path, bad):
    with pytest.raises(InvalidId):
        video_dir(tmp_path, bad, "b"*32)
    with pytest.raises(InvalidId):
        video_dir(tmp_path, "a"*32, bad)

def test_video_dir_stays_inside_root(tmp_path):
    assert tmp_path in video_dir(tmp_path, "a"*32, "b"*32).parents

def test_cache_key_is_stable_and_sensitive():
    a = asset_cache_key("image", "openrouter", "m:free", "palco", {"aspect": "9:16"})
    assert a == asset_cache_key("image", "openrouter", "m:free", "palco", {"aspect": "9:16"})
    assert a != asset_cache_key("image", "openrouter", "m:free", "palco ", {"aspect": "9:16"})
    assert a != asset_cache_key("image", "openrouter", "m:free", "palco", {"aspect": "16:9"})

def test_cache_path_rejects_bad_key(tmp_path):
    with pytest.raises(InvalidId):
        cache_path(tmp_path, "../../etc/passwd")
```

(`"a"*32+"\n"` pega o armadilha do `$` do regex: usar `re.fullmatch`.)

- [ ] **Step 2: Run** — Expected: FAIL
- [ ] **Step 3: Implement** `storage.py` com `re.fullmatch`
- [ ] **Step 4: Run** — Expected: passam
- [ ] **Step 5: Commit** — `git commit -m "feat(studio): layout de storage e chave de cache (P01)"`

### Task 6: Banco, migrações e Postgres de teste

**Files:**
- Create: `renderer/app/studio/db.py`, `renderer/app/studio/migrations/0001_init.sql`, `docker-compose.test.yml`
- Modify: `renderer/requirements.txt` (adicionar `psycopg[binary]==3.2.9`), `requirements-dev.txt` se preciso
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `def connect(dsn: str | None = None) -> psycopg.Connection` — usa `STUDIO_DATABASE_URL` se `dsn` for `None`
  - `def migrate(conn) -> list[str]` — aplica em ordem os `NNNN_*.sql` ainda não registrados em `studio.schema_migrations(version text primary key, applied_at timestamptz)`, **cada um em uma transação**; devolve as versões aplicadas nesta chamada; usa `pg_advisory_xact_lock` para dois processos não migrarem juntos
- `0001_init.sql` cria o schema `studio` e as tabelas com PK `text` + `CHECK (id ~ '^[0-9a-f]{32}$')`: `projects`, `videos`, `scripts`, `scenes`, `assets`, `render_jobs`, `publications`, `source_snapshots`, `step_runs`, `usage_ledger`, `video_metrics`. Restrições obrigatórias: `assets.cache_key` UNIQUE; `scenes` UNIQUE `(video_id, idx)`; `publications.video_id` UNIQUE; `step_runs` UNIQUE `(video_id, step, attempt)`; `video_metrics` PK `(video_id, date)`; `videos.status` com `CHECK` na lista de `VideoStatus`; `videos.privacy` padrão `'private'`; `usage_ledger` com `cost_usd numeric(12,6) CHECK (>= 0)`; FKs com `ON DELETE RESTRICT`
- `docker-compose.test.yml`: serviço `postgres-test` (`postgres:16-alpine`, sem volume, porta `127.0.0.1:55432`)
- Testes de banco usam a fixture `conn` que lê `STUDIO_TEST_DSN` e **pula** (`pytest.skip`) se ausente, para não quebrar quem roda sem banco; cada teste cria um schema limpo (`DROP SCHEMA studio CASCADE` antes)

- [ ] **Step 1: Write the failing tests**

```python
def test_migrate_applies_once(conn):
    assert migrate(conn) == ["0001_init"]
    assert migrate(conn) == []

def test_failed_migration_rolls_back_and_is_not_recorded(conn, tmp_path, monkeypatch):
    # pasta de migrações com um SQL que cria uma tabela e depois falha
    ...
    with pytest.raises(psycopg.Error):
        migrate(conn)
    assert not table_exists(conn, "studio", "half_done")
    assert "0002_broken" not in applied_versions(conn)

def test_publication_unique_per_video(conn):
    migrate(conn)
    seed_video(conn, "v"*32)
    insert_publication(conn, "v"*32)
    with pytest.raises(psycopg.errors.UniqueViolation):
        insert_publication(conn, "v"*32)

def test_rejects_bad_id_and_negative_cost(conn):
    migrate(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO studio.projects(id,name) VALUES ('x','y')")
    ...
```

- [ ] **Step 2: Run** — `docker compose -f docker-compose.test.yml up -d postgres-test` e `STUDIO_TEST_DSN=postgresql://postgres:test@127.0.0.1:55432/postgres pytest tests/test_db.py -v` — Expected: FAIL (módulo inexistente)
- [ ] **Step 3: Implement** `db.py` e `0001_init.sql`. Os nomes e tipos de coluna seguem os campos dos modelos da Task 1 (um campo por coluna; JSON em `jsonb`).
- [ ] **Step 4: Run** o mesmo comando — Expected: passam; sem `STUDIO_TEST_DSN`, os testes de banco aparecem como `skipped`, não como falha
- [ ] **Step 5: Commit** — `git commit -m "feat(studio): migrações e schema studio (P01)"`

### Task 7: Repositório com transição atômica

**Files:**
- Create: `renderer/app/studio/repo.py`
- Test: `tests/test_repo.py`

**Interfaces:**
- Consumes: `connect`, `migrate` (Task 6); `Video`, `VideoStatus`, `assert_transition` (Tasks 1–2)
- Produces:
  - `def create_project(conn, name: str, niche: str = "", language: str = "pt-BR") -> Project`
  - `def create_video(conn, project_id: str, topic: str, fmt: VideoFormat) -> Video` (estado `IDEA`, privacidade `private`)
  - `def get_video(conn, video_id: str) -> Video | None`
  - `def transition_video(conn, video_id: str, expected: VideoStatus, new: VideoStatus) -> bool` — valida com `assert_transition` **antes** de tocar no banco; executa `UPDATE … SET status=%s, updated_at=now() WHERE id=%s AND status=%s`; devolve `cursor.rowcount == 1`

- [ ] **Step 1: Write the failing tests**

```python
def test_transition_wins_once_under_concurrency(dsn):
    # dois threads, cada um com sua conexão, tentam IDEA->SCRIPTED no mesmo vídeo
    results = run_in_threads(2, lambda c: transition_video(c, vid, IDEA, SCRIPTED))
    assert sorted(results) == [False, True]

def test_transition_false_when_state_moved(conn):
    ...  # vídeo já em SCRIPTED; esperado IDEA -> False, estado intacto

def test_invalid_transition_raises_before_touching_db(conn):
    with pytest.raises(InvalidTransition):
        transition_video(conn, vid, VideoStatus.RENDERED, VideoStatus.APPROVED)

def test_new_video_is_private_idea(conn):
    v = create_video(conn, p.id, "ADE 2026", VideoFormat.short)
    assert v.status == VideoStatus.IDEA and v.privacy == "private"
```

- [ ] **Step 2: Run** — Expected: FAIL
- [ ] **Step 3: Implement** `repo.py`; cada função faz `commit` ao terminar; IDs por `uuid.uuid4().hex`
- [ ] **Step 4: Run** — Expected: passam (repetir o teste de concorrência 20× sem flakiness: `pytest tests/test_repo.py -k concurrency --count=20` ou laço de shell)
- [ ] **Step 5: Commit** — `git commit -m "feat(studio): repositório com transição atômica (P01)"`

### Task 8: API `/studio` e saúde com banco

**Files:**
- Create: `renderer/app/studio/api.py`
- Modify: `renderer/app/main.py` (incluir o router e estender `/health` **sem remover campos existentes**), `docker-compose.yml` (variável `STUDIO_DATABASE_URL` montada a partir de `POSTGRES_*`; `depends_on` do postgres saudável; `STUDIO_STORAGE_ROOT: /data`)
- Test: `tests/test_studio_api.py`

**Interfaces:**
- Consumes: `repo` (Task 7), `migrate` (Task 6)
- Produces (HTTP):
  - `POST /studio/projects` `{name, niche?, language?}` → 201 `Project`
  - `POST /studio/videos` `{project_id, topic, format}` → 201 `Video`; 404 se o projeto não existe
  - `GET /studio/videos/{id}` → 200 `Video` | 404 | 422 se o ID for inválido
  - `POST /studio/videos/{id}/transition` `{expected, new}` → 200 `{ok: true}` | 409 se o estado mudou | 422 se a transição for proibida
  - `GET /health` mantém os campos atuais e acrescenta `"studio_db": "ok"|"unavailable"`; **com banco fora, `/health` continua 200** (o modo antigo `/videos` não depende do banco)
- `migrate()` roda no *startup* do app; se o banco estiver indisponível, o app sobe em modo degradado e `/studio/*` responde 503

- [ ] **Step 1: Write the failing tests** (FastAPI `TestClient`, banco de teste)

```python
def test_transition_conflict_is_409(client):
    ...  # 1ª chamada 200, 2ª idêntica 409

def test_forbidden_transition_is_422(client):
    r = client.post(f"/studio/videos/{vid}/transition", json={"expected": "RENDERED", "new": "APPROVED"})
    assert r.status_code == 422

def test_bad_id_is_422(client):
    assert client.get("/studio/videos/..%2Fetc").status_code in (404, 422)
    assert client.get("/studio/videos/" + "A"*32).status_code == 422

def test_health_keeps_legacy_fields_and_survives_db_down(client_without_db):
    r = client_without_db.get("/health")
    assert r.status_code == 200 and r.json()["studio_db"] == "unavailable"
    assert client_without_db.post("/studio/projects", json={"name": "x"}).status_code == 503
```

- [ ] **Step 2: Run** — Expected: FAIL
- [ ] **Step 3: Implement** `api.py` e a integração mínima em `main.py`
- [ ] **Step 4: Run** a suíte inteira com e sem `STUDIO_TEST_DSN` — Expected: sem DSN, 48 antigos + testes sem banco passam e os de banco ficam `skipped`; com DSN, tudo passa
- [ ] **Step 5: Verificar o comportamento antigo na stack real:** `docker compose up -d --build renderer`, rodar `scripts/test-create.sh` (ou `.ps1`) e `curl localhost:8000/health` — Expected: o vídeo `slides` continua sendo gerado e `/health` traz `studio_db: ok`
- [ ] **Step 6: Commit** — `git commit -m "feat(studio): API /studio e health com banco (P01)"`

### Task 9: `doctor`

**Files:**
- Create: `scripts/doctor.py`
- Test: `tests/test_doctor.py`

**Interfaces:**
- Produces (funções puras, só `stdlib`):
  - `@dataclass Check: name: str, ok: bool, detail: str`
  - `def check_env(env_text: str, required: list[str]) -> list[Check]` — falha por variável ausente **ou em branco**; `detail` cita só o nome, nunca o valor
  - `def check_port(host: str, port: int, expect_open: bool) -> Check`
  - `def check_http(url: str, timeout: float = 3.0) -> Check`
  - `def run_all(root: Path) -> list[Check]` e `main() -> int` (código de saída `1` se algum `Check.ok` for falso; lê `.env` do repositório)
- Verifica: variáveis obrigatórias (`POSTGRES_PASSWORD`, `N8N_ENCRYPTION_KEY`, `OPENCODE_BRIDGE_TOKEN`), `localhost:8000/health`, `localhost:5678/healthz`, bridge `localhost:8787/health` (**aviso**, não falha, se `AI_PROVIDER` não for `opencode`), `STUDIO_DATABASE_URL` alcançável via `/health`; no POSIX, alerta se `.env` tiver permissão mais aberta que `600` (no Windows, pula com aviso)

- [ ] **Step 1: Write the failing tests**

```python
def test_missing_and_blank_secret_fail_without_leaking_value():
    checks = check_env("POSTGRES_PASSWORD=s3cr3t-value\nN8N_ENCRYPTION_KEY=\n", ["POSTGRES_PASSWORD", "N8N_ENCRYPTION_KEY", "OPENCODE_BRIDGE_TOKEN"])
    by = {c.name: c for c in checks}
    assert by["POSTGRES_PASSWORD"].ok
    assert not by["N8N_ENCRYPTION_KEY"].ok and not by["OPENCODE_BRIDGE_TOKEN"].ok
    assert all("s3cr3t-value" not in c.detail for c in checks)

def test_check_port_detects_closed():
    assert check_port("127.0.0.1", free_port(), expect_open=True).ok is False

def test_main_returns_nonzero_when_env_missing(tmp_path, monkeypatch):
    assert doctor.main(root=tmp_path) == 1
```

- [ ] **Step 2: Run** — Expected: FAIL
- [ ] **Step 3: Implement** `doctor.py`
- [ ] **Step 4: Run** `pytest tests/test_doctor.py -v` e `python scripts/doctor.py` na stack real — Expected: testes passam; `doctor` verde com tudo no ar
- [ ] **Step 5: Commit** — `git commit -m "feat: scripts/doctor.py (P01)"`

### Task 10: Backup e restauração

**Files:**
- Create: `scripts/backup.py`, `backups/.gitkeep`
- Modify: `.gitignore` (`backups/*` exceto `.gitkeep`)
- Test: `tests/test_backup.py`

**Interfaces:**
- Produces:
  - `def write_backup(dump: bytes, out_dir: Path, now: datetime) -> Path` — grava `out_dir/faceless-<YYYYmmdd-HHMMSS>.sql.gz` e `…sql.gz.sha256`; devolve o caminho
  - `def verify_backup(path: Path) -> bool` — confere o SHA-256 e se o gzip é legível
  - `main(argv)`: `backup` chama `docker compose exec -T postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB` (credenciais lidas do ambiente do container, nunca impressas) e grava com `write_backup`; `verify <arquivo>`; `restore <arquivo>` **recusa** rodar sem `--yes` e documenta que sobrescreve o banco

- [ ] **Step 1: Write the failing tests**

```python
def test_write_and_verify_roundtrip(tmp_path):
    p = write_backup(b"SELECT 1;", tmp_path, datetime(2026, 11, 19, 10, 0, 0))
    assert p.name == "faceless-20261119-100000.sql.gz" and verify_backup(p)

def test_verify_detects_corruption(tmp_path):
    p = write_backup(b"SELECT 1;", tmp_path, datetime(2026, 11, 19))
    p.write_bytes(p.read_bytes() + b"x")
    assert not verify_backup(p)

def test_restore_requires_yes(tmp_path):
    assert backup.main(["restore", str(tmp_path / "x.sql.gz")]) != 0
```

- [ ] **Step 2: Run** — Expected: FAIL
- [ ] **Step 3: Implement** `backup.py`
- [ ] **Step 4: Run** testes; depois, na stack real: `python scripts/backup.py backup` → `verify` → restaurar num Postgres descartável (`docker-compose.test.yml`) e conferir que `studio.projects` existe — Expected: restauração sem erro
- [ ] **Step 5: Commit** — `git commit -m "feat: backup e verificação do Postgres (P01)"`

### Task 11: Validação real no Lenovo (manual, com evidência)

**Files:**
- Create: `docs/11-validacao-lenovo.md` (checklist + espaço para a saída real)
- Modify: `docs/03-configuracao-windows.md` (correções encontradas na execução)

O agente não alcança o Lenovo; esta tarefa entrega o roteiro e **só é concluída com a saída real colada por você**. Confirmar primeiro o sistema (Windows 11 + Docker Desktop/WSL2 é a suposição).

- [ ] **Step 1:** Escrever o checklist: clonar o repositório; copiar `.env.example` para `.env` e preencher segredos; `docker compose up -d --build`; `python scripts/doctor.py`; `scripts\test-create.ps1` com `IMAGE_PROVIDER=placeholder`; `python scripts/backup.py backup` e `verify`.
- [ ] **Step 2 (você, no Lenovo):** executar o checklist e registrar versões (`docker --version`, `python --version`), tempo do primeiro build e qualquer erro.
- [ ] **Step 3:** Para cada falha, corrigir `docs/03-configuracao-windows.md` ou o script e repetir só o passo afetado.
- [ ] **Step 4: Verification** — Expected: `doctor` sem falhas, vídeo de teste gerado e backup verificado **no Lenovo**, com a saída anexada no documento.
- [ ] **Step 5: Commit** — `git commit -m "docs: validação real no Lenovo (P01)"`

**Marco P01 (M1):** `pytest -q` verde (com banco de teste), `/studio` funcionando na stack, `doctor` verde, backup restaurável e checklist do Lenovo concluído.

---

## Auto-revisão

- **Cobertura da spec:** P00 (contratos, estados, política, schemas e diagramas) → Tasks 1–4. P01 (migrações, layout, doctor, backup, healthchecks, Lenovo) → Tasks 5–11. `UsageLedger` com colunas separadas → Tasks 1 e 6. Teto de custo padrão 0 → Task 3. Aprovação obrigatória → Task 2 (sem atalho a `APPROVED`).
- **Lacuna declarada:** a validação de *para onde* um vídeo `FAILED` pode voltar fica para a P06 (anotado na Task 2).
- **Consistência de tipos:** `VideoStatus`, `transition_video(conn, video_id, expected, new)`, `asset_cache_key(kind, provider, model, prompt, params)` e `check_cost(estimated_usd, spent_usd, cap_usd)` têm a mesma assinatura onde reaparecem.
- **Proporção:** os blocos de código são testes e assinaturas; os corpos ficam com o implementador.
- **Healthchecks de compose:** o `postgres` já tem `healthcheck`; a Task 8 acrescenta `depends_on: condition: service_healthy` ao `renderer`, e o `renderer` ganha `healthcheck` em `/health`.
