# Fatia E — motor editorial long-form e aprovação de roteiro (F4-02..F4-09)

Worktree: `/Users/rodrigomendes/.local/share/opencode/worktree/39a258/e-longform`, branch `feat/e-longform`, base `51734c7`.

## Escopo entregue

| Item | Entrega | Onde |
|---|---|---|
| F4-02 | Prompts curto x longo separados; o longo planeja por blocos (gancho, contexto, desenvolvimento, payoff/CTA) | `domain/longform.py` (`Block`, `Chapter`, `ScriptPlan`, `validate_structure`), `application/longform.py` (`build_long_outline_prompt`, `build_long_scenes_prompt`, `build_prompt_for_format`) |
| F4-03 | Palavras/minuto e alvo de duração configuráveis; duração por cena reutiliza a contagem já existente | `domain/narration_duration.py` (novo `estimate_text_durations`; `estimate_narration_durations` passou a delegar — sem duplicar a contagem), `review_script` |
| F4-04 | Roteiro em duas passagens: plano de capítulos e depois cenas com citações | `application/longform.GenerateLongScript` (`_call` por passagem) |
| F4-05 | Revisão determinística de estrutura, continuidade, redundância, duração, citações e invenção, reutilizando o gate factual | `domain/longform.review_script` (usa `facts.check_narration`) |
| F4-06 | Roteiro versionado e aprovação humana presa a (versão, hash); editar cria outra versão e invalida a aprovação | `domain/longform.ScriptApproval`/`approval_is_current`, `application/longform.ApproveScriptVersion`/`EditScriptScene`, migration `0023`, `approve`/`list_script_records` |
| F4-07 | Tela de Roteiro (`#roteiro`) com capítulos+duração, status do fact-check, aprovação por versão e `<details>` de versões | `application/script_view.BuildScriptView`, `api/panel.render_script`, rota `GET /studio/videos/{id}/roteiro` + `POST /studio/videos/{id}/script/approve` |
| F4-08 | Edição invalida só os outputs downstream dependentes | `domain/longform.DEPENDENCIES`/`invalidated_outputs` + efeitos persistidos (cenas substituídas, aprovação por hash não transferida, fontes intactas) |
| F4-09 | Roteiro de ~480 s em 3 temas/estilos (documental/lista/narrativa) determinístico e offline | `tests/test_longform_480s.py` |

## Commits

- `cc24b23` feat(longform): domínio de estrutura por blocos, revisão e invalidação (F4-02/03/05/06/08)
- `159a212` feat(longform): motor em duas passagens, prompts curto/longo e aprovação por versão (F4-02/04/06)
- `c7de848` feat(longform): persistência versionada de plano/hash e aprovação por versão (F4-06/08)
- `7d9e841` feat(ui): tela de Roteiro com dado real, versões e aprovação (F4-07)

## Contagens reais

- Testes novos: **36** — `test_longform_domain.py` 14, `test_longform_editorial.py` 8, `test_longform_repo.py` 5, `test_longform_480s.py` 3, `test_script_page.py` 6.
- Suíte completa (Docker `faceless-v2-hygiene-test-local:latest`, Postgres descartável `e-pg`, `-p no:cacheprovider`):
  **1747 passed, 35 skipped, 4 failed** nas duas execuções. As falhas são ambientais ou instáveis, não desta fatia:
  - `test_secrets_hygiene.py::test_real_starter_archive_is_safe_and_keeps_scripts_executable` e `..._extracted_starter_runs_contract_snapshot_and_backup_import` — as 2 falhas ambientais conhecidas (`Secret hygiene check could not complete safely`, `.git` externo ausente no mount). **Não corrigidas** por serem ambientais.
  - 2 falhas instáveis sob carga, diferentes em cada execução (`test_render_adapters`/`test_render_api` na 1ª; `test_publish_api` na 2ª) e que **passam isoladas** com o mesmo Postgres. Não toquei em render nem em publicação.
- Focada do domínio/app (sem DB): `test_longform_domain + test_longform_editorial + test_longform_480s + test_architecture` → **31 passed**.
- Repo/DB: `test_longform_repo + test_db + test_editorial_repo + test_architecture` → **36 passed**.
- Tela: `test_script_page` → **6 passed**.

## Pendente (registrado, não mascarado)

- **Calibração de TTS real**: a duração continua sendo **estimativa por palavras/minuto**, não medição de voz, pausas ou prosódia. Não há integração com o DarkPlanner/voice para medir velocidade real. Documentado no docstring de `domain/longform.py` e no rail da tela (“A duração real só existe depois do TTS”).
- **Edição a partir de estados avançados**: `EditScriptScene` só aceita o vídeo em `IDEA`/`SCRIPTED` (a máquina de estados não permite retroceder de `FACT_CHECKED`/`RENDERED`/`AWAITING_APPROVAL` sem a retomada validada da P06). Reexecutar a produção para “rebobinar” os downstream (cita o mockup) fica para a fatia de produção. A propagação de invalidação está coberta no domínio e no repositório (nova versão substitui cenas, aprovação por hash deixa de valer, fontes intactas), mas **não** um fluxo de UI de edição.
- **Provider long-form real**: nenhum adaptador novo (`GeminiFlashText`/`OpenAiText` do plano). Reutiliza-se a porta `TextModel`/bridge OpenCode existente; o teste F4-09 usa provider fake determinístico. Não foi adicionado SDK de provedor (proibido em `domain/`/`application/`).
- **Aprovação pela UI**: o ator humano (`approved_by`) vem de `STUDIO_BROWSER_USER`; não há identidade por usuário no banco (o mesmo padrão do fluxo de publicação).

## Onde o código contradisse o plano

- **Assinatura do caso de uso**: o plano propõe `GenerateLongScript.execute(briefing: ContentBrief) -> LongScriptResult`. Implementei `execute(video_id, *, target_seconds, words_per_minute)` — o motor real é escopado a vídeo, coleta claims dos snapshots e persiste plano/hash/cenas atomicamente, reusando o gate de fontes existente. `LongScriptResult` existe e expõe `estimated_duration_seconds`, `scene_count`, `cost_usd`, `plan`, `review`.
- **Custo**: o exemplo do plano espera `cost_usd == 0.015` de uma chamada; o roteiro longo é **duas** passagens, então o custo é a soma das duas chamadas (e cada passagem passa pelo mesmo padrão de reserva/validação do `GenerateScript`).
- **Faixa de cenas**: o plano diz 12–16; a base já limita cenas a 2–20 (`MIN_SCENES/MAX_SCENES`). Fixei o formato longo em **8–20** cenas (constante `MIN_LONG_SCENES/MAX_LONG_SCENES`). A tela do mockup (18 cenas/8 min) respeita o limite de 400 caracteres de `Scene.narration`: ~480 s a 130–150 wpm pede ~12–18 cenas.
- **Contratos**: o plano alteraria `domain/contracts.py`; a trilha do Render Plan congela `contracts/` (snapshot gerado), então plano/hash/aprovação vivem em módulo próprio (`domain/longform.py`) e em tabela nova, **sem** alterar `Script`/`Scene` exportados.
- **`<details>` e estados**: o mockup mostra “7 claims verificados”, “script_v1 substituída”, durações ilustrativas. A tela renderiza **dado real** (nomes de capítulos, contagens, hash, duração estimada) ou **estado vazio explícito**; um teste prova que nenhum texto ilustrativo do mockup vaza e que não há `%`, `role="progressbar"` nem `<progress`.

## Buraco conhecido no mockup x real

- O mockup mostra sub-linhas por capítulo com “2 claims verificados”. A revisão conta **cenas** sem citação e claims desconhecidas por roteiro, não “claims verificados por capítulo” (o fact-check é por versão inteira). A tela mostra o status agregado do fact-check e a contagem de cenas/capítulos real, sem inventar um número por capítulo.

## Migração

- `0023_longform_script_approval.sql`: `studio.script_plans` e `studio.script_approvals`, ligadas por FK a `studio.scripts(video_id, version)`; adicionada às **duas** listas de `tests/test_db.py`.
