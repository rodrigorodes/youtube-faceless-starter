# Validação da proposta contra o repositório real · 22/11/2026

**Base:** checkout `a2e6a39` (`youtube-faceless-starter`), proposta `faceless-visual-evolution 2` (revisão 3).
**Método:** leitura estática do código (`renderer/app/studio/`), conferência direta dos achados críticos, execução do teste lógico do protótipo e captura do protótipo em Chrome headless. Nenhum dado, serviço ou código de produção foi alterado.
**Escopo:** cumpre o "COV-01 / BASE-01" da proposta em primeira passada. Status usados: `IMPLEMENTADO`, `PARCIAL`, `AUSENTE`, `UI_ONLY` (existe só no protótipo).

## 1. Veredito

A proposta **segue a UX atual e cabe no core atual**, com ressalvas.

- **Visual e padrões:** o protótipo usa os mesmos tokens da casca real (`shell_v3_css.py`: 48 tokens; o protótipo tem 51 e nenhum token existe só na casca; acento violeta `#6a4bc4` idêntico). Não exige SPA nem novo design system.
- **Navegação:** 5 dos 7 itens globais existem. Dentro do vídeo há **1 das 8** áreas completa. Settings tem 6 itens de menu e um mapa interno de 7 chaves.
- **O que a proposta assume e o core não tem:** edição de cena por HTTP, `scene_id` estável, isolamento por organização, sessão/usuário real, pré-escuta de narração, troca de mídia por cena, N providers de voz e render, BYOK no caminho de execução.
- **O que o core já faz e a proposta trata como futuro:** aprovação presa ao render/checksum, gates de publicação no servidor, runs com pause/resume/retry/cancel e snapshot congelado, estado `UNCERTAIN` de operação paga, cache seletivo por cena.
- **Bloqueios reais antes de implementar:** guard de orçamento desligado no Compose; `scene_id` muda a cada versão do roteiro; não existe "reabrir" após aprovação (§4).

## 2. O protótipo, validado

| Verificação | Resultado | Evidência |
|---|---|---|
| Lógica (Node, DOM mínimo) | **52/52 aprovadas** (reexecutado) | `node evidence/test-prototype-logic.cjs` |
| Renderização em navegador real | **OK em 390, 768 e 1280 px**, sem overflow horizontal da página | `evidence/prototype-screens/` (390 medido em iframe, porque o Chrome headless do macOS não reduz a janela abaixo de 500 px) |
| Mesmos tokens da casca real | Sim | comparação de `--accent`, `--bg`, `--panel`, `--line`, `--muted` com `shell_v3_css.py` |
| Contraste, foco e teclado | **Não validado** | só há 8 `aria-label` e 6 regras `:focus-visible` no protótipo; a casca real já tem skip link, `:focus-visible`, `<dialog>` e contraste ≥4,5:1 documentado. Usar a casca real como referência, não o protótipo |
| Breakpoints | Protótipo: 760/820/1080/1100/1150. Casca real: **820 e 1080** | `shell_v3_css.py:515,521`. A meta "390/768/1280" é de **teste**, não de breakpoint; manter 820/1080 |
| Mobile | Menu rola na horizontal, conteúdo empilha. Igual ao comportamento da casca real (`shell_v3_css.py:512,521-535`); **não é sidebar colapsável** | captura 390 |

A afirmação do `DELIVERY-VALIDATION.md` de que Chromium estava bloqueado não vale mais neste ambiente: o Chrome headless funcionou.

## 3. Matriz de cobertura (FEATURE-COVERAGE-V3 × código real)

Colunas: **UI** = tela atual, **Core** = caso de uso/API/pipeline. Evidência `arquivo:linha` relativa a `renderer/app/studio/`.

| Funcionalidade | UI hoje | Core | Status | Evidência / lacuna |
|---|---|---|---|---|
| Início e continuar vídeo | sim | sim | IMPLEMENTADO | `api/panel_home.py`; cartão sem imagem (`shell_v3_css.py:241-246`) |
| Criar vídeo (tema, formato, duração, roteiro) | sim | sim | IMPLEMENTADO | `panel_new_video.py`; sem campo de duração-alvo nem roteiro pronto (hipótese: não conferi o formulário campo a campo) |
| Contexto de canal | sim | sim | PARCIAL | `active_channel.py`. **Páginas de vídeo/prévia/roteiro/execução passam `projects=[]`** (`panel.py:3985,4173`, `preview.py:158`, `panel_production.py:757`): seletor sem canais (leitura de código, não renderizei) |
| Listar/filtrar vídeos; publicado ≠ aprovado | sim | sim | **PARCIAL (bug)** | `panel_videos.py:68-69` põe `APPROVED` em "Publicados". Não há rótulo "Publicado" (`panel_home.py:17-24`) |
| Fontes e evidências | sim | sim | IMPLEMENTADO | `panel.py:3343-3405`; `application/editorial.py:240-263`; URL só de hosts da allowlist (default: 1 domínio, `composition.py:112`); `Claim` derivado por heurística e não persistido (`domain/claims.py:12-26`) |
| Fact-check | sim (no roteiro) | sim | IMPLEMENTADO | `panel.py:4002`; `fact_checks` com `script_version` |
| Roteiro por cena (ver) | sim | sim | IMPLEMENTADO | `panel.py:4012-4178`. Só contagem de cenas |
| Roteiro por cena (editar, add, remover, reordenar) | **não** | **parcial** | **PARCIAL / AUSENTE** | `EditScriptScene` existe (`application/longform.py:393`) mas **nenhuma rota o chama**. Add/remover/reordenar: ausente. Botão "Editar cenas" (`panel.py:4073`) aponta para uma página sem editor |
| **ID de cena estável** | — | **não** | **AUSENTE** | `editorial_repo.py:77-81`: a cada versão `DELETE` + `INSERT` com `uuid4` novo; `asset_id` por cena se perde. Quebra deep-link, mídia por cena e cache seletivo entre versões |
| Voz, provider, velocidade | só leitura | parcial | PARCIAL | 1 provider de voz (`piper`). A "Voz do narrador" do perfil (`channel_profiles.voice`, `panel_channels.py:583-588`) **é ignorada**: a voz sai de `style.voice.model` ou do projeto (`composition.py:247-260`). Velocidade: sem campo |
| Pré-escuta / duração real | não | parcial | **AUSENTE** | sem rota de áudio; `scenes.duration_s` nunca é gravada; duração medida só no render (`render.py:52-57`) |
| Regeneração de voz por cena | não | parcial | PARCIAL | reaproveita WAV por fingerprint (`render.py:260-271`); sem comando por cena |
| Storyboard e intenção visual | só na prévia | sim | PARCIAL | `preview.py:81`; `image_prompt` existe por cena; sem UI de edição |
| Mídia: trocar, candidatos, upload | não | não | **AUSENTE** | `link_scene` só em STORYBOARDED e só em cena sem asset (`media.py:65,75`); sem upload; stock só Pexels (nenhuma ocorrência de Pixabay) |
| Licença e proveniência | sim (créditos na prévia) | sim | IMPLEMENTADO | `assets.license` obrigatória (`media.py:93-104`) |
| Camadas / B-roll | não | não | AUSENTE | é o escopo VE-01/02 |
| Legendas, tipografia, música | sim (biblioteca e patch) | sim | PARCIAL | consumidos: motion, bpm/seed, legenda (tamanho/posição/cores), cor do selo, modelo de voz (`render_plan_ffmpeg.py:84-131,434,585`). **Não existem:** volume da música (fixo 0,40, `render_compiler.py:54`), família da fonte (fixa), thumbnail configurável |
| Resolução, FPS, transição, motion | parcial | parcial | PARCIAL | resolução e FPS fixos (`render.py:12`, 25 fps). **Transição só declarada**: o compilador não lê `Shot.transition` (`visual_style.py:502-506`; a própria UI avisa, `channel_style_page.py:34-35`) |
| QA técnico | sim (na prévia) | sim | IMPLEMENTADO | `preview.py:69-80`; bloqueante |
| QA semântico | não | não | AUSENTE | VE-05 |
| Aprovar versão (render/checksum) | sim | **sim** | IMPLEMENTADO | `publish_repo.py:41-63`: aprovação grava `render_id`, `media_checksum`, QA e `idempotency_key` na mesma transação |
| Título, descrição, privacidade, agendamento | sim (na prévia) | sim | IMPLEMENTADO | `preview.py:91-108`; `public` exige confirmação separada (`publication_policy.py`) |
| Gates de publicação no servidor | — | sim | IMPLEMENTADO | `publication_execution.py:189-249`; `verify_publication_gate`. **Fail-open** quando o canal não tem destino YouTube (`:228-238`) |
| Thumbnail | automática | sim | PARCIAL | `adapters/thumbnail.py` (1ª cena); sem briefing nem upload |
| Histórico / revisões / restaurar | só roteiro | parcial | PARCIAL | versão do roteiro inteiro (`scripts`), sem versão por cena; sem "restaurar" |
| **Editar após aprovar** | — | **não** | **AUSENTE** | `states.py:9`: `APPROVED` só vai a `PUBLISHED`; não há "reabrir" (§4, D-EDIT). Os cenários A06/A12/A18/A22 dependem disso |
| Pause / resume / retry / cancel | sim | sim | IMPLEMENTADO | `routes.py:1780-1826`; `resume` com `expected_state` |
| Snapshot congelado por run | sim | sim | IMPLEMENTADO | `0039`; ressalva: `provider_profile` não entra no snapshot e sai sempre `BALANCED` (`composition.py:213-215`) |
| Retomada após fechar o navegador | sim | sim | IMPLEMENTADO (no processo) | worker em `ThreadPoolExecutor` dentro da API; `recover_in_flight` no boot |
| Custos e limites | sim (por canal) | **parcial** | **PARCIAL (risco)** | ver §4-R1 |
| Tendências | sim | sim (dados reais) | IMPLEMENTADO | YouTube Data API (`youtube_trends.py`); **"Criar vídeo deste tema" navega sem `project_id`** (`panel_trends.py:164-170`; hipótese de troca silenciosa de canal) |
| Desempenho | sim | sim (real ou `not_yet_available`) | IMPLEMENTADO | `youtube_analytics.py`; nunca fabrica zero |
| Biblioteca (estilos, vozes, mídias) | só estilos, dentro de Settings | sim (estilos) | PARCIAL | `panel_styles.py`. Não há página `/biblioteca`. Vozes: 1 provider. Mídias: sem biblioteca |
| Perfil, público, pilares | sim | sim | IMPLEMENTADO | consumidos no prompt (`editorial.py:99-153`) |
| Narrativa, duração padrão, CTA | **não** | **sim** | PARCIAL | consumidos pelo prompt, **sem UI** (só `PATCH /channels/{id}`) |
| `strategy`, `audio`, `thumbnail`, `visual_identity` | parcial | **não** | **UI_ONLY** | persistidos e **não consumidos**; a UI diz que a identidade visual é "aplicada a thumbnail, cartelas e legendas" (`panel_channels.py:630`) |
| Estilos compartilhados, override de canal | sim | sim | IMPLEMENTADO | `visual_styles`, `style_patch`, `panel_channel_style.py` |
| Override de vídeo (patch) | **não** | repo sim | PARCIAL | `set_video_style_patch` existe (`repo.py:203`) sem rota nem chamador |
| Providers por tarefa / fallback | só leitura | sim | PARCIAL | `PUT /projects/{id}/config` sem tela; botão "Reordenar fallback" desabilitado (`panel_channels.py:765`); com perfil, **o provider executado pode diferir do exibido** (`composition.py:310-336`) |
| N providers por capacidade | — | texto 2, imagem 4, voz **1**, render **1** | PARCIAL | `composition.py:367-398` |
| Conexões, YouTube/Google | sim | sim | IMPLEMENTADO | `0035`; tokens só no cofre de arquivos; revogação (`connections.py:335-368`) |
| BYOK | sim (cofre/auditoria) | **fora da execução** | **PARCIAL** | a própria UI avisa (`panel_channels.py:1074-1081`); providers usam env do servidor |
| Equipe e papéis | sim | **só na tela de Equipe** | PARCIAL | papéis owner/editor/reviewer/viewer; `require()` só nas mutações de Equipe. `CREATE_VIDEO`, `EDIT_VIDEO`, `APPROVE_*`, `PUBLISH` declaradas e **não aplicadas** |
| Isolamento por organização | — | **não** | **AUSENTE** | `organization_id` não aparece em nenhum repo de vídeo/asset/render/produção; `organization_id` vem do corpo/query; um único usuário Basic |
| Avançado / saúde / config efetiva | sim (leitura) | parcial | PARCIAL | sem logs/eventos nem diff de snapshot por run; `/health` devolve `ffmpeg: True` fixo (`main.py:34-36`) |
| n8n / API / RenderPlan | parcial | sim | PARCIAL | a prévia diz que o n8n publica (`preview.py:41`) e `routes.py:1656` diz que o servidor publica: **caminho vigente não confirmado** |

## 4. Riscos e lacunas que a proposta não prevê (ou prevê tarde)

| # | Achado | Impacto | Onde a proposta cobre |
|---|---|---|---|
| R1 | **Guard de orçamento desligado no Compose.** O serviço `renderer` tem `environment:` explícito sem `STUDIO_BUDGET_GUARD`; `docker compose config` não o define. Sem guard só valem os tetos **globais** do env; limites hard/soft **por canal** da UI não protegem | Controles de custo da tela "Orçamento do canal" dão falsa segurança | BASE-02 (correto, mas é pré-requisito de tudo que gera mídia paga) |
| R2 | **`scene_id` instável** entre versões do roteiro (`editorial_repo.py:77-81`) | EDIT-01 não é possível sem isso; o cache seletivo por `scene_id` não reaproveita entre versões (hipótese) | EDIT-01 cita "IDs estáveis", sem dizer que o repositório hoje os recria |
| R3 | **Não há reabrir após aprovação** (`states.py:9`) | A06, A12, A18, A22 | DECISIONS fala em "nova revisão", sem a transição |
| R4 | **UI declara efeitos que o core não tem** ("Voz do narrador", "Identidade visual aplicada a thumbnail/cartelas/legendas", transição) | viola a regra da própria proposta ("não apresentar como aplicado") | SET-02 trata, mas a violação já existe |
| R5 | **`APPROVED` aparece em "Publicados"** (`panel_videos.py:68-69`) | A21 | UX-01 (correto) |
| R6 | **Páginas de vídeo sem canal no shell** | UX-01 "canal consistente" | UX-01 |
| R7 | **RBAC e org não aplicados fora de Equipe**; auth = 1 usuário Basic; `organization_id` do cliente | só importa com 2+ usuários/clientes | ISO-01/02 (correto, bloqueante só para multi-cliente) |
| R8 | **Gate de autorização do canal YouTube é fail-open** sem destino configurado | publicação sem validar destino | PUB-01 |
| R9 | **Snapshot do run não congela o perfil de provider** | retry pode rotear diferente do run original | BASE/SET-03 |
| R10 | **Banco vazio hoje** (limpeza autorizada em 22/11): migração/backfill de DECISIONS VE-D2 só é testável com dados sintéticos | ensaio de migração sem dado real | VE-D2 (manter aditivo) |
| R11 | **Dependência de ordem** entre testes (`test_port_contracts`) e `renderplan.schema.json` defasado | baseline vermelho antes de começar | BASE-01 |

## 5. Divergências do texto da proposta

1. `PROJECT-V3.md` §3 lista "Biblioteca" e "Tendências e ideias" no menu global; o menu real tem "Tendências" e "Desempenho" e **não tem Biblioteca** (`shell_v3.py:408-412`). "Ideias" existe só como API (`routes.py:1141,1152`).
2. `UX-SPEC.md` "Navegação do vídeo": o vídeo real é **uma página única de cartões**, sem abas; roteiro, prévia e execução são páginas separadas.
3. `DOMAIN-CONTRACTS.md` cadeia "conta → canal → vídeo → cena": a precedência real é **motor < estilo < patch do canal < patch do vídeo** (`effective_config.py:510-595`); não há camada de conta nem de cena. O próprio documento manda mapear antes de alterar; este é o mapa.
4. `PROJECT-V3.md` §5 "Produção e orçamento: providers por tarefa, retry/fallback": a tela é **somente leitura**; retry/fallback de chamada não existe (a cadeia `fallbacks` não é usada na execução, hipótese `composition.py:325`).
5. `BACKLOG-V2.md` EDIT-02 "alinhamento por palavra": **ausente** e fora de escopo (`domain/render.py:86`).
6. `START-HERE.md` cita `PLAN-VE00-VE06-AS-RECEIVED.md` como histórico; a versão do plano **revisada** (D1–D7, golden, VE-01) está em `phases/VE-01-render-overlay.md` e em `evidence/golden/`.
7. `RULES.md` (pacote) item 4 aponta para DECISIONS; o `RULES.md` antigo do backlog exigia "feature flag", já removido por VE-D6.

## 6. Limitações desta validação
- Leitura estática; testes do produto **não** foram executados para esta matriz. A suíte completa no container (351 s) deu 5 falhas e 2888 passes, descritas em `evidence/ve-00-closure.md` quando for escrito.
- Não renderizei o painel real (a aplicação estava parada); os pontos R5/R6 vêm do código e devem ser confirmados no navegador na primeira atividade da UX-01.
- Hipóteses marcadas no texto: troca silenciosa de canal em Tendências, reuso de cache entre versões de roteiro, caminho vigente de publicação (n8n × servidor).
