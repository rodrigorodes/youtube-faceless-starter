# Isolamento do core — orientações e sugestões

**Origem:** instrução do operador (22/11/2026) — "toda ferramenta do core pode ser
conectada a diferentes tipos de fornecedor; seguir Clean Architecture e contrato com
a ferramenta é obrigação". Este documento fixa as regras **como o código já as
verifica** e lista o que eu sugiro mudar. Evidência `arquivo:linha` relativa a
`renderer/app/studio/`.

## 1. O que já está em vigor (e é verificado por CI, não por disciplina)

`tests/test_architecture.py` roda 4 guardas + 1 teste que prova que a guarda é
*load-bearing* (detecta violação de verdade):

| Guarda | Regra | Teste |
|---|---|---|
| Domínio | não importa `application`/`adapters`/`api`/`composition` nem I/O (`fastapi`, `psycopg`, `httpx`, `subprocess`, `os`, …) | `test_domain_has_no_outward_or_io_imports` |
| Aplicação | importa **só** domínio | `test_application_only_imports_domain` |
| API | não toca `adapters` nem `psycopg` | `test_api_does_not_touch_adapters_or_database` |
| Núcleo de render | nada de mídia (`PIL`, `numpy`, `cv2`, `ffmpeg`) nem SDK de fornecedor (`openai`, `anthropic`, `elevenlabs`, `fal_client`, `boto3`, `google`) | `test_render_core_has_no_media_or_provider_sdks` |

Documentado em `docs/10-arquitetura.md`: **`domain` ← `application` ← `adapters` / `api`;
só `composition.py` conhece adaptadores concretos.**

## 2. Orientações (regras que qualquer ferramenta nova deve seguir)

1. **Direção da dependência.** Sempre para dentro. `domain` não conhece ninguém;
   `application` conhece só `domain`; `adapters`/`api` conhecem todos; `composition`
   é o único que monta concreto.
2. **Contrato antes de adaptador.** Ferramenta nova nasce como `Protocol` em
   `application/ports.py`. O adaptador só existe depois do contrato.
3. **Fornecedor não vaza.** Nome de fornecedor (`pexels`, `piper`, `opencode`, `ffmpeg`)
   só pode aparecer em `adapters/`, `composition.py` e nos cartões de catálogo — nunca em
   `domain/` nem no fluxo de `application/`.
4. **Registro é dado, não condicional.** Fornecedor novo = `register()` + entrada em
   `_provider_implementations` com `ProviderKind`, `capabilities`, `CostEstimate`,
   `Availability` e `reason`. Zero `if provider == "x"` no fluxo.
5. **Seleção roteada e auditada.** `ProviderRouter` → `ProviderService.route` →
   `domain/provider.py`. Seleção por capacidade + perfil econômico, com auditoria e
   reavaliação explícita; **sem fallback silencioso**.
6. **Erro de domínio, não de fornecedor.** O núcleo levanta `InvalidTransition`,
   `RenderRefused`, `ProviderNotFound`; o adaptador traduz o erro do SDK. Nenhum
   `except requests.HTTPError` no núcleo.
7. **Configuração por injeção.** `Settings` é construída na composição e injetada;
   `os.environ` não aparece no núcleo.
8. **Contrato versionado.** Tipos públicos são gerados do código
   (`scripts/export_contracts.py`) e travados por snapshot
   (`tests/test_contracts_snapshot.py`). Mudança de contrato = mudança de snapshot.
9. **Teste de arquitetura é o gate.** Violação nova tem que deixar um teste vermelho;
   não se "resolve" com exceção no `violates()`.

## 3. Sugestões concretas (achados reais nesta árvore)

| # | Achado | Por que importa | Sugestão |
|---|---|---|---|
| S1 | `domain/panel.py:10` — `_KNOWN_FREE_PROVIDERS = {"placeholder","demo","piper","stock"}` | Domínio conhece **nomes** de fornecedor para decidir custo grátis | Mover a decisão para o `CostEstimate` do cartão (`domain/provider.py` já tem `free`). Domínio passa a olhar custo, não nome. |
| S2 | `application/render.py:354` — `model="ffmpeg"` fixo ao gravar o asset | Aplicação nomeia fornecedor de render | Usar `renderer.name` (a porta já expõe) ou o modelo do cartão. |
| S3 | `application/render_compiler.py:270,280,457` — emite `args` com `"ffmpeg"` | O artefato compilado é **específico de ffmpeg**; a porta `Renderer` fica nominal | O plano neutro é `RenderPlan` (domínio) — está certo. Mover `CompiledRender`/execução para `adapters/` e deixar `application/` só com o plano neutro. Senão "conectar outro renderer" exige reescrever o compilador. |
| S4 | `composition.py` — 912 linhas: `Settings` + registro de providers + wiring + health + recover | Raiz de composição grande demais para revisar | Dividir em `composition/settings.py`, `composition/providers.py`, `composition/wiring.py`, sem mudar comportamento. |
| S5 | `api/panel.py` — 4.199 linhas | Um módulo por área já começou (`panel_video_workspace.py`, `panel_settings.py`) | Continuar a divisão por área de tela; `panel.py` fica só com o que não tem dono. |
| S6 | Portas que ainda não existem para os itens autorizados | `MediaSearch`, `SemanticChecker`, `TenantContext` (ISO) | Declarar o `Protocol` **antes** do adaptador; é o que impede o item novo de virar exceção à regra. |
| S7 | A guarda só proíbe **imports**, não nomes | S1 e S2 passam pelo CI hoje | Adicionar teste que proíbe nome de fornecedor em `domain/`/`application/` (lista de strings), com allowlist explícita para o que é o próprio produto (YouTube). |
| S8 | Seleção de fornecedor **não** congelada no snapshot do run (achado W0B.3 ii) | Com N fornecedores, retry pode trocar de fornecedor e o resultado deixa de ser reproduzível | Congelar `provider`/`model` por capacidade no snapshot do run (migração aditiva) — já é o item 3 do quadro de achados abertos. |

## 4. Como isso se aplica aos oito itens autorizados

| Item | Porta/contrato | Adaptador | Onde **não** pode aparecer |
|---|---|---|---|
| Camadas/B-roll (VE-01/02) | `RenderPlan` já é o contrato; `OverlayLayer` entra como DTO de porta | compositor em `adapters/render_*` | `ffmpeg` no domínio/compilador puro |
| Troca de mídia (VE-03/EDIT-03) | `MediaSearch` + `MediaCandidate` (licença, proveniência, custo) | Pexels hoje; outros grátis/pagos depois | `pexels` no fluxo; licença obrigatória no contrato |
| QA semântico (VE-05) | `SemanticChecker` → `Verdict` (`VERIFIED`/`NOT_VERIFIED`/`FAILED`) | nenhum hoje (default `NOT_VERIFIED` honesto) | qualquer veredito inventado sem verificador |
| Pré-escuta/duração (EDIT-02) | `Voice` já existe; `duration_s` é dado de cena | Piper/adaptador de voz | medição de áudio no domínio |
| IDs de cena estáveis (W4.0) | identidade no domínio + repositório | Postgres | `idx` como identidade |
| Editar após aprovar (W4.2) | transição de estado no domínio | — | regra de reabertura na rota |
| Edição de cena (W4.1) | caso de uso `EditScriptScene` já existe | rota + CAS | lógica de edição na API |
| Isolamento por organização (ISO) | `TenantContext`/escopo por conta | Postgres (coluna + filtro) | `organization_id` vindo de query string |

## 5. Ordem sugerida de saneamento (barata, antes dos itens novos)

1. S7 (teste de nomes) — pega S1/S2 sozinho e impede regressão.
2. S1 e S2 — correções pequenas, cobertas pelo teste novo.
3. S6 — declarar as três portas antes de implementar os itens.
4. S8 — congelar seleção no snapshot (é pré-requisito de "N fornecedores").
5. S3, S4, S5 — refatorações estruturais, sem mudança de comportamento, quando houver folga.

Nenhuma dessas sugestões muda contrato público; todas são aditivas ou internas.

## 6. Referências de produto (fornecidas pelo operador, 22/11/2026)

- **https://fstudio.digital** — site do produto. Declara as integrações reais: Google,
  YouTube, Meta, Pexels, Pixabay, CapCut. Define o universo de fornecedores que as portas
  precisam aceitar: imagem/B-roll (Pexels, Pixabay), vídeo/edição (Google/CapCut), publicação
  (YouTube) e IA (Meta, Google). Nenhum pode aparecer como nome no domínio: cada um entra como
  adaptador de uma porta (`MediaSearch`, `Renderer`, `Uploader`, `TextGenerator`).
- **https://join.elevenlabs.io/** — fornecedor de voz (TTS, dublagem, clonagem). Confirma que a
  porta `Voice` precisa aceitar provedor remoto com custo por caractere/segundo, não só o Piper
  local. O contrato atual (`application/ports.py`, `Voice`) já é agnóstico: recebe texto e
  devolve áudio; o adaptador do ElevenLabs entra ao lado do Piper, sem mudar domínio.

Consequência prática: o catálogo de `ProviderKind` cresce por **capacidade**, não por
fornecedor — `image`, `video`, `voice`, `text`, `publish`, `search`, `qa`. Cada fornecedor novo
é uma linha no registro de composição, nunca um `if` no núcleo.

