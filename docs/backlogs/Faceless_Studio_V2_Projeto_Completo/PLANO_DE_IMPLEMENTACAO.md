# Faceless Studio V2: Orquestração, Long-Form, Provedores e Custos — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o orquestrador unificado de produção (`ProductionCoordinator`), suporte a roteiros long-form (~8 min), seleção plugável de provedores de voz (DarkPlanner e Piper TTS local), composição audiovisual dinâmica no FFmpeg e publicador nativo do YouTube com controle orçamentário.

**Architecture:** Clean Architecture rigorosamente desacoplada com entidades puras em `domain/`, portas agnósticas em `application/ports.py`, adaptadores isolados em `adapters/`, e raiz de injeção em `composition.py`, protegido por testes estáticos de AST (`test_architecture.py`).

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL, FFmpeg, Piper ONNX (`pt_BR-faber-medium`), DarkPlanner HTTP API (ACL adapter), Gemini Flash / GPT-4o-mini, fal.ai FLUX / Pexels, Google YouTube Data API v3.

**Spec:** `docs/superpowers/specs/2026-11-20-faceless-studio-v2-avaliacao-custos-e-plano-design.md`

---

## Global Constraints

- **Pureza do Domínio:** `domain/` não importa nada fora de `domain/` ou da biblioteca padrão; nenhuma chamada de I/O, rede, subprocess ou banco.
- **Isolamento da Aplicação:** `application/` só importa de `domain/`; dependências de infraestrutura são resolvidas exclusivamente através de `application/ports.py`.
- **Raiz de Composição Única:** `composition.py` é o único local onde adaptadores concretos são instanciados e conectados aos use cases.
- **Coexistência de Vozes:** O provedor `piper` (local, ONNX, zero custo) deve permanecer ativo e selecionável lado a lado com `darkplanner:<voice-id>`.
- **Baseline de Testes Offline:** Toda a suíte de testes ponta a ponta e unitários deve executar e passar sem necessidade de chaves de API pagas na nuvem.

---

## Review Focus

1. **Aprovação em Modo Automático:** No modo `BUDGET_GUARDED`, se o custo projetado exceder o `budget_cap`, o orquestrador deve pausar imediatamente em `AWAITING_APPROVAL` em vez de falhar ou estourar a verba.
2. **Fallback e Silêncio de Áudio:** Quando o DarkPlanner falhar ou retornar áudio corrompido/silencioso (< 300 peak amplitude), o pipeline deve capturar o erro limpo, registrar `FAILED` no estágio sem corromper o renderizador e não lançar cobrança duplicada em retries.
3. **Idempotência de Upload no YouTube:** Executar o retry de um estágio de publicação já concluído ou em andamento não pode duplicar o vídeo no canal; deve reutilizar o `upload_uri` ou confirmar o ID existente.
4. **Cache de Cena no Render:** A edição de apenas uma cena do roteiro só pode invalidar o WAV e o clipe de vídeo daquela cena específica, mantendo as demais cenas em cache no FFmpeg.
5. **Enriquecimento Opcional de Pesquisa:** Briefings criados manualmente pelo operador com texto já fornecido devem pular o crawler de pesquisa (F3) e ir direto para o outline/roteiro sem lançar erro de fontes ausentes.

---

## Estrutura de Arquivos

```
renderer/app/studio/
├── domain/
│   ├── production.py              <-- [NOVO] ProductionRun, StageExecution, StageKind, ExecutionMode, BudgetGuard
│   ├── contracts.py               <-- [MODIFICADO] Suporte a VisualBeat em Scene
│   └── states.py                  <-- [MODIFICADO] Transições atômicas de ProductionRun
├── application/
│   ├── ports.py                   <-- [MODIFICADO] ProductionRunRepository, PublisherPort
│   ├── coordinator.py             <-- [NOVO] ProductionCoordinator (DAG de estágios e retomada)
│   ├── editorial.py               <-- [MODIFICADO] Suporte a outline e long-form (~8 min)
│   └── config.py                  <-- [MODIFICADO] Resolução de providers de voz e orçamentos
├── adapters/
│   ├── postgres/
│   │   ├── production_repo.py     <-- [NOVO] PostgresProductionRunRepository
│   │   └── migrations/013_*.sql   <-- [NOVO] Tabela production_runs e stage_executions
│   ├── voice_darkplanner.py       <-- [NOVO] DarkPlannerVoice (ACL implementando Voice port)
│   ├── text_llm.py                <-- [NOVO] Adaptador Gemini Flash / OpenAI para long-form
│   ├── render_ffmpeg.py           <-- [MODIFICADO] Suporte a múltiplos VisualBeats e cache de cena
│   └── youtube_publisher.py       <-- [NOVO] GoogleYouTubePublisher (resumable upload e idempotência)
├── api/
│   ├── production.py              <-- [NOVO] Endpoints de runs, status, aprovação e retry
│   └── routes.py                  <-- [MODIFICADO] Registro de rotas de produção
└── composition.py                 <-- [MODIFICADO] Wiring de ProductionCoordinator, DarkPlanner e Publisher
```

---

## Tarefas de Implementação

### Task 1: Saneamento, Higiene e Secret Scanning (F0)

**Files:**
- Create: `scripts/check-secrets.sh`
- Create: `tests/test_secrets_hygiene.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: Arquivos do repositório
- Produces: Script de validação com exit code 0/1 para CI e empacotamento seguro

- [ ] **Step 1: Escrever teste de sanitização de segredos e allowlist**

```python
# tests/test_secrets_hygiene.py
from pathlib import Path

def test_no_sensitive_files_in_git_or_packaging():
    root = Path(__file__).resolve().parents[1]
    forbidden_patterns = [
        "*.pem", "*id_rsa*", "credentials/client_secret*.json",
        "backups/*.dump", "backups/*.sql"
    ]
    leaked = []
    for pattern in forbidden_patterns:
        leaked.extend(list(root.glob(pattern)))
    assert leaked == [], f"Found sensitive files that should not be tracked: {leaked}"

def test_env_example_has_no_real_keys():
    root = Path(__file__).resolve().parents[1]
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    assert "sk-" not in env_example
    assert "AIzaSy" not in env_example
```

- [ ] **Step 2: Executar teste para verificar falha ou comportamento atual**

Run: `pytest tests/test_secrets_hygiene.py -v`

- [ ] **Step 3: Criar script `scripts/check-secrets.sh` e sanitizar `.env.example`**

Criar script bash que faz varredura de regex por chaves de API conhecidas (`sk-`, `AIzaSy`, `Bearer `, `client_secret`) e verifica permissões.

- [ ] **Step 4: Executar teste e validar passagem**

Run: `pytest tests/test_secrets_hygiene.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/check-secrets.sh tests/test_secrets_hygiene.py .env.example
git commit -m "security: add secret hygiene test and check-secrets script (F0)"
```

---

### Task 2: Domínio & Contratos de Produção e Modos de Operação (F1)

**Files:**
- Create: `renderer/app/studio/domain/production.py`
- Modify: `renderer/app/studio/domain/contracts.py:20-50`
- Test: `tests/test_production_domain.py`

**Interfaces:**
- Consumes: `domain.contracts.VideoFormat`, `domain.ids`
- Produces: `StageKind`, `StageStatus`, `ExecutionMode`, `StageExecution`, `ProductionRun`, `BudgetGuard`

- [ ] **Step 1: Escrever teste unitário para o domínio de produção**

```python
# tests/test_production_domain.py
from app.studio.domain.production import (
    ProductionRun, StageExecution, StageKind, StageStatus, ExecutionMode, BudgetGuard
)

def test_production_run_creation_and_budget_guard():
    guard = BudgetGuard(budget_cap_usd=2.0, estimated_cost_usd=1.20)
    assert guard.is_within_budget() is True

    run = ProductionRun(
        run_id="run-001",
        project_id="proj-001",
        video_id="vid-001",
        mode=ExecutionMode.BUDGET_GUARDED,
        budget_guard=guard,
    )
    assert run.can_auto_advance(projected_cost=1.20) is True
    assert run.can_auto_advance(projected_cost=2.50) is False
```

- [ ] **Step 2: Executar teste para verificar que falha (módulo não existe)**

Run: `pytest tests/test_production_domain.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implementar `renderer/app/studio/domain/production.py`**

Definir `StageKind` (BRIEFING, RESEARCH, SCRIPT, ASSETS, RENDER, QA, PUBLISH), `StageStatus` (PENDING, RUNNING, AWAITING_APPROVAL, COMPLETED, FAILED, SKIPPED), `ExecutionMode` (`INTERACTIVE`, `BUDGET_GUARDED`), dataclass pura `BudgetGuard` e `ProductionRun`. Nenhuma importação externa.

- [ ] **Step 4: Executar teste para validar passagem**

Run: `pytest tests/test_production_domain.py -v`
Expected: PASS

- [ ] **Step 5: Validar conformidade de arquitetura**

Run: `pytest tests/test_architecture.py -v`
Expected: PASS (nenhuma violação de import no domínio)

- [ ] **Step 6: Commit**

```bash
git add renderer/app/studio/domain/production.py tests/test_production_domain.py
git commit -m "domain: add ProductionRun and StageExecution domain entities (F1)"
```

---

### Task 3: ProductionCoordinator & Persistência PostgreSQL (F1)

**Files:**
- Create: `renderer/app/studio/application/coordinator.py`
- Create: `renderer/app/studio/adapters/postgres/production_repo.py`
- Create: `renderer/app/studio/adapters/postgres/migrations/013_production_runs.sql`
- Modify: `renderer/app/studio/application/ports.py:100-130`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `domain.production.ProductionRun`, `application.ports.ProductionRunRepository`
- Produces: `ProductionCoordinator.start_run()`, `ProductionCoordinator.advance()`, `ProductionCoordinator.approve_stage()`

- [ ] **Step 1: Escrever teste de coordenação de estágios com retomada determinística**

```python
# tests/test_coordinator.py
from app.studio.domain.production import ExecutionMode, StageKind, StageStatus, BudgetGuard
from app.studio.application.coordinator import ProductionCoordinator

class InMemoryProductionRepo:
    def __init__(self):
        self.runs = {}
    def save_run(self, run): self.runs[run.run_id] = run
    def get_run(self, run_id): return self.runs.get(run_id)

def test_coordinator_pauses_in_interactive_mode():
    repo = InMemoryProductionRepo()
    coord = ProductionCoordinator(run_repo=repo)
    run = coord.start_run(
        project_id="proj-1", video_id="vid-1", mode=ExecutionMode.INTERACTIVE, budget_cap=2.0
    )
    # Após gerar roteiro no modo interativo, deve pausar para aprovação
    coord.advance(run.run_id, current_stage=StageKind.SCRIPT, output={"script": "ok"}, stage_cost=0.02)
    updated = repo.get_run(run.run_id)
    assert updated.stages[StageKind.SCRIPT].status == StageStatus.AWAITING_APPROVAL

def test_coordinator_auto_approves_in_budget_guarded_mode():
    repo = InMemoryProductionRepo()
    coord = ProductionCoordinator(run_repo=repo)
    run = coord.start_run(
        project_id="proj-1", video_id="vid-1", mode=ExecutionMode.BUDGET_GUARDED, budget_cap=2.0
    )
    coord.advance(run.run_id, current_stage=StageKind.SCRIPT, output={"script": "ok"}, stage_cost=0.02)
    updated = repo.get_run(run.run_id)
    assert updated.stages[StageKind.SCRIPT].status == StageStatus.COMPLETED
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_coordinator.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar porta `ProductionRunRepository` em `ports.py`, `ProductionCoordinator` em `application/coordinator.py` e migração Postgres**

Criar use case puro no `application` orquestrando o avanço atômico de etapas, verificação de guardas de custo e persistência com idempotency keys. Criar migração SQL `013_production_runs.sql` e repositório `PostgresProductionRunRepository`.

- [ ] **Step 4: Executar testes de coordenação e arquitetura**

Run: `pytest tests/test_coordinator.py tests/test_architecture.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/application/coordinator.py renderer/app/studio/adapters/postgres/production_repo.py renderer/app/studio/adapters/postgres/migrations/013_production_runs.sql renderer/app/studio/application/ports.py tests/test_coordinator.py
git commit -m "feat: implement ProductionCoordinator and Postgres persistence (F1)"
```

---

### Task 4: DarkPlanner Voice Provider & Coexistência com Piper (F5, DPA)

**Files:**
- Create: `renderer/app/studio/adapters/voice_darkplanner.py`
- Modify: `renderer/app/studio/application/config.py:30-60`
- Modify: `renderer/app/studio/composition.py:30-65`
- Test: `tests/test_voice_providers.py`

**Interfaces:**
- Consumes: `application.ports.Voice` (`speak(text: str, out_path: Path) -> float`)
- Produces: `DarkPlannerVoice` adapter registrado em `composition.py` sob `register("voice", "darkplanner", DarkPlannerVoice)` mantendo `register("voice", "piper", PiperVoice)`

- [ ] **Step 1: Escrever teste de conformidade de contrato para ambos os provedores**

```python
# tests/test_voice_providers.py
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.studio.adapters.voice_piper import PiperVoice
from app.studio.adapters.voice_darkplanner import DarkPlannerVoice

def test_both_voice_providers_implement_voice_contract():
    assert hasattr(PiperVoice, "speak")
    assert hasattr(DarkPlannerVoice, "speak")
    assert PiperVoice.name == "piper"
    assert DarkPlannerVoice.name == "darkplanner"

@patch("httpx.Client.post")
def test_darkplanner_voice_generates_valid_wav_and_duration(mock_post, tmp_path):
    out_wav = tmp_path / "scene_01.wav"
    # Mock de resposta HTTP com payload WAV válido
    mock_post.return_value = MagicMock(
        status_code=200,
        content=b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )
    voice = DarkPlannerVoice(api_url="https://api.fake-darkplanner.com", api_key="secret", voice_id="pt-narrator")
    with patch("app.studio.adapters.voice_darkplanner._validate_wav_audio", return_value=3.5):
        duration = voice.speak("Texto de teste da cena", out_wav)
        assert duration == 3.5
        assert out_wav.exists()
```

- [ ] **Step 2: Executar teste para verificar falha (módulo não existe)**

Run: `pytest tests/test_voice_providers.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implementar `DarkPlannerVoice` e registrar na raiz de composição**

Implementar `renderer/app/studio/adapters/voice_darkplanner.py` com Anti-Corruption Layer (timeout seguro, conversão WAV, validação de silêncio contra `MIN_PEAK`). Registrar em `composition.py` sob o nome `darkplanner`, permitindo selecionar `voice='darkplanner:voice_id'` ou `voice='piper:faber'` em `ProjectConfig`.

- [ ] **Step 4: Executar testes de providers e arquitetura**

Run: `pytest tests/test_voice_providers.py tests/test_architecture.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/adapters/voice_darkplanner.py renderer/app/studio/application/config.py renderer/app/studio/composition.py tests/test_voice_providers.py
git commit -m "feat: add DarkPlanner Voice provider adapter and preserve Piper (F5, DPA)"
```

---

### Task 5: Motor Editorial Long-Form (~8 min) com Gemini Flash / GPT-4o-mini (F4)

**Files:**
- Create: `renderer/app/studio/adapters/text_llm.py`
- Modify: `renderer/app/studio/application/editorial.py:40-120`
- Modify: `renderer/app/studio/domain/contracts.py:60-90`
- Test: `tests/test_editorial_longform.py`

**Interfaces:**
- Consumes: `application.ports.TextModel` (`complete(prompt, json_schema) -> TextResult`)
- Produces: `GenerateLongScript.execute(briefing: ContentBrief) -> LongScriptResult` (12–16 cenas, estimativa de timing em segundos e contagem de palavras)

- [ ] **Step 1: Escrever teste para geração de roteiro longo em duas passagens**

```python
# tests/test_editorial_longform.py
from app.studio.application.editorial import GenerateLongScript
from app.studio.domain.contracts import VideoFormat

class FakeTextModel:
    name = "gemini-flash"
    def cost_estimate(self, prompt: str) -> float: return 0.008
    def complete(self, prompt: str, *, json_schema: dict | None = None):
        from app.studio.application.ports import TextResult, UsageEntry
        # Retorna mock de roteiro longo com 12 cenas estruturadas
        scenes_json = '{"chapters": [{"title": "Hook", "scenes": [{"narration": "Texto da cena 1", "estimated_seconds": 35}]}]}'
        return TextResult(text=scenes_json, usage=UsageEntry(provider="gemini", model="gemini-flash", input_tokens=1500, output_tokens=3500, cost_usd=0.015))

def test_generate_long_script_calculates_word_count_and_timing():
    model = FakeTextModel()
    generator = GenerateLongScript(text_model=model)
    result = generator.generate(topic="A Queda de Constantinopla", target_duration_seconds=480)
    assert result.estimated_duration_seconds >= 400
    assert result.scene_count >= 10
    assert result.cost_usd == 0.015
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_editorial_longform.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar geração de roteiro longo e adaptador `GeminiFlashText` / `OpenAiText`**

Implementar geração em duas passagens (Capítulos → Cenas com pacing balanceado de 130–150 palavras/minuto) e registrar estimativas financeiras por token consumido.

- [ ] **Step 4: Executar testes de roteiro e arquitetura**

Run: `pytest tests/test_editorial_longform.py tests/test_architecture.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/adapters/text_llm.py renderer/app/studio/application/editorial.py tests/test_editorial_longform.py
git commit -m "feat: add long-form 8-minute script generation and cost tracking (F4)"
```

---

### Task 6: Visual Beats & Montagem Dinâmica no FFmpeg (F5)

**Files:**
- Modify: `renderer/app/studio/domain/contracts.py:25-55`
- Modify: `renderer/app/studio/adapters/render_ffmpeg.py:80-160`
- Test: `tests/test_render_visual_beats.py`

**Interfaces:**
- Consumes: `RenderSpec`, `Scene` com `list[VisualBeat]`
- Produces: `FfmpegRenderer.render_scene_clip()` com cache em disco e concatenação final

- [ ] **Step 1: Escrever teste de renderização de cenas com múltiplos visual beats e cache**

```python
# tests/test_render_visual_beats.py
from pathlib import Path
from app.studio.domain.contracts import Scene, VisualBeat
from app.studio.adapters.render_ffmpeg import build_scene_filtergraph

def test_scene_filtergraph_generates_ken_burns_and_transitions():
    scene = Scene(
        scene_id="sc-01",
        narration="Texto de teste",
        beats=[
            VisualBeat(beat_id="b1", duration=4.0, effect="zoom_in"),
            VisualBeat(beat_id="b2", duration=5.0, effect="pan_right"),
        ]
    )
    filtergraph = build_scene_filtergraph(scene)
    assert "zoompan" in filtergraph
    assert "fade" in filtergraph
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_render_visual_beats.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar suporte a `VisualBeat` e filtros de movimento no `render_ffmpeg.py`**

Adicionar transições cinemáticas leves e animações Ken Burns com FFmpeg (`zoompan`) sobre imagens estáticas. Implementar gravação de cache em `storage/renders/scenes/{scene_hash}.ts`.

- [ ] **Step 4: Executar testes de render e arquitetura**

Run: `pytest tests/test_render_visual_beats.py tests/test_architecture.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/domain/contracts.py renderer/app/studio/adapters/render_ffmpeg.py tests/test_render_visual_beats.py
git commit -m "feat: add VisualBeat camera motion and scene render cache in FFmpeg (F5)"
```

---

### Task 7: YouTube Data API v3 Publisher Nativo & Idempotência (F8)

**Files:**
- Create: `renderer/app/studio/adapters/youtube_publisher.py`
- Modify: `renderer/app/studio/application/publishing.py:50-110`
- Test: `tests/test_youtube_publisher.py`

**Interfaces:**
- Consumes: `application.ports.PublisherPort`, `PublicationSpec`
- Produces: `GoogleYouTubePublisher.upload_resumable(video_file, metadata, idempotency_key) -> str (youtube_id)`

- [ ] **Step 1: Escrever teste de upload seguro com travamento de concorrência e sessão resumable**

```python
# tests/test_youtube_publisher.py
from unittest.mock import MagicMock, patch
from app.studio.adapters.youtube_publisher import GoogleYouTubePublisher

@patch("httpx.Client.post")
def test_youtube_resumable_upload_and_idempotency(mock_post, tmp_path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"dummy mp4 data")

    mock_post.return_value = MagicMock(
        status_code=200,
        headers={"Location": "https://www.googleapis.com/upload/youtube/v3/resumable-session-123"},
        json=lambda: {"id": "yt_video_abc123"}
    )
    publisher = GoogleYouTubePublisher(channel_id="chan-01", token_repo=MagicMock())
    yt_id = publisher.publish(
        video_path=dummy_video,
        title="Título do Vídeo",
        description="Descrição",
        tags=["historia", "curiosidades"],
        privacy="private",
        idempotency_key="run-001-pub"
    )
    assert yt_id == "yt_video_abc123"
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_youtube_publisher.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar `GoogleYouTubePublisher` em `adapters/youtube_publisher.py`**

Implementar upload resumable via API v3 com lease lock no Postgres para evitar uploads duplicados do mesmo vídeo e armazenamento seguro de refresh tokens por canal.

- [ ] **Step 4: Executar testes de publicação e arquitetura**

Run: `pytest tests/test_youtube_publisher.py tests/test_architecture.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/adapters/youtube_publisher.py renderer/app/studio/application/publishing.py tests/test_youtube_publisher.py
git commit -m "feat: add native Google YouTube Data API v3 publisher with idempotency (F8)"
```

---

### Task 8: Endpoints de Produção e Verificação Arquitetural Ponta a Ponta (F1, F2, Regras de Arquitetura)

**Files:**
- Create: `renderer/app/studio/api/production.py`
- Modify: `renderer/app/studio/api/routes.py:10-50`
- Modify: `renderer/app/studio/composition.py:70-130`
- Test: `tests/test_production_api.py`
- Test: `tests/test_architecture.py`

**Interfaces:**
- Consumes: `ProductionCoordinator`
- Produces: `POST /production-runs`, `GET /production-runs/{id}`, `POST /production-runs/{id}/approve`

- [ ] **Step 1: Escrever teste de integração de API para disparar e inspecionar corridas**

```python
# tests/test_production_api.py
from fastapi.testclient import TestClient
from app.studio.composition import build_app

def test_production_run_lifecycle_via_api():
    app = build_app()
    client = TestClient(app)
    response = client.post("/production-runs", json={
        "project_id": "proj-default",
        "topic": "História dos Samurais",
        "mode": "budget_guarded",
        "budget_cap_usd": 2.50
    })
    assert response.status_code == 201
    run_id = response.json()["run_id"]

    status_resp = client.get(f"/production-runs/{run_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] in ["PENDING", "RUNNING", "AWAITING_APPROVAL"]
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_production_api.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar rotas em `api/production.py` e amarrar na composição**

Registrar endpoints que delegam diretamente para o `ProductionCoordinator` sem acoplar controllers a banco de dados ou adaptadores.

- [ ] **Step 4: Executar suíte completa de testes e validação rigorosa de Clean Architecture**

Run: `pytest tests/test_production_api.py tests/test_architecture.py -v`
Expected: PASS (nenhuma violação de imports)

- [ ] **Step 5: Commit**

```bash
git add renderer/app/studio/api/production.py renderer/app/studio/api/routes.py renderer/app/studio/composition.py tests/test_production_api.py
git commit -m "feat: wire production run endpoints and validate full architecture compliance (F1, F2)"
```
