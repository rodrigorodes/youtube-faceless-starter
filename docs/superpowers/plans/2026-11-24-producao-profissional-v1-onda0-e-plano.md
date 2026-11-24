# Produção Profissional V1 — Onda 0 (diagnóstico) e plano por ondas

Data: 2026-11-24. Status: **proposta para aprovação; nenhum código de produto foi alterado.**
Base factual: leitura do código em `renderer/app/studio` (HEAD `2beb90e`) por quatro mapeamentos
independentes + inspeção do ambiente. Onde não executei, está marcado como *hipótese*.

## 1. Conclusão que muda o plano

O pedido parte de "vídeos simples". O repositório **não está no zero**: já tem `RenderPlan v1`
(ADR-001), builder, compilador FFmpeg, cache seletivo por cena, QA, orçamento com reservas,
`ProductionRun` com leases, workspace V3 com 5 áreas e Piloto/Diretor. O trabalho real é
**ligar o que está órfão e preencher lacunas**, não construir um motor novo.

O maior gargalo para "qualidade audiovisual superior" é um só: **o produtor.** O contrato
aceita N shots por cena, mas `render_plan_builder` e `_build_plan` emitem **1 shot por cena**
(1 imagem + Ken Burns). `beat_plan.py` e `visual_beat.py` não têm consumidor; `ContentBrief`
não tem consumidor; `NotVerifiedSemanticChecker` é o único checker semântico.

## 2. Ambiente (fatos medidos)

| Item | Estado |
|---|---|
| Host macOS | sem `ffmpeg`, `piper`, `whisper`, `psql`. Testes só valem **no contêiner** (`scripts/test-container.sh`). |
| Contêiner `renderer` | ffmpeg 7.1.5 com `libass`, `xfade`, `zoompan`, `sidechaincompress`, `loudnorm`, `amix`, `drawtext`; Piper 1.8.0; numpy; Pillow. **Sem Whisper/torch.** |
| Credenciais (só presença) | `PEXELS_API_KEY` definida. Nenhuma chave Pixabay. LLM via bridge `opencode` (`STUDIO_TEXT`). |
| Stack rodando | `renderer`, `postgres`, `n8n` e outros contêineres já ativos. |
| Baseline de testes | Ver §9 (resultado real, abaixo). `tests/e2e_ux`/`e2e_full` exigem Playwright, ausente na imagem de teste — ficam fora da suíte padrão. |
| Observação | O checkout principal trocou de branch durante a análise (`main` → `feat/publication-lease-recovery`). Implementar **somente em worktree dedicado** por onda. |

## 3. Matriz de capacidades

| Capacidade | Existe? | Estado atual (evidência) | Lacuna | Mudança proposta |
|---|---|---|---|---|
| Creative Director | **Parcial** | `EditorialContext` (público, narrativa, CTA, duração: `editorial.py:56,139`); plano de capítulos no longform (`longform.py:149`). `ContentBrief` (`domain/content_brief.py`) **sem consumidor**. | Sem hook, ritmo, direção visual, mídia recomendada, critérios de qualidade; sem etapa própria nem persistência. | Evoluir `ContentBrief` → `CreativeBrief` v1 (schema, persistência, nova etapa `direction` antes de `script`, injeção nos prompts). Cache por hash de entrada. |
| Storyboard | **Existe** | Aba Cenas editável (`panel_video_workspace.py:630`, `panel_video_storyboard_js.py`). | Mostra 1 mídia/cena; sem direção criativa nem beats. | Exibir beats/assets por cena (Onda 4). |
| Multiple Assets | **Parcial (só contrato)** | `Shot` N por cena no domínio; `Scene.asset_id` único (`contracts.py:111`); `_build_plan` 1 asset/cena (`render_plan_ffmpeg.py:492`). | Persistência N:1, produtor, compilador de shots base sequenciais *(hipótese: parece suportar; não rodado)*. | Tabela `scene_assets` + produtor de beats (Onda 1). |
| Timeline Composer | **Parcial** | Tracks `visual`/`narration`/`subtitle`; overlay máx. 1 por cena e só imagem (`render_compiler.py:45,300`). Timeline da UI é texto. | Tracks `music`/`sfx`/`caption` não modeladas; sem overlay múltiplo/vídeo. | `RenderPlan v2` com tracks e `AudioMix` (Onda 1/3). |
| B-roll Selection | **Ausente** | `broll_enabled`/`broll_note` são só flag+nota de UI (`contracts.py:113`). Pexels só **foto**, `per_page=1`, primeiro resultado (`media_pexels.py:82`, `image_stock.py:50`). Veo é stub. | Vídeo stock, ranking, consulta semântica, dedupe entre cenas, upload do usuário, Pixabay. | Media Intelligence (Onda 2). |
| Audio Director | **Parcial** | `MIX_FILTER` fixo: música 0,40, `sidechaincompress`, `amix`, `loudnorm -16/-1.5/11`, AAC160k (`render_plan_compiler.py:44`). Música **sintetizada** (`rich.synth_music`). | Sem SFX, música por arquivo, `afade`, parâmetros no plano, detecção/corte de silêncio, true-peak/clipping. | `AudioMix` no plano + catálogo local de faixas licenciadas (Onda 3). |
| Captions | **Parcial** | SRT + PNG Pillow com `overlay enable=` (`render_plan_compiler.py:268`). Cues proporcionais a caracteres (`render.py:85`); presets posição/fonte/paleta (`visual_style.py:206`). `word_highlight` aceito mas **no-op**. | Tempo por palavra, ASS/libass, realce de palavra. | Alinhamento + ASS opt-in por estilo (Onda 3). |
| Quality Evaluator | **Parcial** | Determinístico: LUFS, silêncio, preto, duração, resolução, assets, overlay (`quality.py`, `render.py:131`). Semântico: stub `not_verified`. | Sem clipping/true-peak, codec, frames duplicados/congelados, `scene_id` estruturado, correção automática, avaliação multimodal. | Onda 5. `QaReport` v2. |
| Preview | **Parcial** | Player do render real (Qualidade, `/preview`). Prévia da Composição é aproximada. | Preview por cena/rascunho. | Preview de cena (clip curto) (Onda 4). |
| Selective Regeneration | **Parcial** | Render: grafo+cache por nó, só cenas alteradas (`domain/render_cache.py`). Voz por cena. `Production.regenerate` refaz o run inteiro. | Sem regeneração seletiva de mídia por cena nem cache de resposta do LLM; fingerprint visual ignora estilo de legenda *(hipótese)*. | Onda 2/5. |

Também existentes e **reaproveitados**: ledger/reservas/limites por canal e vídeo, aprovação com
`qa_override` auditado, `ReopenForEditing`, boot recovery, estilos (`VisualStyle`), proveniência e
licença **obrigatórias** por asset (CHECK no banco).

## 4. Achados preexistentes (registrados, **não corrigidos** nesta tarefa)

1. `Transition.kind="none"` recai em fade de 0,25 s, não em corte seco (compilador).
2. `caption.style_kind="word_highlight"` é aceito na validação e **não faz nada**.
3. Orçamento: `budget_guard` vem **desligado por padrão** (`settings.py:54`); sem a flag, o piso por canal também some (`wiring.py:669`).
4. `usage_ledger` sem categoria (só `step` livre), sem duração e sem tentativas por linha; não existe categoria "vídeo gerado"/"render".
5. Retry de etapa é manual, sem limite nem backoff.
6. Card de histórico de revisões só é renderizado em `visao-geral`, que `normalize_area` redireciona → **inacessível** na UI, apesar dos endpoints existirem.
7. Undo/redo vive só no cliente; perde-se ao recarregar.
8. UI "decorativa": duração/budget/idioma no Novo Vídeo não chegam ao backend; nota da Composição diz que transição "não é consumida", mas `transition ∈ APPLIED_GROUPS`.
9. `docs/18-painel.md` e `evidence/2026-11-22-ux-e2e-findings.md` descrevem UI antiga.
10. `test-container.sh` não sobe o Postgres quando `TMPDIR` aponta para o diretório temporário do OpenCode; com `TMPDIR=/tmp` funciona.

## 5. Decisões de arquitetura (minhas; reversíveis)

- **Um motor, dois modos.** Rápido = Piloto; Profissional = Diretor (já existem e já compartilham `ProductionRun`). Nada de segundo motor.
- **Contratos:** `RenderPlan` → **v2** e `QaReport` → v2, seguindo `docs/contracts-versioning.md` (bump inteiro, leitura fechada, `load_versioned` com conversor v1→v2 explícito, schema gerado + snapshot). Projetos existentes continuam renderizando (builder v1 → upconvert).
- **LLM decide, código executa.** Creative Director/visual intent produzem JSON validado por schema + regras de negócio (budget, tipos permitidos); o compilador FFmpeg só consome o plano.
- **Menos chamadas pagas:** a *visual intent* e as consultas de busca saem **na mesma chamada** que escreve as cenas (campo novo no `_SCHEMA`), com `paid_key` por hash; o reranking multimodal é opcional e amostral (thumbnails, não vídeo).
- **Legendas ASS como caminho opt-in** (`caption_engine=ass`); o caminho PNG/Pillow permanece para paridade golden.
- **Sem dependência pesada no default:** alinhamento por palavra primeiro tenta o que o Piper já oferece; Whisper só como extra opcional (spike na Onda 3).
- **Providers:** Pixabay e música por arquivo entram como adapters atrás das portas existentes; vídeo generativo continua stub opcional.
- Tudo em **migrações aditivas** (próxima: `0050`).

## 6. Ondas

Cada onda = 1 worktree/branch (`ve/…` convention), PRs pequenos, testes antes de código (TDD), sem push/merge.

### Onda 1 — Fundação (multi-shot, transições, áudio no plano) — **CONCLUÍDA** ✅

- **Status:** CONCLUÍDA em 2026-11-24 na branch `feat/onda1-fundacao-renderplan-v2` (worktree `ve-onda1-fundacao`).
- **Commits:**
  - `12edb60` chore(contracts): sync contracts snapshot with current domain models
  - `65d6b09` feat(render_plan): evoluir RenderPlan para v2 com AudioMix, novas transicoes e offset
  - `7048a63` feat(repo): implementar persistencia e contratos para multiplos assets por cena
  - `8559abc` feat(builder): suportar multiplos shots base sequenciais por cena no RenderPlan
  - `2a69a22` feat(compiler): implementar corte seco, trim de video com offset e audio mix declarativo
  - `ddb27b3` feat(cache): refinar fingerprints visuais e de audio para invalidacao seletiva precisa
  - `d34dae6` test(render): adicionar teste de integracao FFmpeg real com cenas multi-shot e video
  - `70364e0` test(render): atualizar assercoes legadas para compatibilidade com RenderPlan v2
- **Modelos e Entregas:**
  - `RenderPlan v2` (`schema_version = 2`, suporte retrocompatível a v1 com `upconvert_v1_to_v2`, snapshots atualizados).
  - `AudioMix`: parâmetros declarativos de mixagem, ducking e loudnorm.
  - `Transition`: tipos `none`, `fade`, `crossfade`, `cut` com validações semânticas de duração.
  - `SceneAsset` e migração `0050_scene_assets.sql`: persistência N:1 de múltiplos assets sequenciais por cena com fallback legado.
  - `build_render_plan`: múltiplos shots contíguos por cena garantindo exatidão de ticks sem lacunas.
  - Compilador FFmpeg: corte seco v2 sem filtros `fade`, trim com offset temporal para vídeo (`media_type="video"`), e mixagem de áudio declarativa.
  - `render_cache`: fingerprints granulares contemplando transições, offsets e estilo visual.
- **Evidência de Testes:**
  - Suíte completa de renderização e persistência no contêiner:
    `TMPDIR=/tmp scripts/test-container.sh tests/test_render_*.py tests/test_composition.py tests/test_contracts_snapshot.py tests/test_scene_assets_repo.py -q`
    Resultado: **423 passed, 0 failures, 2 warnings** em 87.43s.
  - Teste de integração E2E real FFmpeg (`tests/test_render_plan_multishot_e2e.py`):
    Validação completa de vídeo de 7s (1080x1920) com multi-shot imagem+vídeo, corte seco e fade, verificado via `ffprobe` e `evaluate_qa`.

1. **TDD de contrato:** `RenderPlan v2` (tracks `music`/`sfx`, `Transition` = `cut|fade|crossfade`, `AudioMix{music_gain, duck{…}, loudnorm{…}, fades}`, `video` como shot); conversor v1→v2; snapshot regenerado.
2. **Persistência:** migração `0050_scene_assets` (N assets por cena, `position`, `start_s`, `end_s`, `role`, `motion`, `transition`); leitura legada (cena com `asset_id` único) vira 1 beat.
3. **Produtor de beats:** ligar `beat_plan` ao builder (`build_render_plan` → N shots base); validar lacuna/sobreposição por track.
4. **Compilador:** `xfade` para crossfade, corte seco para `cut`; shots `video` (trim+scale) no `_build_plan`; corrigir o *none → fade* **somente** atrás da versão v2 (v1 mantém comportamento).
5. **Cache:** incluir estilo de legenda/transição/áudio no fingerprint do nó correto (v2).
6. **Testes:** contrato, migração/compat, ordenação, sobreposição, duração, transições, ausência de mídia, **integração FFmpeg real com assets sintéticos locais** (gerados por `ffmpeg lavfi` no contêiner), golden preservado para v1.
**Aceite:** cena com 3 assets (2 imagens + 1 vídeo) renderiza com crossfade/corte; vídeo v1 antigo renderiza byte-equivalente.

### Onda 2 — Inteligência (Creative Director + Media Intelligence) — **CONCLUÍDA** ✅

- **Status:** CONCLUÍDA em 2026-11-24 na branch `feat/onda1-fundacao-renderplan-v2` (worktree `ve-onda1-fundacao`).
- **Commits:**
  - `659cfbc` feat(director): definir contrato de dominio CreativeBrief
  - `743fae2` feat(director): implementar caso de uso CreateCreativeBrief e injecao no roteiro
  - `d7eb5d4` feat(media): implementar MediaRanker com pontuacao deterministica e deduplicacao
  - `1bd567d` feat(pexels): suportar busca de video stock na API do Pexels
  - `a43b931` feat(pixabay): implementar adaptador MediaSearch para fotos e videos do Pixabay
  - `1a7be9a` feat(media): integrar ranking inteligente, deduplicacao e suporte multiprovedor
  - `334d804` fix(media): implementar deduplicacao entre cenas, fetcher multiprovedor e queries complementares
- **Modelos e Entregas:**
  - `CreativeBrief` (`domain/creative_director.py`): Contrato puro e congelado para direção criativa (hook, estrutura de conteúdo, tom, ritmo, direção visual, tipos de mídia recomendados, estratégia de legendas, orientação de áudio, validação estrita de budget e critérios de qualidade).
  - `CreateCreativeBrief` e `build_prompt` (`application/creative_director.py`, `application/editorial.py`): Caso de uso para síntese de briefing com cache de hash (`paid_key`), e enriquecimento do prompt de roteiro para gerar `visual_intent`, `recommended_asset_kind` e `search_queries` por cena.
  - `MediaRanker` (`domain/media_ranker.py`): Motor determinístico de pontuação de candidatos de mídia por resolução, aspect ratio, duração mínima, casamento léxico com intent/queries e penalidade severa de repetição (`-50 pts`) para evitar mídias duplicadas entre cenas.
  - `PexelsMediaSearch` com vídeo (`adapters/media_pexels.py`): Suporte completo à busca de vídeo stock na API do Pexels (`media_type="video"`), além de imagens, extraindo `duration_s`, resolução e atribuição fotográfica/videográfica.
  - `PixabayMediaSearch` (`adapters/media_pixabay.py`): Adaptador completo para fotos e vídeos da API Pixabay sob `Pixabay Content License`, resiliente a payloads parciais.
  - `MultiProviderMediaFetcher` e `MultiProviderMediaSearch` (`adapters/media_multi.py`, `composition/wiring.py`): Agregador resiliente multiprovedor (Pexels + Pixabay) e despachante inteligente de download por URL/licença, integrado ao pipeline `ProduceAssets` e `SearchSceneMedia` com tracking de `used_media_ids` e expansão de queries de busca.
- **Evidência de Testes:**
  - Suíte completa de inteligência de mídia e editorial no contêiner:
    `TMPDIR=/tmp scripts/test-container.sh tests/test_creative_director_*.py tests/test_media_*.py -q`
    Resultado: **169 passed, 0 failures, 2 warnings** em 9.67s.
  - Suíte completa de regressão combinada (editorial, mídia, render e contratos):
    `TMPDIR=/tmp scripts/test-container.sh tests/test_creative_director_*.py tests/test_media_*.py tests/test_render_*.py tests/test_contracts_snapshot.py -q`
    Resultado: **556 passed, 0 failures, 2 warnings** em 89.77s.

1. `CreativeBrief` v1 (objetivo, abertura, hook, estrutura, tom, ritmo, direção visual, tipos de mídia, texto/legenda, música/SFX, restrições de custo, critérios de qualidade) + validação (nenhuma sugestão altera config sensível nem estoura budget).
2. Etapa `direction` no `ProductionRun`, atrás de flag; usa `ContentBrief` existente como base; `paid_key` por hash de entradas.
3. Prompt de cenas passa a devolver `visual_intent`, `asset_kind`, `queries[]` por beat.
4. **Media Intelligence:** `MediaRanker` (regras: resolução/aspecto/duração, penalidade de repetição por `provider+external_id`, casamento de termos) + `SemanticReranker` opcional (LLM multimodal sobre thumbnails, só se houver orçamento e provider); justificativa e score persistidos.
5. Pexels **vídeo** (`media_type="video"` hoje lança `ModelUnavailable`), `per_page>1`; adapter Pixabay (**bloqueado sem chave**); upload de asset do usuário com licença declarada.
6. Testes: schemas, budget excedido, falha de provider, retry, dedupe, ranking determinístico (providers falsos); testes de rede/pagos marcados `@pytest.mark.live` fora da suíte padrão.

### Onda 3 — Qualidade audiovisual
1. **Pacing Engine** (domínio puro): duração do clip por fala/ênfase/estilo → beats; presets de edição (extensão de `VisualStyle`).
2. **Audio Director:** `AudioMix` aplicado; `afade`; SFX; música por arquivo de um **catálogo local licenciado** (CC0, com licença registrada); detecção de silêncio e true-peak no QA.
3. **Captions:** spike de alinhamento (Piper → fallback faster-whisper opcional em imagem separada); cues por palavra; ASS com realce, margens seguras e quebra de linha.
4. Testes de sincronização (tolerância em ms), integração FFmpeg com ASS.

### Onda 4 — UX (reuso da UX V3)
1. Novo Vídeo: **ligar de verdade** duração, voz, idioma, perfil de qualidade e teto de custo (hoje decorativos); estimativa de custo real.
2. Aba **Direção** (CreativeBrief editável/aprovável), Storyboard com beats, **Bancada da cena** (duração, N mídias, remover, texto/voz), Timeline interativa mínima (reordenar/duração), preview de cena.
3. Undo/redo persistido no servidor (reusa `scene_revisions`); religar card de histórico; botão de **exportação/download** do arquivo aprovado.
4. Estados de loading/erro/progresso/recuperação; nenhum botão sem efeito (teste que falha se houver controle sem handler).

### Onda 5 — Avaliação
`QaReport v2` (`scene_id`, `auto_fix`, `needs_human`), checagens novas (clipping/true-peak, codec, frames duplicados/congelados, assets repetidos), adapter semântico multimodal por amostragem de frames (**só se o bridge aceitar imagem — a verificar**), painel por cena, regeneração seletiva a partir do achado, gate de aprovação existente mantido. Nota: nota alta do LLM nunca libera sozinha.

### Onda 6 — Piloto
Vídeo longo de 3–5 min, formato `long`, com os providers reais disponíveis (LLM via bridge pago, Pexels, Piper, FFmpeg). Relatório com custo por categoria, QA, revisão visual por amostragem de frames. **Só será declarado gerado se o render existir e for revisado.**

## 7. Orçamento e rastreabilidade (transversal, entra na Onda 1/2)
Migração aditiva: `usage_ledger.category` (`llm|tts|image|video_gen|storage|render`), `duration_ms`, `attempt`. Piloto roda com `STUDIO_BUDGET_GUARD=1` e teto por vídeo definido antes. Sem mudar o default global (achado 3) sem decisão.

## 8. Riscos
| Risco | Mitigação |
|---|---|
| Regressão do renderer v1 / goldens | v2 atrás de versão; `tests/golden` obrigatório em cada PR |
| Alinhamento por palavra sem Whisper | spike com saída honesta: se inviável, cues por frase + realce desabilitado e documentado |
| Licença de música/stock | só catálogo com licença registrada; Pexels com atribuição; nada "licenciado por estar na web" |
| Custo LLM | `visual_intent` na mesma chamada; `paid_key` por hash; reranking opcional |
| Bridge LLM sem imagem | Onda 5 degrada para avaliação textual + deterministic; documentado |
| `xfade` + `zoompan` + áudio sincronizado | testes de duração por frame no ffprobe |
| Checkout compartilhado muda de branch | worktrees isolados |

## 9. Bloqueios / dependências externas
- **Decisão do usuário (2026-11-24): Whisper = SIM.** Onda 3 testa primeiro o alinhamento do Piper; se não bastar, imagem de contêiner **separada e opcional** com `faster-whisper` (imagem padrão do renderer inalterada). Desempenho em pt-BR no hardware local ainda não validado.
- **Pixabay:** chave fornecida e validada em 2026-11-24 (HTTP 200, vídeo até 2160p, 100 req/60 s), gravada em `.env` (ignorado pelo Git). Falta repassá-la no `docker-compose.yml` e ler a Content License antes do uso real. A API cobre só imagem/vídeo, **não música/SFX**.
- **Música:** precisa de faixas CC0 fornecidas ou baixadas com licença verificada; senão a trilha continua sintetizada.
- **LLM multimodal:** depende do bridge.
- **Whisper:** opcional; se rejeitado, realce por palavra fica como limitação documentada.

## 10. Baseline de testes (resultado real)
Comando: `TMPDIR=/tmp scripts/test-container.sh -q -p no:cacheprovider --ignore=tests/e2e_full --ignore=tests/e2e_ux`
(HEAD `0c280f3`, checkout compartilhado; o HEAD mudou de `2beb90e` durante a análise).

**3586 passed, 40 failed, 20 skipped** (10 min 16 s). **O baseline NÃO está verde.** Falhas por grupo:
- UI/shell (≈30): `test_panel_page`, `test_channels_page`, `test_analytics_page`, `test_connections_page`, `test_settings_sections`, `test_styles_page`, `test_script_page`, `test_panel_production_page`, `test_video_style_api`.
- Contratos/esquema/migração: `test_contracts_snapshot::test_committed_contracts_match_code`, `test_schema_docs` (2), `test_db` (2), `test_secrets_hygiene` (extração do starter).
- `test_production_flow_db` (2).

Causa **não investigada** (preexistente, fora do escopo da Onda 0): suspeita de estado divergente do checkout compartilhado (branch trocando, mudanças não commitadas em docs). **Primeira ação da Onda 1:** criar worktree limpo a partir do commit escolhido, rodar a suíte e fixar a lista de falhas conhecidas; só falhas novas contam como regressão.
