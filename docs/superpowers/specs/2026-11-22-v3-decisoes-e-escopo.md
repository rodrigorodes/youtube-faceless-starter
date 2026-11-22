# Mockup V3 → plataforma: decisões e escopo de implementação

Data: 2026-11-22. Fonte visual: `docs/backlogs/faceless-visual-evolution 2/prototype-v4-v3/`.
Base factual: `2026-11-22-persistencia-prototipo-vs-plataforma.md` (lacunas) e `2026-11-22-benchmark-ux-jornadas-v2.md` (prioridades de UX).

## 1. Decisões

| # | Pergunta | Decisão | Origem |
|---|---|---|---|
| 1 | Controles sem lastro no motor | **Implementar no motor**, em fases. Até cada controle existir, a tela real não o exibe (ou o exibe desabilitado, rotulado "em breve"). | Dito pelo usuário |
| 2 | "Estilo" = composição ou direção de arte? | **Composição** (`visual_styles.params`, o que o banco e o motor já tratam). A direção de arte é texto livre no `visual_identity` do canal, que já existe. Nenhuma entidade nova. | **Escolha minha** (usuário não soube responder): é a opção sem migração e sem promessa nova. Reversível. |
| 3 | Onde mora o B-roll | **Metadado da cena** (`scenes.broll_enabled`, `scenes.broll_note`). Só vira mídia no vídeo na fase do motor; antes disso a tela diz que é referência para o editor. | **Escolha minha** (usuário não soube responder): é por cena no mockup, e `scenes` já tem revisões (0046). Reversível. |
| 4 | Piloto/Diretor | **Preferência pré-configurada no canal** (`default_mode`) **e** escolha em cada vídeo (`videos.production_mode`, registrada). | Dito pelo usuário |
| 5 | Providers | **Configuração da plataforma.** O usuário só informa token (BYOK, já existente) ou escolhe um provider gratuito. Sem "Adicionar provider" livre. | Dito pelo usuário |

Consequências de 5: o catálogo continua vindo de código (`domain/provider.py`, `ProviderCard`). A tela precisa saber, por provider, se exige credencial. Hoje `ProviderCard` expõe custo (`FREE`/`ESTIMATE`/`UNKNOWN`), mas **não** diz se precisa de token — isso é verificado no plano 4 antes de implementar.

## 2. Planos (um por subsistema)

Cada plano entrega software testável sozinho. A ordem importa: 1 destrava 3; 2 é independente; 4 é independente.

| Plano | Escopo | Estado |
|---|---|---|
| **1. Fundação do canal e do vídeo** | preferências do canal, modo por vídeo, criação de canal transacional e idempotente | **detalhado:** `plans/2026-11-22-v3-plano-1-fundacao-canal-video.md` |
| 2. Motor de composição | legenda (posição topo/meio/base, fonte, estilo), trilha/volume/ducking, transição, FPS, B-roll | esboço abaixo; detalhar após ler o executor de render |
| 3. Telas | home com ideia/roteiro, criação de canal em tela única, workspace com 5 áreas, desfazer, histórico de voz, agendamento | esboço abaixo; depende do plano 1 |
| 4. Providers | cartão diz se exige token ou é gratuito; fluxo "só o que falta"; remover cadastro livre | esboço abaixo |

### Plano 2 — esboço (ordem por valor/risco)

Fatos de partida: o motor aplica `caption.font_size`/`caption.bottom`, `palette`, `motion`, `music.bpm/seed`, `voice.model`; legenda é desenhada por PIL em `adapters/render_plan_ffmpeg.py` (layout por formato); `transition` é só carregada; FPS é a constante 25 em `domain/render.py`.

1. Posição da legenda topo/meio/base: derivável de `caption.bottom` no layout, sem novo esquema. Menor risco.
2. Fonte e estilo da legenda (caixa/simples/destaque por palavra): nova chave em `caption`, exige fonte embarcada e licença.
3. Transição `fade` aplicada de verdade (`LOADED_ONLY_GROUPS` → `APPLIED_GROUPS`); "deslizar" só se houver demanda.
4. Música: seleção de faixa, volume, ducking. Exige catálogo de faixas e licenças.
5. FPS configurável: toca `Timebase`, duração por cena e cache de render; maior risco, por último. Padrão continua 25 até decisão.
6. B-roll como segunda camada de mídia por cena.

Regra: cada item muda `APPLIED_GROUPS` e o hash do plano de render; testes de golden (`tests/golden`) precisam continuar estáveis para vídeos sem o novo parâmetro.

### Plano 3 — esboço

Reaproveita o que já está em `panel_new_video.py` (tela única, não commitado). Itens: entrada "ideia/roteiro" (roteiro vira cenas sem reescrever), herança de `target_duration_s`, `default_mode` do canal, criação de canal em tela única chamando o caso de uso do plano 1, 5 áreas no workspace, desfazer/refazer em cenas (usa `scene_revisions`), histórico de voz, diálogo de impacto antes de renderizar com custo `null` → "estimativa indisponível", agendamento com fuso.

### Plano 4 — esboço

Primeiro passo de investigação: ver como cada adaptador decide disponibilidade (`composition/providers.py`, `provider_probes.py`) e derivar `requires_credential`. Depois: API, tela "só o que falta", remoção do cadastro livre, teste de conexão contextual.

## 3. Fora de escopo agora

Biblioteca de vozes/músicas/modelos de roteiro em tabelas (P2), alvo de duração por vídeo, `DELETE` de fonte, rótulo de fonte. Ficam para depois dos planos 1–4.

## 4. Limites desta análise

Decisões 2 e 3 são minhas, não suas; revise-as. Não executei nenhum desses itens contra um banco ou render reais. O esboço dos planos 2–4 não substitui o detalhamento por tarefa.
