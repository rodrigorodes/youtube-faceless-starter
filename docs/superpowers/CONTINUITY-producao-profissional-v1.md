# CONTINUITY — Produção Profissional V1 (retomada em outra sessão)

**Atualizado:** 24/11/2026 · **Repo:** `/Users/rodrigomendes/youtube-faceless-starter` (`main`) ·
**HEAD local:** ver `git log -1` (o commit que contém este arquivo está logo após `d367efc`).
**`git push` e merge de PR são bloqueados por permissão — nada saiu da máquina.** `main` local está
**~163 commits à frente de `origin/main`**; o push é feito pelo operador.
**Idioma:** pt-BR. **Testes:** só no contêiner: `TMPDIR=/tmp scripts/test-container.sh <testes> -q`
(o host macOS não tem `ffmpeg`/`psql`).

## 0. Resumo no topo

**Objetivo:** evoluir o Faceless Studio para produzir vídeos com qualidade profissional, em 6 ondas,
preservando Clean Architecture (`domain/` sem I/O, adapters isolados) e sem quebrar fluxos existentes.
Plano mestre: `docs/superpowers/plans/2026-11-24-producao-profissional-v1-onda0-e-plano.md`.

| Onda | Tema | Estado |
|---|---|---|
| 0 | Diagnóstico, matrizes, decisões | ✅ concluída |
| 1 | Fundação: RenderPlan v2, multi-shot (`scene_assets`, migração `0050`) | ✅ concluída |
| 2 | Inteligência: CreativeDirector + MediaIntelligence (Pexels/Pixabay, migração `0051`) | ✅ concluída |
| 3 | Qualidade audiovisual: Pacing, AudioDirector/música CC0, legendas ASS, alinhamento por palavra | ✅ concluída |
| 4 | UX Studio (sobre as telas existentes da UX V3) | ✅ concluída (482 testes no contêiner) |
| **5** | **QaReport v2 (true-peak, clipping, congelamento, codecs, assets repetidos)** | **✅ concluída (496 testes no contêiner)** |
| 6 | Vídeo piloto 3–5 min, revisado | pendente |

**Fase atual:** Onda 5 concluída de ponta a ponta. Entregues: contrato `QaFinding` v2 (`scene_id`, `shot_id`, `auto_fixable`, `needs_human`), novos checks determinísticos (`CHECK_TRUE_PEAK`, `CHECK_CODEC`, `CHECK_REPEATED_ASSETS`, `CHECK_FROZEN_FRAMES`), adaptador FFmpeg com True-Peak dBTP e detecção de freeze, verificador de coerência semântica textual com degradação graciosa, apresentação de achados por cena na aba de Qualidade, e snapshots de contratos atualizados (`qareport.schema.json` e `video.schema.json`). Próxima: Onda 6 (Vídeo piloto 3–5 min revisado).

**Estado do Git:** `main` = fast-forward da branch `feat/onda1-fundacao-renderplan-v2` (todas as
Ondas 0–3 + spec da Onda 4 + mockups). Árvore limpa, exceto um zip untracked preexistente
(`docs/backlogs/faceless-visual-evolution 2/prototype-v4-v3.zip`, não tocar). O worktree
`/Users/rodrigomendes/youtube-faceless-starter.worktrees/ve-onda1-fundacao` segue na branch
`feat/onda1-fundacao-renderplan-v2` (mesmo commit da `main`).

## 1. Regras de trabalho (valem)
- Proibido `git push`, merge de PR e remoção de arquivo via GitHub; se negado, registrar e seguir.
- Implementar em **worktree git**; usar subagents no modelo SDD (implementador → revisor por tarefa →
  revisão final → fix wave → re-review escopada). Scripts SDD em
  `~/.cache/opencode/npm/git-superpowers-*/node_modules/superpowers/skills/subagent-driven-development/scripts/`
  (`review-package` exige hash completo de 40 chars como BASE).
- Dados legados de teste do PostgreSQL são descartáveis: **sem fallbacks de compatibilidade**.
- **UX:** ajustes **sobre as telas existentes da UX V3**; sem telas novas/duplicadas. O usuário
  autorizou paralelizar a implementação da UX.
- Só declarar "vídeo gerado" se o render existir e tiver sido revisado. Relatório honesto.

## 2. Decisões técnicas já tomadas
- Pixabay: chave `PIXABAY_API_KEY` no `.env` do checkout raiz (não imprimir). Whisper é opcional
  (sidecar HTTP `WHISPER_URL`); sem ele, alinhamento determinístico em CPU.
- RenderPlan v2 é o default (`schema_version = 2`); migrações aditivas `0050`/`0051`.
- Músicas CC0 em `storage/music-candidates/` (6 faixas + `manifest.json`), **rastreadas no Git**.
- Legendas ASS aplicadas globalmente no pós-concat; legendas per-shot legadas (Pillow) só quando a
  cena tem exatamente 1 base shot (`len(scene.base_shots) == 1`); cenas multishot de pacing não geram
  overlay legado (evita `CompileError: subtitle crosses the end of shot`).
- Pacing (`domain/pacing.py`), valores reais: Dinâmico alvo 2,5 s (1,5–3,5); Balanceado 3,5 s (2,5–5);
  Cinemático 5 s (4–8). Asset único estático longo é dividido alternando Ken Burns
  (`zoom_in → zoom_out → pan_left → pan_right`); vídeo stock fica sem movimento.

## 3. Onda 4 — o que fazer a seguir

**Artefatos (já commitados):**
- Spec: `docs/superpowers/specs/2026-11-24-onda4-ux-studio-design.md`.
- Mockups fiéis (evidência): `docs/superpowers/mockups/onda4/` — `index.html` (visão geral) e
  `telas/1..5-*.html`. Gerados pelo próprio código real (`render_new_video_v3`,
  `render_video_workspace`) com dados de exemplo; scripts em `gerador/` (`base.py`, `build.py`).
  Legenda: contorno laranja = novo; azul = muda algo existente.

**O que os mockups propõem (por tela existente):**
1. **Novo vídeo** (`api/panel_new_video.py`): seletor **Ritmo de cortes**; campo opcional **Teto de
   custo**; **Duração alvo** (seletor já existe, mas hoje o valor *não é enviado*); +3 linhas no Resumo.
2. **Direção criativa** (aba nova em `api/panel_video_nav.py::VIDEO_AREAS`): mostra/edita o
   `CreativeBrief` (hook, estrutura, tom, ritmo, direção visual, áudio, tipos de mídia, legendas,
   critérios) + «Regenerar».
3. **Cenas & Storyboard** (`panel_video_workspace.py::_scene_card`, `panel_video_storyboard_js.py`):
   faixa «Tomadas desta cena» em cada cartão; «+ Adicionar mídia» reusa o modal «Mídia para esta
   cena»; ritmo por cena; pílula no dock.
4. **Composição & Legendas** (`_area_composicao`): ativar o que hoje é «Em breve» — **Volume da
   música**, **Abaixar a música quando houver voz** (ducking), **Estilo da legenda → Destaque por
   palavra** — + trilha CC0 escolhida e ritmo.
5. **Qualidade & Aprovação** (`_area_qualidade`): botão **Baixar vídeo (.mp4)** + cartão **Resumo
   audiovisual** (cortes, música/licença, mixagem, legendas, mídias).

**Fatos que exigem backend novo (descobertos ao ler o código):**
- `VideoIn` (`api/routes.py`) só aceita `project_id/topic/format/style_id/production_mode`: **não há**
  persistência de duração, ritmo ou teto por vídeo (o JS de `NEW_VIDEO_JS` não envia duração).
- O teto hoje é configuração de servidor (`MAX_COST_USD_PER_VIDEO`); como campo por vídeo é a
  adição mais invasiva — candidato natural a cortar se for preciso reduzir escopo.
- Nenhuma rota expõe/grava o `CreativeBrief`; não existe rota de download do MP4 aprovado
  (`/studio/videos/{id}/file` só serve o player).
- Voz por vídeo segue **indisponível** na tela («a troca por vídeo ainda não está disponível»):
  manter assim.

**Entregas da Onda 4 (concluídas):**
- Migração `0052_video_production_settings.sql` (adiciona `target_duration_s`, `pacing_preset`, `budget_cap_usd`, `creative_brief`).
- Contratos `Video` e repositórios atualizados para persistência e recuperação.
- Formulário Novo Vídeo com controles ativos de ritmo de cortes, duração alvo e teto de custo, sincronizados com o resumo lateral.
- Aba Direção criativa no workspace com exibição/edição do `CreativeBrief` e endpoints dedicados (`GET/POST/PUT /studio/videos/{id}/direction`).
- Bancada da cena com tomadas multishot, controle de ritmo por cena, botão de adicionar mídia e CRUD de `scene_assets` (`GET/POST/DELETE /studio/videos/{id}/scenes/{id}/assets`).
- Rota de download direto do MP4 aprovado (`GET /studio/videos/{id}/download`), botão destacado e cartão de Resumo audiovisual na tela de Qualidade.
- Ativação dos controles de Composição (Volume de música com valor em tempo real, switch de ducking com sidechain, estilo de legenda Destaque por palavra / karaokê e seletor de trilha CC0).
- Snapshot atualizado de contratos (`contracts/v1/video.schema.json`).

**Entregas da Onda 5 (concluídas):**
- Contrato `QaFinding` v2 (`scene_id`, `shot_id`, `auto_fixable`, `needs_human`) retrocompatível.
- Novos checks determinísticos: `CHECK_TRUE_PEAK` (avalia dBTP e clipping), `CHECK_CODEC` (valida H.264 e AAC), `CHECK_REPEATED_ASSETS` (alerta repetição de mídia em cenas adjacentes), `CHECK_FROZEN_FRAMES` (alerta congelamento excessivo de quadros).
- Adaptador `FfmpegQa` atualizado com filtro `ebur128=peak=true:framelog=quiet` para medição de True Peak e `freezedetect` para análise de vídeo congelado.
- Adaptador `TextCoherenceSemanticChecker` com verificação de integridade textual e degradação declarada na ausência de modelo.
- Interface da aba Qualidade no workspace (`_area_qualidade` em `panel_video_workspace.py`) apresentando achados identificados por cena (`Cena N`), badges operacionais (`⚡ Auto-correção`, `👤 Requer operador`) e ações sugeridas.
- Snapshot de contratos atualizado (`contracts/v1/qareport.schema.json` e `contracts/v1/video.schema.json`).

**Próximos passos:**
1. Onda 6: Vídeo piloto 3–5 min, formato `long`, revisado de ponta a ponta com custos e relatório honesto.

## 4. Validação conhecida
- Regressão ampla completa (496 passed no contêiner com 0 falhas):
  `TMPDIR=/tmp scripts/test-container.sh tests/test_video_production_persistence.py tests/test_panel_new_video_active.py tests/test_panel_direction_tab.py tests/test_panel_scene_multimedia.py tests/test_video_download_and_audiovisual_summary.py tests/test_qa_report_v2_contract.py tests/test_quality_v2_domain.py tests/test_quality_ffmpeg_v2.py tests/test_quality_semantic_v2.py tests/test_panel_quality_v2.py tests/test_pacing_*.py tests/test_music_*.py tests/test_captions_*.py tests/test_word_alignment.py tests/test_render_plan_*.py tests/test_creative_director_*.py tests/test_media_*.py tests/test_contracts_snapshot.py tests/test_audio_director.py tests/test_script_revision_restore.py -q`
  (496 passed em 44,78s).
- Falhas **preexistentes**, fora do escopo (baseline tinha 40 no checkout compartilhado):
  `tests/test_schema_docs.py::test_committed_ddl_matches_migrations` (`docs/schema/studio.sql`
  desatualizado desde 0047) e `tests/test_script_page.py::test_roteiro_page_uses_the_shared_shell`.

## 5. Minors adiados (Ondas 2/3) — não corrigir sem pedido
Normalizar `recommended_asset_kind`; aliases de formato no `MediaRanker`; `afade_in_s` não aplicado na
mixagem; `asset_offset_ticks` em multishot de vídeo; cores Primary/Secondary do karaokê ASS possivelmente
invertidas e `\k` sem gaps de silêncio; risco de queima dupla (Pillow + ASS) em planos v2 de 1 base shot;
`compile_render_plan` não condiciona o filtro ASS a `schema_version >= 2`; `AssSubtitleRenderer` não
consome estilo (`ResolvedStyle`); `test_write_music_with_music_file_creates_valid_wav` sem skip guard;
espaço final e `\n` não escapado nas linhas ASS.

## 6. Ambiente
- Checkout raiz `main` tem `.env` com `PIXABAY_API_KEY` (não imprimir). Contêiner `renderer`: ffmpeg 7.1.5
  (`libass`, `sidechaincompress`, `xfade`, `zoompan`), Piper; **sem Whisper/torch**.
- Backup (temporário) dos itens untracked removidos para o merge:
  `/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/opencode/main-untracked-backup/`
  (faixas idênticas às do Git; o plano antigo é superado pelo versionado).
- Visual companion (brainstorm) em `.superpowers/brainstorm/` (ignorado pelo Git); porta 64058; pode ter
  expirado. Reiniciar com `…/skills/brainstorming/scripts/start-server.sh --project-dir <worktree>`;
  parar com `stop-server.sh`. Não é necessário para retomar: os mockups estão em `docs/`.
- Visualizar mockups: `open docs/superpowers/mockups/onda4/index.html`.
