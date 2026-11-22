# VE-00 — Revisão do site de referência, do projeto e da aplicação

**Data:** 22/11/2026 · **HEAD:** `a2e6a39` (árvore com 2 itens não rastreados: `docker-compose.preview.yml` e esta pasta).
**Escopo:** leitura e medição. Nenhum arquivo de produção foi alterado.
**Legenda:** **[F]** fato verificado (arquivo:linha, comando ou captura) · **[H]** hipótese a confirmar na fase indicada.

---

## 1. Site de referência — https://fstudio.digital

**O que li:** home, `/studio`, `/como-funciona`, `/recursos/{cenas,edicao,narracao,chat-ia}`, `/planos`, com capturas de tela da home, de `/recursos/cenas` e da home em 390 px.
**Limite:** são páginas de marketing. As telas do produto são "ilustração interativa" (o próprio site diz). **Não verifiquei** o comportamento real do app Windows; tudo abaixo é o que o site *promete*.

### 1.1 O que é
Um **editor desktop para Windows** (assinatura R$ 89,90–356/mês), centrado em edição manual ou assistida: importa SRT + narração, associa mídia a cada bloco do SRT, edita numa timeline e exporta localmente. Contas, APIs e créditos de IA ficam por conta do usuário (BYOK).

Nosso produto é outra coisa: **pipeline automatizado** (tema → fontes → roteiro → voz → render → QA → aprovação humana → YouTube), em Docker + painel web. **Seguir o site = adotar a qualidade visual e a organização por cena, não copiar o produto, o texto ou os assets** (RULES §15).

### 1.2 Capacidades prometidas × o que a nossa evolução visual cobre

| Capacidade no site | Fase VE | Situação em nosso código |
|---|---|---|
| Cena com **fontes mistas** (banco de vídeo, IA, YouTube) e comparação no **Organizador de Cenas** | VE-03, VE-06 | Só imagem: porta `ImageModel` + Pexels foto + Gemini/placeholder. Sem vídeo, sem alternativas por cena **[F]** |
| **Camadas** na timeline (B-roll, CTAs, efeitos) | VE-01, VE-02 | Domínio aceita camadas; compilador recusa **[F]** (§2.1) |
| **Tipografia cinética**, legendas, efeitos | VE-04 | Legenda estática (caixa + texto); só `font_size`, `bottom` e 3 cores **[F]** |
| **Configurações prontas por nicho**, modelos reutilizáveis | VE-04 | Estilos versionados + patches já existem (`visual_style.py`); falta o catálogo/preset **[F]** |
| **Prévia antes de exportar** | VE-06 | Prévia só do corte final renderizado; sem prévia por cena **[F]** (captura do painel) |
| Trilhas e sons, modificador de voz | — | Fora do escopo visual (música sintetizada, TTS Piper) |
| Chat IA / agentes no editor, multilogin Flow, clonagem de voz | — | **Fora do escopo** (README do backlog exclui editor completo e SaaS) |
| Planos, equipe, multi-PC, cupom | — | Fora do escopo |

### 1.3 Padrões de UI/UX do site que valem como referência

- **Hierarquia tipográfica forte:** títulos grandes e apertados, uma palavra-chave em cor de acento; rótulos em caixa-alta monoespaçada ("01 / SEU ESPAÇO DE PRODUÇÃO").
- **Mockup do produto como herói**, com legenda honesta ("ilustração… imagens de exemplo").
- **Organizador de Cenas:** grade numerada, cada célula com a **origem** (Banco / Google Flow / YouTube) e o estado "vinculada à cena". É o modelo mental para VE-06.
- **Jornada em 4 passos** (material → cenas → acabamento → exportar), curta e escaneável.
- Paleta escura com **acento laranja único**, cartões com borda fina; contraste alto.
- Cuidados de honestidade: "Ilimitado" definido; "beta" e "disponibilidade conforme plano" explícitos.

**Recomendação de identidade:** **não** trocar nossa paleta (violeta, shell V3 já aprovado, contraste ≥ 4,5:1 documentado em `shell_v3_css.py`). Adotar *princípios* (hierarquia, rótulo de origem por cena, estados honestos), não cores.

---

## 2. Projeto (`renderer/`) — inventário contra o backlog

### 2.1 Tabela de inventário

| Item do backlog (README "Baseline verificado") | Confirmado? | Evidência |
|---|---|---|
| `render_plan.py` contrato canônico versionado | **Sim, com nuance** | `schema_version` é um **inteiro global** (`domain/schema.py:11`, `SCHEMA_VERSION = 1`) e o validador **rejeita qualquer outro valor**. Não existe "v2" do plano: só campos **aditivos com default** sobrevivem sem migração (§2.3) |
| `_require_single_layer()` no compilador | **Sim** | `application/render_compiler.py:332`; teste que o fixa: `tests/test_render_compiler.py:366` |
| `PlanFfmpegRenderer` executor único | **Sim** | `adapters/render_plan_ffmpeg.py:228`; publicação atômica `:592` |
| `production.py` stages/checkpoints/aprovação | **Sim** | aprovação amarrada a `render_id` + `checksum` (`application/production.py:395,430`) |
| `quality.py` multimodal não verificado | **Sim** | `MULTIMODAL_EVALUATION = "out_of_scope_without_provider"` (`domain/quality.py:44`); `FindingCategory = technical \| editorial` |
| `visual_style.py` estilos e patches | **Sim** | `KNOWN_PARAMS = motion, music, transition, caption, palette, voice, extra` (`:63`); `extra` é carregado e **ignorado** pelo render |
| V3.1 em paralelo | **Sim, com README desatualizado** | O README da V3.1 diz "F01, F03–F07 planejadas", mas o `git log` mostra F03.T04, F05.T04, F06.T02/T03 e "gate de regressão" fechados. Reler `evidence/status.md` da V3.1 antes de VE-04 |

### 2.2 Achados **não** previstos no backlog (mudam o plano)

1. **O plano nasce do `RenderSpec` legado, dentro do adaptador.** `PlanFfmpegRenderer._build_plan()` (`render_plan_ffmpeg.py:394`) reconstrói o `RenderPlan` a partir de `RenderSpec` (`application/ports.py:57`): listas paralelas `scenes/images/speech_wavs/scene_seconds`, **uma imagem PNG por cena**. O `media_type` é fixado em `"image"` (`:420` e `:480`). Logo, **ampliar o contrato (VE-01) não basta**: nada alimenta camadas ou vídeo. VE-01/02 precisam de um canal de entrada (`RenderSpec.layers`, default vazio) e do builder aceitando overlays.
2. **O compilador já sabe tratar `video`, `graphic` e `text`** (`render_compiler.py:394-412`), mas o executor só entrega imagens. É capacidade latente, não implementada de ponta a ponta.
3. **`Shot.transition` existe no contrato e o compilador não o lê** (`grep transition render_compiler.py` → vazio). O fade é fixo (`FADE_S = 0.25`, `domain/render.py:9`) por segmento. Transição "configurável" hoje é decorativa.
4. **O domínio já permite sobreposição entre tracks.** `Timeline` só rejeita overlap **na mesma track** (`render_plan.py:326-337`) e exige cobertura da cena pelo **conjunto** de shots (`:339-355`). A única barreira real é o compilador. Mas falta distinguir *base* de *overlay*: hoje um shot qualquer pode "cobrir" a cena, então um overlay opaco esconderia a base sem erro.
5. **Concat `-c copy` de um segmento por shot** é a premissa do pipeline (`render_compiler.py:266-273`). Um segundo shot na mesma cena **viraria um segmento extra concatenado em sequência** — vídeo errado, sem erro. Por isso VE-02 deve compor **dentro do segmento da cena base**, não adicionar segmentos.
6. **Cache de render por fingerprint** (`domain/render_cache.py:171`): nós `visual` são por shot e o fingerprint ignora qualquer coisa que o plano acrescente. Se overlays entrarem no filtro sem entrar no fingerprint, **o cache reaproveita segmento antigo e o vídeo sai sem o overlay** (falha silenciosa). Inversamente, alterar o fingerprint de planos sem overlay invalidaria todo o cache. Regra: o termo novo entra **somente quando há camadas**.
7. **`ProviderKind` só tem `text/image/voice/renderer`** (`domain/provider.py:26`). Não há porta de busca de vídeo/mídia; VE-03 cria porta nova, reaproveitando `CostEstimate` e `route_provider`.
8. **Fonte hardcoded de Linux** (`rich.py:24`: `/usr/share/fonts/truetype/dejavu/...`). No macOS os overlays quebram com `OSError: cannot open resource`. É ambiente (o produto roda em Docker/Windows via Docker), mas impede validar render no host.

### 2.3 Compatibilidade de contrato (consequência do achado §2.2-1)

`RenderPlan` e filhos têm `extra="forbid"`. Campos **novos opcionais com default** deixam documentos antigos legíveis (não há bump). Contrapartida: um plano gravado por código novo **não é legível por código antigo** (rollback). Mitigação: feature flag que impede gravar campos novos enquanto desligada, e nenhum bump de `SCHEMA_VERSION` (um bump invalidaria todos os planos persistidos).

---

## 3. Baseline medido (VE-00)

| Onde | Comando | Resultado |
|---|---|---|
| Host macOS (sem `ffmpeg`, sem fonte DejaVu, Python 3.11.9, pydantic 2.5.0) | `python3 -m pytest tests -q -p no:cacheprovider` | **20 failed, 2248 passed, 775 skipped** (38 s) |
| Host — 12 arquivos de render/plano/estilo/QA | `pytest` do subconjunto | 16 failed, 294 passed, 9 skipped |
| Container `youtube-faceless-starter-renderer` (ffmpeg em `/usr/bin/ffmpeg`), tests montados somente leitura | `pytest tests/test_render_plan_executor.py tests/test_render_reuse.py tests/test_render_plan_repo.py tests/test_render_compiler.py tests/test_render_quality_e2e.py` | **63 passed, 10 skipped, 0 failed** (13,6 s) |

**Leitura:**
- As 16 falhas de render no host são **ambiente** (sem `ffmpeg` e sem a fonte). Dentro da imagem do renderer, as mesmas suítes passam. Isso confirma o registro prévio da V3.1 (`evidence/pre-existing-failures.md`, §2).
- As 4 falhas restantes do host: `test_contracts_snapshot`, `test_port_contracts` (2) e `test_secrets_hygiene`. O registro da V3.1 atribui falhas de contrato à versão do pydantic; **não confirmei a causa das 4 individualmente** **[H]**. Não afetam as fases VE, mas VE-01 mexe no contrato: confirmar se `test_contracts_snapshot` passa **no container** antes de alterar o schema.
- Os 775 *skips* são, em sua maioria, testes de banco sem `STUDIO_TEST_DSN` **[H]**: a cobertura de persistência de plano (`test_render_plan_repo`) fica parcial sem Postgres descartável.
- **Baseline de referência para as próximas fases:** rodar sempre no container do renderer. Comando usado (não escreve no repositório):

```bash
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD":/w:ro -w /w --entrypoint sh \
  youtube-faceless-starter-renderer -c \
  'pip install -q pytest==8.3.5 && PYTHONPATH=renderer python -m pytest tests/test_render_*.py tests/test_architecture.py -q -p no:cacheprovider'
```

**Golden render (pendente, executar no início de VE-01):** não congelei MP4 byte a byte (x264/threads variam). O golden deve ser `CompiledRender.digest()` (já determinístico, `render_compiler.py:207`) + métricas por ffprobe (duração, nº de quadros, resolução, áudio) de um plano legado.

---

## 4. Aplicação (painel) — o que a captura mostra

Painel em `http://127.0.0.1:8000/studio/panel` (container saudável, autenticado; nenhuma credencial foi exibida). Capturas: Início e detalhe de vídeo.

| Observação | Evidência | Implicação |
|---|---|---|
| Os cartões de "Continuar de onde parou" mostram **um degradê borrado**, não um quadro do vídeo | captura Início | Não há *thumbnail* por vídeo/cena; ganho visual grande e barato após VE-06 |
| Detalhe do vídeo: **"Prévia do corte final"** é um placeholder até existir render; **não há visão por cena** (asset, origem, duração) | captura Vídeo/Detalhe | É exatamente o espaço do **Organizador de Cenas** (VE-06) |
| Estados honestos e acionáveis ("A produção parou… Motivo… Tentar novamente") | captura Vídeo/Detalhe | Padrão a manter: VE-05 deve exibir "não verificado" no mesmo tom |
| Casca V3 (sidebar, tema claro/escuro, acento violeta, contraste documentado) | `shell_v3_css.py:17-30` | Reaproveitar; não reabrir design system |
| Dois cartões de "Tendências do canal" com o **mesmo título** e visualizações diferentes (28,4 mi × 26,8 mi) | captura Início | Provavelmente dois vídeos distintos com título igual; pode ser duplicidade de dados **[H]**. Fora do escopo VE; não corrigido |

---

## 5. Divergências entre o backlog e o código real (corrigir no backlog)

1. README "Resultado esperado" assume tipos `Layer`/`MediaCandidate`/`VisualEvaluation` (RULES "Contratos mínimos"); a própria RULES manda **estender `Shot`/`AssetReference`/`QaReport`** antes de criar tipos. Recomendo **estender `Shot`** (§PLAN, VE-01) e só criar `MediaCandidate` e `VisualEvaluation`, que não têm equivalente.
2. README "Como executar" passo 1 (copiar a pasta) **já está feito** (a pasta existe, não rastreada).
3. O backlog não cita o `RenderSpec` como gargalo de entrada (§2.2-1) nem o cache (§2.2-6): incluídos no PLAN.
4. A V3.1 trata este trabalho como "Projeto B — Audiovisual Engine", com gate de **benchmark audiovisual e custo antes de expor UI** (`faceless-studio-v31/05-roadmap.md`). `application/benchmark.py` e `tests/test_render_benchmark.py` existem: reutilizar em vez de criar métrica nova.
