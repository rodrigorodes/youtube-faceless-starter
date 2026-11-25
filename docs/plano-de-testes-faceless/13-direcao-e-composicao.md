# Direção criativa e composição

**Prefixo dos cenários:** `DRC`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

O workspace do vídeo tem seis áreas canônicas (Direção criativa, Cenas & Storyboard, Composição & Legendas, Qualidade & Aprovação, Publicação YouTube, Fontes & Evidências) e o diagnóstico de produção. A área Direção criativa lê e grava o briefing criativo por GET/POST/PUT /studio/videos/{id}/direction. A área Composição & Legendas grava o override tipado por PATCH /studio/videos/{id}/style-patch com controle otimista de revisão. A navegação usa links de servidor com aria-current e normaliza área desconhecida para cenas.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `DRC.R01` | GET/POST/PUT /studio/videos/{id}/direction: 404 para vídeo inexistente; POST sem brief gera briefing pelo diretor criativo ou fallback determinístico e persiste; PUT exige brief (422) e faz merge raso; GET devolve o brief persistido. | `renderer/app/studio/api/routes.py:1358-1405`, `renderer/app/studio/application/creative_director.py:15-95` | [DRC-01](#drc-01), [DRC-02](#drc-02), [DRC-03](#drc-03) |
| `DRC.R02` | Composição & Legendas salva PATCH /studio/videos/{id}/style-patch com expected_revision otimista; conflito de revisão é 409; grupo ou chave fora da allowlist e valor inválido são 422; patch nulo ou None herda o canal. | `renderer/app/studio/api/routes.py:2997-3020`, `renderer/app/studio/domain/visual_style.py:462-520` | [DRC-04](#drc-04), [DRC-05](#drc-05), [DRC-06](#drc-06) |
| `DRC.R03` | Allowlist de composição: caption (font_size 8-400, bottom >= 0, position top/middle/bottom, font_family dejavu/roboto/georgia/inter, style_kind box/simple/word_highlight); transition (none/fade, fade exige duration_ticks > 0); palette (hex #RRGGBB ou #RRGGBBAA); motion (none/zoom_in/zoom_out/pan_left/pan_right); music (bpm e seed). | `renderer/app/studio/domain/visual_style.py:179-300`, `renderer/app/studio/domain/visual_style.py:56-79` | [DRC-04](#drc-04), [DRC-05](#drc-05), [DRC-07](#drc-07) |
| `DRC.R04` | O workspace do vídeo expõe as seis áreas canônicas na ordem do protótipo; produção é área de diagnóstico; área desconhecida normaliza para cenas; a nav usa aria-current na área ativa. | `renderer/app/studio/api/panel_video_nav.py:13-27`, `renderer/app/studio/api/panel_video_nav.py:40-66` | [DRC-08](#drc-08) |

## Resumo dos cenários

Total: 8 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [DRC-01](#drc-01) | Gerar briefing sem brief explícito | feliz | DRC.R01 | `A_PROJETAR` |
| [DRC-02](#drc-02) | Brief explícito e merge do PUT | feliz/borda | DRC.R01 | `A_PROJETAR` |
| [DRC-03](#drc-03) | Vídeo inexistente e brief ausente no PUT | erro | DRC.R01 | `A_PROJETAR` |
| [DRC-04](#drc-04) | Salvar composição com revisão otimista | feliz | DRC.R02, DRC.R03 | `A_PROJETAR` |
| [DRC-05](#drc-05) | Conflito de revisão e allowlist | erro/concorrencia | DRC.R02, DRC.R03 | `A_PROJETAR` |
| [DRC-06](#drc-06) | Reset de grupo e herança do canal | borda | DRC.R02 | `A_PROJETAR` |
| [DRC-07](#drc-07) | Controles de composição sem efeito | erro | DRC.R03 | `A_PROJETAR` |
| [DRC-08](#drc-08) | Seis áreas e área desconhecida | regressao | DRC.R04 | `A_PROJETAR` |

## Cenários

### DRC-01 — Gerar briefing sem brief explícito

- **Tipo:** feliz
- **Regras:** DRC.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Confirmar que o POST sem corpo gera e persiste um briefing válido.
- **Pré-condições:** Vídeo IDEA com tema e orçamento; caso de uso com diretor criativo dublê.; Repositório espião que registra update_video_creative_brief.
- **Dados:** POST /studio/videos/{id}/direction com corpo vazio ou {}; tema 'Energia solar'.
- **Passos:**
  1. Chamar o POST sem brief.
  2. Ler o brief com GET /direction.
  3. Repetir com o diretor criativo ausente do wiring.
- **Esperado:** Resposta 200 com ok=true e brief com schema_version, topic, narrative_goal, hook, content_structure, tone, pacing, visual_direction, recommended_media, caption, audio_guidance, max_budget_usd e quality_criteria; o GET devolve o mesmo brief; sem diretor, o fallback determinístico é persistido.
- **Limitações:** Não comprova qualidade editorial do briefing nem custo da chamada paga; o fallback é determinístico e não consulta modelo.
- **Automação:** camada `mock`; referência `Proposto: tests/test_direction_api.py (novo) com TestClient e repositório dublê.`

### DRC-02 — Brief explícito e merge do PUT

- **Tipo:** feliz/borda
- **Regras:** DRC.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Verificar que o brief enviado é persistido e que o PUT faz merge raso.
- **Pré-condições:** Vídeo com brief existente de 3 campos.; Repositório espião.
- **Dados:** POST com {"brief": {"hook": "Gancho X"}}; PUT com {"brief": {"tone": "Calmo"}}.
- **Passos:**
  1. Enviar brief explícito no POST.
  2. Enviar PUT com apenas um campo.
  3. Ler o brief final.
- **Esperado:** O POST grava exatamente o brief enviado; o PUT preserva os campos anteriores e substitui apenas os informados; o GET devolve o resultado do merge.
- **Limitações:** O merge é raso: listas e objetos aninhados são substituídos inteiros, não mesclados.
- **Automação:** camada `mock`; referência `Proposto: tests/test_direction_api.py.`

### DRC-03 — Vídeo inexistente e brief ausente no PUT

- **Tipo:** erro
- **Regras:** DRC.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Confirmar os erros 404 e 422 da área de direção.
- **Pré-condições:** Repositório sem o vídeo alvo.
- **Dados:** GET, POST e PUT em /videos/{id}/direction com id desconhecido; PUT com body vazio.
- **Passos:**
  1. Chamar GET, POST e PUT com id inexistente.
  2. Chamar PUT com {"brief": {}} e sem body.
- **Esperado:** Vídeo inexistente devolve 404 nas três rotas; PUT sem brief devolve 422 sem gravar nada.
- **Limitações:** O erro 404 é HTTPException simples; não há mensagem de domínio padronizada.
- **Automação:** camada `mock`; referência `Proposto: tests/test_direction_api.py.`

### DRC-04 — Salvar composição com revisão otimista

- **Tipo:** feliz
- **Regras:** DRC.R02, DRC.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Confirmar que o patch de composição é validado, persistido e devolve a revisão.
- **Pré-condições:** Vídeo com style_patch_revision 0; repositório real ou dublê transacional.
- **Dados:** PATCH com expected_revision 0 e patch contendo caption, transition, palette, motion e music.
- **Passos:**
  1. Enviar o patch válido.
  2. Ler o vídeo e conferir o patch persistido.
  3. Repetir com expected_revision 1.
- **Esperado:** Resposta 200 com a nova revisão e o patch normalizado; o segundo PATCH usa a revisão 1 e também é aceito.
- **Limitações:** A leitura efetiva da composição depende da resolução do estilo; este cenário verifica o patch, não o render.
- **Automação:** camada `local-integrado`; referência `Proposto: tests/test_video_style_patch_api.py.`

### DRC-05 — Conflito de revisão e allowlist

- **Tipo:** erro/concorrencia
- **Regras:** DRC.R02, DRC.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Recusar patch perdedor e conteúdo fora da allowlist.
- **Pré-condições:** Vídeo com revisão 2.; Duas chamadas concorrentes com a mesma revisão.
- **Dados:** expected_revision 1 com revisão atual 2; patch com chave desconhecida; caption.font_size 500; transition fade com duration_ticks 0; palette com cor inválida.
- **Passos:**
  1. Enviar cada variante inválida.
  2. Disparar duas chamadas concorrentes com a mesma revisão.
- **Esperado:** Revisão defasada devolve 409; chave ou valor inválido devolve 422 com a chave nomeada; apenas uma chamada concorrente vence e a outra recebe 409.
- **Limitações:** O 409 depende do controle otimista do repositório; não há bloqueio pessimista.
- **Automação:** camada `local-integrado`; referência `Proposto: tests/test_video_style_patch_api.py.`

### DRC-06 — Reset de grupo e herança do canal

- **Tipo:** borda
- **Regras:** DRC.R02
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Confirmar que patch nulo ou grupo None devolve a herança.
- **Pré-condições:** Vídeo com override de caption e music; canal com estilo próprio.
- **Dados:** PATCH com {"caption": null} e depois com patch vazio.
- **Passos:**
  1. Enviar caption null.
  2. Enviar patch vazio.
  3. Ler o patch e o estilo efetivo.
- **Esperado:** caption null remove o grupo e o vídeo herda a legenda do canal; patch vazio remove o override inteiro; o estilo efetivo volta a ser o do canal.
- **Limitações:** A resolução efetiva é de outro caso de uso; aqui se verifica o patch persistido e a ausência de override.
- **Automação:** camada `local-integrado`; referência `Proposto: tests/test_video_style_patch_api.py.`

### DRC-07 — Controles de composição sem efeito

- **Tipo:** erro
- **Regras:** DRC.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Caracterizar controles renderizados que não entram no patch salvo.
- **Pré-condições:** Workspace na área composicao com estilo efetivo.
- **Dados:** Formulário com trilha, volume e ducking preenchidos; resolução e FPS visíveis; opção Deslizar presente.
- **Passos:**
  1. Alterar trilha, volume e ducking e salvar.
  2. Conferir o payload enviado pelo formulário.
  3. Inspecionar o patch persistido.
- **Esperado:** Caracterização atual: trilha, volume e ducking são exibidos mas não fazem parte do patch; resolução e FPS ficam disabled; Deslizar fica disabled. Critério de correção: remover ou ligar esses controles ao patch e nunca apresentá-los como salvos.
- **Limitações:** Achado de honestidade da UI, não reproduzido em navegador nesta tarefa; registrado em 99-lacunas.
- **Automação:** camada `browser`; referência `Proposto: tests/ve08/test_video_composition_form.py (novo) com Playwright.`

### DRC-08 — Seis áreas e área desconhecida

- **Tipo:** regressao
- **Regras:** DRC.R04
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Confirmar a navegação canônica do workspace.
- **Pré-condições:** Vídeo em qualquer estágio.
- **Dados:** GET /studio/panel/videos/{id}/areas com área inválida 'xyz'.
- **Passos:**
  1. Abrir cada uma das seis áreas.
  2. Abrir uma área desconhecida.
  3. Conferir aria-current.
- **Esperado:** Seis links na ordem do protótipo; a área ativa recebe aria-current; área desconhecida abre cenas; produção não aparece na nav primária.
- **Limitações:** O teste existente cobre a estrutura; o comportamento de área inválida precisa de teste dedicado.
- **Automação:** camada `unit`; referência `Existente: tests/test_video_workspace_v3_nav.py:48-90; área inválida proposta.`

## Resumo do capítulo

8 cenários documentais, todos A_PROJETAR. Execução direta, sem workflow. Os testes citados são referências existentes, não comprovação de aprovação. Os achados de honestidade da tela de composição estão registrados como limitações e em 99-lacunas.
