# Estilo visual do canal (VisualStyle) — desenho

**Projeto:** Faceless Studio V2 — continuidade da Render Plan Foundation (F5-RP §13)
**Versão:** 1.0
**Status:** Desenhado (brainstorming concluído); item 1 implementado, item 2 fatiado
**Data:** 2026-11-21

---

## 1. Problema

O `RenderPlan` tem um campo `style_snapshot: StyleSnapshot(style_id, version)` — a
referência **versionada** à identidade visual de quem produziu o vídeo (R4/RP-016). O
desenho da fundação antevia que essa referência apontaria para a identidade do canal
(§13, "evoluções posteriores": *Visual Style Engine*, *Channel Identity*).

O que existe hoje, medido no código:

| Fato | Evidência |
| --- | --- |
| A função que liga canal → snapshot **já existe** | `domain/render_plan_builder.py:102` — `style_snapshot_for_channel(profile)` |
| Ela **não** é usada em produção | o único chamador monta o plano com uma constante |
| O executor grava `studio-default@1` no lugar do canal | `adapters/render_plan_ffmpeg.py:52-53, 390` — `DEFAULT_STYLE_ID`/`DEFAULT_STYLE_VERSION` |
| O canal coleta identidade visual, voz, áudio, CTA | `domain/channel.py:155` (`ChannelProfile`), UX em `api/panel_channels.py` |
| Nenhum campo do canal chega ao render | `profile.visual_identity`/`voice`/`audio`/`cta` só são lidos pelos roteadores do painel e pelo repositório |

Ou seja: **o usuário preenche a identidade do canal, ela é persistida — e o plano grava
uma constante.** É a mesma família de "config que mente" que o resto do arco vem fechando.
E não existe **nenhuma** engine de estilo: nenhuma superfície configura aparência, e o
`style_id` do plano aponta para algo que ninguém aplica.

## 2. Decisões (do usuário, no brainstorming)

1. **Estilo é propriedade do canal.** Cada canal segue **um** estilo. O vídeo não escolhe
   estilo — ele **herda** o do canal, e o plano registra o **retrato versionado**
   (`style_id` + `version`) do momento em que foi construído.
2. **O estilo é uma entidade nomeada e reutilizável** (biblioteca), não um conjunto de
   campos soltos no canal. Vários canais podem apontar para o mesmo estilo; editar o
   estilo muda todos eles. (Resposta "Opção A".)
3. **O vídeo pode sobrepor** o estilo do canal para um caso específico (herda por padrão,
   pode apontar outro estilo sem mudar o canal).
4. **Começar extensível e simples**: poucos parâmetros de verdade, mais um mecanismo de
   extensão (`extra`) que permite crescer conforme o uso, sem migração.
5. **O canal é a unidade de trabalho do produtor** (achado de produto). O produtor de vídeo
   pensa em **canal** — público, nicho, cara, voz, destino — não em "projeto". "Projeto" e
   "canal" hoje **duplicam** a mesma coisa (`projects.name`/`niche`/`language` ×
   `channel_profiles.name`/`strategy`/`audience`/`pillars`/`visual_identity`/`voice`), e o
   produtor não sabe onde põe o quê.
6. **A conexão do YouTube é por canal** (não por "conta" do produtor): o token é do canal,
   e mesmo brand channels de uma mesma conta Google tipicamente exigem consentimento
   próprio. Manter por canal evita o risco de dois canais publicando na mesma conta.
7. **A biblioteca de estilos é compartilhada** (o ponto de "reutilizável"): um estilo é
   definido uma vez e vários canais apontam para ele. Logo a biblioteca mora **acima** do
   canal (nível do estúdio/organização). Hoje o app é single-tenant, então na prática é
   **um pool só**, pronto para ganhar `organization_id` quando a multi-tenancy ligar.

## 3. Modelo

### 3.1 Hierarquia

```
Estúdio (organização — existe no schema, vazia; o app roda single-tenant)
 ├── VisualStyle   ← NOVO: a biblioteca **compartilhada** de estilos (uma por estúdio)
 │     • id, organization_id, name, params (jsonb), version, archived, timestamps
 │     • versionado por snapshot (mesmo padrão de channel_profile_revisions)
 │
 └── Canal (ChannelProfile)   ← ganha 1 campo: style_id → VisualStyle
      ├── conexão YouTube (por canal)
      └── Vídeo               ← herda o estilo do canal; pode sobrepor
            • style_snapshot no plano = (style_id, version) do estilo efetivo
```

**Por que a biblioteca é do estúdio:** o sentido de "reutilizável" é compartilhar. Se a
biblioteca ficasse dentro do canal, um estilo não serviria a outro canal — e o produtor
recopiaria, que é exatamente o problema que queremos evitar. Hoje (single-tenant) há um
pool só; `organization_id` já deixa a coluna pronta.

**O canal é a unidade (Etapa 1 do produto):** o produtor cria canais, cada um com a sua
identidade, o seu estilo e a sua conexão do YouTube. "Projeto" deixa de ser um conceito
separado — some a duplicação. Não requer mudança de constraint (hoje já é 1 canal por
projeto); é reframe + juntar a identidade duplicada.

### 3.2 Parâmetros v1

Cada parâmetro mapeia um **knob que o render já tem** (ou que é custo baixo expor). Nada
de parâmetro decorativo: se o render não aplica, o parâmetro não entra — ele vai para
`extra` até ter aplicação.

| Parâmetro | Controla | Já existe no render? | Custo |
| --- | --- | --- | --- |
| `motion` | ciclo de movimento de câmera por cena (Ken Burns) | ✅ `Motion` (`none/zoom_in/zoom_out/pan_left/pan_right`), honrado via `Effects.motion` → compilador → ffmpeg | **0** |
| `music` | trilha: `{bpm, seed}` | ✅ `DEFAULT_MUSIC_PARAMS = {"bpm":122,"seed":7}` | **0** |
| `transition` | corte entre cenas: `{kind: none|fade, duration_ticks}` | ✅ `Transition` no contrato | **0** |
| `caption` | tamanho/posição da legenda | ⚠️ hardcoded em `_LAYOUT` por formato | baixo |
| `palette` | cores da legenda e do destaque | ⚠️ literais no adapter (`(255,0,140)` etc.) | baixo |
| `voice` | a voz do canal | ⚠️ `rich.py:55` (`PIPER_VOICE or spec or default`) | baixo — e resolve a "duas verdades" |

```jsonc
// params de um VisualStyle (v1)
{
  "motion": ["zoom_in", "zoom_out", "pan_right", "pan_left"],
  "music": {"bpm": 122, "seed": 7},
  "transition": {"kind": "fade", "duration_ticks": 8},
  "caption": {"font_size": 58, "bottom": 1560},
  "palette": {"caption_text": "#FFFFFF", "caption_box": "#000000A5", "accent": "#FF008C"},
  "voice": {"model": "pt_BR-faber-medium"},
  "extra": {}          // extensão livre, versionada, ignorada pelo render até ser ligada
}
```

### 3.3 Extensibilidade (`extra`) — o "conforme o uso vamos melhorando"

`extra` é um mapa livre que:

- é **persistido e versionado** junto do estilo desde o dia 1;
- é **carregado** no plano (fica no snapshot/params do estilo efetivo);
- é **ignorado** pelo renderer enquanto não houver knob ligado para aquela chave.

Assim, quando `extra: {"lut": "warm"}` já estiver salvo, ligar o knob de LUT é só fazer o
renderer **ler** a chave — os estilos existentes começam a funcionar sem migração. É o
"fácil e flexível" com contrato, não com promessa.

### 3.4 Versionamento

Mesmo padrão já usado para o canal (`channel_profile_revisions`, `snapshot jsonb`):

- `visual_style_revisions (style_id, version, snapshot jsonb)` — o retrato de cada versão.
- **Editar** um estilo → `version + 1` + nova revisão.
- O vídeo referencia `(style_id, version)` **do momento do build**. Mudar o estilo depois
  **não** reescreve o passado: o vídeo antigo continua apontando para a versão antiga; um
  render novo pega a versão nova.
- **Ganho:** como o estilo não mexe em áudio, trocar a cara do canal **reusa a narração**
  (o cache do RP-06c invalida só o que depende do conteúdo da cena). Trocar estilo fica
  barato.

### 3.5 Resolução (runtime)

```
vídeo → projeto → canal(style_id) [→ override do vídeo] → VisualStyle.params → RenderSpec → RenderPlan
                                                                                 └─ StyleSnapshot(style_id, version)
```

- `domain` continua puro: uma função `resolve_style(...)` que decide o estilo efetivo.
- `application` não conhece banco: o `RunRender` recebe um `style_for(project_id, video_id)`
  injetado (mesma forma de `voice_for`/`renderer_for`).
- A leitura do `VisualStyle` e do override do vídeo mora em `adapters/`; a fiação, só em
  `composition.py` (enforçado por `tests/test_architecture.py`).

## 4. UX

- **Uma superfície nova "Estilos"** (dentro de Canais ou seção irmã): lista dos estilos do
  projeto, criar/editar (nome + os parâmetros), arquivar. Não inventa dado: mostra os
  parâmetros reais e, quando o valor é o default do sistema, diz que é o default.
- **No canal:** um seletor "qual estilo este canal segue" (o `style_id`).
- **No vídeo:** opção "usar o estilo do canal" (default) ou "sobrepor" (escolher outro
  estilo), sem alterar o canal.

## 5. Fatias

### Item 1 — Fiação (aprovado) — **implementado nesta rodada**

Ligar o caminho que já existe: o executor deixa de gravar `studio-default@1` e passa a
gravar o estilo do canal.

- `RenderSpec` ganha `style: StyleSnapshot | None`.
- `RunRender` ganha `style_for: Callable[[str], StyleSnapshot | None]` (project_id → snapshot).
- `PlanFfmpegRenderer._build_plan` usa `spec.style` ou cai no default **apenas quando não
  há canal** (sem canal não há estilo a referenciar; o default é honesto).
- `composition.py` fia `style_for` a partir de `PostgresChannelProfileRepository.get_by_project`
  → `style_snapshot_for_channel`.

Efeito: o `style_snapshot` do plano passa a **apontar para o canal de verdade**. A voz/
identidade/CTA deixam de ser decorativas na referência (o que elas *aplicam* vem no item 2).

### Item 2 — A biblioteca de estilos (aprovado) — fatiado

| Fatia | Entrega | Depende de |
| --- | --- | --- |
| **VS-01** | Migração `visual_styles` + `visual_style_revisions`; domínio `VisualStyle` (+ `params` validado, `extra`); repositório Postgres | — |
| **VS-02** | Canal ganha `style_id`; `ChannelProfile` e repo; resolução `resolve_style(channel, video)` | VS-01 |
| **VS-03** | `style_for` passa a resolver o **VisualStyle** (não o canal): snapshot = `(style_id, version)` do estilo efetivo; liga `motion`/`music`/`transition` do estilo no plano | VS-01, VS-02, item 1 |
| **VS-04** | Aplicar `caption`/`palette`/`voice` no renderer (tirar `_LAYOUT`/literais de dentro do adapter) | VS-03 |
| **VS-05** | UX: superfície "Estilos" (CRUD) + seletor no canal + override no vídeo | VS-01..VS-04 |

Critério de pronto por fatia: teste verde, arquitetura limpa, árvore limpa, nada removido
sem prova de morte.

## 6. Fora de escopo

- Engine visual além dos 6 parâmetros (correção de cor, LUT, tipografia arbitrária) —
  entra por `extra` quando o uso pedir.
- Multi-tenant real (organização/workspace como fronteira de estilo) — hoje single-tenant;
  a decisão foi deixar o projeto como fronteira.
- Retomar o `index % 4` do renderer legado: não volta (fundação §5.6/§14).

## 7. Itens abertos registrados

- **Dono da voz:** o canal guarda `voice`; o `ProjectConfig`/`STUDIO_VOICE` também; o
  render usa só o do projeto. Duas verdades, uma aplicada. O parâmetro `voice` do estilo
  (VS-04) **resolve** isso do lado do produto — mas a semântica de precedência
  (env de deployment vs config de projeto vs estilo) precisa decisão explícita.
- **`channel_profile_revisions` está vazio** porque não há canais: o mecanismo de versão
  existe e nunca foi exercitado. VS-01 exercita o mesmo padrão para o estilo.
- **`PIPER_VOICE` (env) sobrepõe a voz do spec** (`rich.py:55`) enquanto o ledger grava a do
  spec. Latente (env unset). Fecha em VS-04.
