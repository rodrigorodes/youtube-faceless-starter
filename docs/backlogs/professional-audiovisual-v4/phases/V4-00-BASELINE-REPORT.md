# V4-00 — Relatório Consolidado de Baseline e Estabilidade

**Iniciativa:** Professional Audiovisual V4  
**Fase:** V4-00 — Baseline & Stability  
**Branch de Execução:** `feat/v4-00-homologation-fixes`  
**Commit Base:** [`f35976d`](https://github.com/rodrigorodes/youtube-faceless-starter/commit/f35976d)  
**Data:** 25 de Novembro de 2026  
**Auditor Responsável:** Engenheiro de Software Sênior (Antigravity)  
**Ambiente Canônico:** Container Docker oficial `faceless-renderer-pytest:test` (Python 3.12.16, PostgreSQL 16-alpine em `tmpfs`, FFmpeg 7.1.5 com `--enable-libass`, Piper-TTS 1.8.0)

---

## 1. Etapa 1 — Gate de Transição da Foundation

Para garantir que a V4 parta de um alicerce estável, seguro e reproduzível, foi realizada uma auditoria técnica e objetiva das evidências das fases da Foundation:

| Fase | Foco da Auditoria | Evidência Rastreável | Estado Real Verificado | Bloqueio Crítico? |
|---|---|---|---|:---:|
| **FS-01** | Regressão canônica e suíte verde | `RUN-12` e `RUN-13` no container oficial | Suíte canônica aprovada em ambiente isolado. Teste Piper TTS calibrado e estável (5/5 aprovadas). Zero falhas funcionais. | **Não (PASS)** |
| **FS-02** | Isolamento de banco, volumes e redes | `test-container.sh`, `tests/test_e2e_isolation.py`, `tests/test_v4_production_flow_pilot.py`, `tests/test_v4_studio_real_flow_pilot.py` | Postgres 16 em `tmpfs` com rede descartável `faceless-test-net-$$`. Sem portas no host (5432/8000 livres). Prova de descartabilidade `/proof/proof`. Relatórios graváveis isolados em `storage/test-reports`. Jornada completa E2E sem browser comprovada em `tests/test_v4_studio_real_flow_pilot.py`. Skips de Node.js (17) e Playwright (3) auditados formalmente (ver detalhamento de impedimento técnico abaixo). | **Não (PASS / Gate E2E-Browser CONDICIONAL)** |
| **FS-04** | Configuração, flags e controle de custos | `tests/test_compose_env.py`, `tests/test_publication_execution.py` | `STUDIO_PUBLICATION_ENABLED=0` validado no cenário PUB-13 (bloqueia token, claim e upload). Orçamento de API em **$0.00** garantido por `BudgetGuard`. | **Não (PASS)** |
| **FS-05** | Readiness e liveness resilientes | `renderer/app/main.py`, `test_main_boot.py` | Endpoint `/ready` responde 200 quando saudável e 503 quando banco ou FFmpeg falham. Falha em serviços externos não derruba liveness. | **Não (PASS)** |
| **FS-06** | Limites de concorrência, admissão e recuperação | `renderer/app/studio/composition/wiring.py`, `test_production_capacity.py` | Concorrência governada por `render_concurrency` e `max_active_runs`. `CapacityExceeded` sem descarte de runs. Fencing CAS em `production.py`. | **Não (PASS)** |
| **FS-07** | Baseline técnico audiovisual | `tests/test_render_golden.py`, `render_baseline.json` | Determinismo em `golden_render.py` (digest estável, MP4 byte-identical). Suporte longform até 480s via `MAX_DURATION_SECONDS`. | **Não (PASS)** |
| **FS-08** | Mapeamento de dependências modulares | `FS-08-dependency-map.md` | FS-08.01 concluído. FS-08.02 a FS-08.07 formalmente deferidos para as fases consumidoras (V4 e Finder) sem gerar dívida técnica ativa. | **Não (PASS)** |

### Detalhamento do Impedimento Técnico (Node.js e Playwright)
- **Causa Raiz:** O ambiente canônico oficial do backend e renderizador (`faceless-renderer-pytest:test`) é uma imagem Debian slim otimizada exclusivamente para Python 3.12, PostgreSQL e FFmpeg/libass, sem conter o runtime Node.js nem os binários pesados de navegadores headless (Chromium, Firefox, WebKit). Da mesma forma, o host operacional de execução não possui Node nem browsers de teste instalados.
- **Risco Registrado:** A suíte E2E baseada em navegador (`tests/e2e_full` e `tests/e2e_ux`) não pode ser executada no contêiner slim sem a introdução de uma imagem multi-runtime heterogênea ou instalação externa. Conforme as regras do projeto (*"Não introduzir infraestrutura corporativa ou CI/CD"* e *"Caso exista impedimento técnico, registre o risco e mantenha o gate correspondente pendente"*), o gate de UI com navegador real permanece formalmente **CONDICIONAL / PENDENTE**, enquanto toda a jornada funcional da aplicação foi 100% validada e aprovada pelo fluxo nativo da API sem navegador (`tests/test_v4_studio_real_flow_pilot.py`).

---

## 2. Etapa 2 — Execução das Atividades V4-00.01 a V4-00.10

### V4-00.01 — Mapeamento de Módulos e Contratos Existentes
O monólito modular é composto por cinco módulos centrais mapeados no baseline:
1. `renderer/app/studio/api/routes.py`: 140 rotas estruturadas (canais, vídeos, storyboard, render, publicação, conexões, analytics).
2. `renderer/app/studio/application/production.py`: Coordenação assíncrona (`ProductionCoordinator`), DAG de estágios, leases com heartbeat, CAS e admissão de capacidade.
3. `renderer/app/studio/composition/wiring.py`: Raiz única de injeção de dependências (`Studio.create()`), resolução estática de provedores e configuração imutável congelada por execução.
4. `renderer/app/studio/application/ports.py`: Contratos abstratos (`VideoRepository`, `TextModel`, `Voice`, `Renderer`, `RenderSpec`, `ChannelRepository`).
5. `renderer/app/studio/application/render_compiler.py`: Compilador lógico de plano estruturado (`RenderPlan` -> `PlanStructure` -> `CompiledRender`).
6. `renderer/app/studio/adapters/render_plan_ffmpeg.py`: `PlanFfmpegRenderer` — o único motor canônico de renderização FFmpeg do sistema.

### V4-00.02 — Validação de Dependências Reais no Container
- **Python:** 3.12.16 (Debian Bookworm slim).
- **PostgreSQL:** 16-alpine (efêmero em tmpfs na suíte de testes; instância dedicada em DEV).
- **FFmpeg:** `7.1.5-0+deb13u1` com `--enable-libass` (queima de legendas ASS compilada nativamente).
- **Piper-TTS:** `1.8.0` (`piper-tts==1.8.0`) com modelo ONNX nativo `pt_BR-faber-medium.onnx` em `/opt/voices/`.
- **Pillow:** `11.1.0` (geração de overlays estáticos de cena, disclosure e cards visuais).

### V4-00.03 — Validação de Regressão, Fluxo Real e Testes Pequenos
- **Regressão Canônica Completa (RUN-13):** Executada sobre o checkout com o Core atualizado no container oficial `faceless-renderer-pytest:test`, garantindo zero regressões.
- **Validação de Métricas Unitárias:** [`tests/test_v4_baseline_metrics.py`](file:///Users/rodrigomendes/youtube-faceless-starter/tests/test_v4_baseline_metrics.py) (11 testes) cobrindo validadores de duração, critérios de QA com falha fechada para métricas ausentes (`REQUIRED_QA_METRICS`), medições de CPU/RAM pai e filhos, e hashing SHA-256.
- **Regressão de Ticks e Legendas:** [`tests/test_v4_subtitles_ticks_regression.py`](file:///Users/rodrigomendes/youtube-faceless-starter/tests/test_v4_subtitles_ticks_regression.py) (178 testes) comprovando continuidade exata de float em `make_cues`, não sobreposição de ticks em `_subtitle_cues`, respeito aos limites de narração/cena e validação da timeline de 18 cenas do piloto.
- **Integração do Coordenador com Handlers Simulados:** [`tests/test_v4_production_flow_pilot.py`](file:///Users/rodrigomendes/youtube-faceless-starter/tests/test_v4_production_flow_pilot.py) (1 teste) comprovando a máquina de estados, transições, leasing/fencing e persistência do `RenderPlan`.
- **Jornada pelo Fluxo Real do Studio:** [`tests/test_v4_studio_real_flow_pilot.py`](file:///Users/rodrigomendes/youtube-faceless-starter/tests/test_v4_studio_real_flow_pilot.py) (1 teste) comprovando a execução real da aplicação ponta a ponta: `Studio` real com FastAPI, banco PostgreSQL descartável, provedores locais gratuitos (`demo`, `placeholder`, `piper`), renderização real com `PlanFfmpegRenderer` (FFmpeg nativo), avaliação técnica real com `FfmpegQualityEvaluator` (EBU R128), persistência de `qa_report` aprovado em `video.qa_report`, gate de aprovação humana e bloqueio estrito de publicação externa por `STUDIO_PUBLICATION_ENABLED=0`.
- **Resultado dos Módulos V4 no Container Oficial:** `191 passed in 10.45s` (exit code 0).

---

### V4-00.04 & V4-00.05 — Geração do Baseline Audiovisual e Benchmark Técnico

Foram produzidos no contêiner oficial, via [`scripts/render_v4_baseline.py`](file:///Users/rodrigomendes/youtube-faceless-starter/scripts/render_v4_baseline.py), dois vídeos de referência reais com métricas mecânicas extraídas via `ffprobe` e `FfmpegQa`:

#### 1. Fixture Técnica Real (60–90s)
- **Arquivo Gerado:** `storage/output/v4_fixture_tecnica_60s.mp4`
- **Formato:** 1920x1080 (16:9 widescreen)
- **Duração Medida:** **63,52 segundos** (4 cenas calibradas)
- **Codecs:** Vídeo H.264 (avc1, 25.0 fps, 1.588 frames) | Áudio AAC (Stereo, 96 kHz)
- **Conformidade EBU R128:**
  - Loudness Integrado: **-16,3 LUFS** (alvo -16.0 ± 1.5 LUFS atingido)
  - Loudness da Narração: **-16,2 LUFS**
  - True Peak: **-1,6 dBTP** (sem clipping)
  - Silence Ratio: **0,00%** | Narration Silence Ratio: **10,17%** | Black Ratio: **0,00%**
  - Frozen Ratio: **0,5183** (esperado para cards estáticos baseline AS-IS)
- **Tamanho do Arquivo:** 9.167.665 bytes (~8,74 MB)
- **Hash SHA-256:** `904eb8c9b801251ba222cd8f93d180c74c98900c0f1f03cd35399ac656516c04`
- **Tempos de Processamento:** Síntese Piper TTS 6,96s | Renderização FFmpeg 46,92s | Análise QA 11,96s | Total: 65,83s
- **Consumo de Disco:** Saída: 8,74 MB | Diretório Temporário de Trabalho: 25,08 MB

#### 2. Piloto Audiovisual Original (5–8 min / 300–480s)
- **Tema:** *"A História da Computação: Da Mecânica aos Cérebros de Silício"* (Roteiro histórico factual ampliado com 18 cenas documentais completas)
- **Arquivo Gerado:** `storage/output/v4_piloto_audiovisual_5min.mp4`
- **Formato:** 1920x1080 (16:9 widescreen)
- **Duração Medida:** **345,60 segundos** (5 minutos e 45,6 segundos — **estritamente em conformidade com o aceite de 300–480s**)
- **Codecs:** Vídeo H.264 (avc1, 25.0 fps, 8.640 frames) | Áudio AAC (Stereo, 96 kHz)
- **Conformidade EBU R128:**
  - Loudness Integrado: **-15,5 LUFS** (alvo -16.0 ± 1.5 LUFS atingido)
  - Loudness da Narração: **-16,2 LUFS**
  - True Peak: **-1,5 dBTP** (sem clipping ou distorção)
  - Silence Ratio: **0,00%** | Narration Silence Ratio: **9,53%** | Black Ratio: **0,00%**
  - Frozen Ratio: **0,4899** (comprovando consistência e ausência de paralisia total)
- **Tamanho do Arquivo:** 47.798.249 bytes (~45,58 MB)
- **Hash SHA-256:** `9b20e2e749127ccd6ce6aeb4f1d5cf029d31840b338b807aa0aba71b45a1ba6f`
- **Tempos de Processamento:** Síntese Piper TTS (18 cenas): 59,63s | Renderização FFmpeg: 421,95s | Análise QA: 47,79s | Total: 529,37s

#### 3. Consumo de Recursos Globais e Estrutura de Memória RAM
- **Consumo de Disco Temporário:** 134,33 MB (limpo automaticamente ao final).
- **CPU Total (Processo Pai + Filhos do FFmpeg via `RUSAGE_CHILDREN`):** **1.394,566s** (User: 1.258,931s, System: 135,635s).
- **Consumo de Memória RAM Desacoplado:**
  - **Pico RSS do Processo Pai (Python):** **1.348,86 MB**
  - **Pico RSS dos Subprocessos Filhos (FFmpeg/Piper):** **1.632,58 MB**
  - **Limite Superior Teórico Combinado (`rss_sum_upper_bound_mb`):** **2.981,44 MB** (~2,91 GB)
  - **Nota de Limitação do Kernel:** O kernel Linux reporta via `getrusage` o `ru_maxrss` independente do processo pai e de todos os filhos terminados. O pico simultâneo agregado exato não é medido sem amostragem temporal contínua; a soma de 2.981,44 MB representa o limite superior teórico caso ambos atinjam o pico simultaneamente.
- **Custo de API Externa:** **$0.00** (Zero chamadas pagas).
- **Custo Computacional:** Processamento estritamente local em CPU.

#### 4. Preservação Histórica de Execuções
Cada execução do benchmark gera um subdiretório exclusivo versionado em `storage/output/runs/run_<timestamp>/`, preservando de forma imutável:
- O vídeo da fixture técnica MP4
- O vídeo do piloto audiovisual MP4
- As amostras de quadros extraídas PNG
- O relatório sanitizado JSON de métricas e hashes
Cópia canônica dos arquivos mais recentes permanece disponível na raiz de `storage/output/` para visualização direta.

#### 5. Evidência Visual — Amostragem de Quadros do Piloto
Amostras de quadros extraídas via `scripts/render_v4_baseline.py` para inspeção visual de layout e legendas:
- Frame 1 (17s): `storage/output/frames_pilot_v4/frame_01_17s.png` (O Ábaco)
- Frame 2 (69s): `storage/output/frames_pilot_v4/frame_02_69s.png` (Tear de Jacquard)
- Frame 3 (138s): `storage/output/frames_pilot_v4/frame_03_138s.png` (Turing e Enigma)
- Frame 4 (207s): `storage/output/frames_pilot_v4/frame_04_207s.png` (Transistor e Silício)
- Frame 5 (276s): `storage/output/frames_pilot_v4/frame_05_276s.png` (A Internet Global)
- Frame 6 (328s): `storage/output/frames_pilot_v4/frame_06_328s.png` (Fronteiras da IA)

---

### V4-00.06 — Avaliação Humana e Comparação AS-IS vs TO-BE

Os vídeos gerados estão disponíveis no repositório local para inspeção e avaliação humana do operador:
- Fixture Técnica: [`storage/output/v4_fixture_tecnica_60s.mp4`](file:///Users/rodrigomendes/youtube-faceless-starter/storage/output/v4_fixture_tecnica_60s.mp4)
- Piloto Audiovisual: [`storage/output/v4_piloto_audiovisual_5min.mp4`](file:///Users/rodrigomendes/youtube-faceless-starter/storage/output/v4_piloto_audiovisual_5min.mp4)

A análise crítica da qualidade evidencia os seguintes gaps entre o pipeline atual e a meta profissional V4.1:

| Dimensão | Estado Atual (AS-IS no Baseline V4-00) | Meta Profissional (TO-BE na V4.1) | Impacto no Telespectador |
|---|---|---|---|
| **Voz & Entonação** | Voz única offline (Piper `pt_BR-faber-medium`). Dito claro e calibrado, mas tom uniforme, pausas mecânicas e sem variação emocional. | Vozes neurais com inflexão dramática, modulação de ênfase por pontuação, respiração orgânica e suporte a múltiplos timbres. | Redução drástica da fadiga auditiva em documentários longos (>3 min). |
| **Sonoplastia & Trilha** | Trilha sonora CC0 única em loop com ducking estático simples. Ausência de efeitos sonoros (SFX) ou ambiência. | Multitrack com trilha dinâmica que varia por ato narrativo, SFX de transição e pontuação rítmica de cortes. | Aumento acentuado na imersão e retenção média de visualização. |
| **Composição Visual** | 1 imagem por cena com zoompan linear e overlays estáticos em texto. | Camadas múltiplas (B-roll em vídeo, gráficos de dados, motion de títulos cinéticos e transições estilizadas). | Ritmo visual contemporâneo similar a canais documentais de alto padrão. |
| **Pesquisa & Roteiro** | Factual básico baseado em 1 fonte Wikipédia com extração léxica. | Pesquisa aprofundada multiconteúdo (claims cruzadas, fatos curiosos e estrutura de retenção em 3 atos). | Maior autoridade factual e engajamento da narrativa. |

---

### V4-00.07 — Mapeamento de Capabilities e Limitações do FFmpeg 7.1

- **Capabilities Confirmadas:**
  - `libass` nativo habilitado para renderização de legendas ricas (fontes, cores, sombras e margens).
  - Filtro `scale` e `zoompan` para animação suave de imagens paradas em 25 fps.
  - Filtros de áudio `afade` (fade in/out gradual) e `amix` com ducking para balanceamento de fala.
  - Normalização automática via `loudnorm` assegurando padrão EBU R128 (-16 LUFS integrado).
- **Limitações Identificadas:**
  - O pipeline atual compila cada cena em um MP4 temporário individual (`scene_xxx.mp4`) antes do `concat demuxer`. Isso dobra o tempo de escrita em disco.
  - Não há suporte a aceleração por hardware GPU no contêiner Linux slim (toda a codificação depende da CPU x264/ultrafast).
  - O suporte a overlays é limitado estruturalmente a 1 imagem sobreposta por cena (`MAX_OVERLAYS_PER_SCENE=1`).

---

### V4-00.08 — Mapeamento de Gaps Arquiteturais e Proposta para V4-01

Para habilitar a evolução para a **V4-01 (Provider Extensibility)** sem violar a Clean Architecture:

1. **Expansão de Capacidades no Provider Registry (`composition/providers.py`):**
   - Introduzir capabilities explícitas: `voice.neural`, `video.generate`, `audio.multitrack`.
   - Adicionar adaptador de teste `FakeExtensibleProvider` para comprovar desacoplamento sem modificar o Core.
2. **Evolução do `RenderSpec` e `ports.py`:**
   - Permitir `RenderSpec` receber múltiplos tracks de áudio (`AudioTrack`: narração, música, SFX, ambiência).
   - Suporte nativo a assets de vídeo (`AssetKind.video`) com propriedades de corte/trim (`trim_in_s`, `trim_out_s`, `mute_audio=True`).
3. **Preservação do `BudgetGuard` e Governança:**
   - Toda extensão de provider deve congelar a seleção no momento da submissão do job (`frozen_provider_selection`).
   - Bloqueio estrito de execução se o custo estimado ultrapassar `MAX_COST_USD_PER_VIDEO`.

---

### V4-00.09 — Checkpoints e Recuperação de Falhas

- **Persistência de Leases:** Implementada em `production.py` com fencing CAS (`claim_stage`).
- **Heartbeat:** `LeaseHeartbeat` renova ativamente o lock durante renders pesados, evitando que workers concorrentes tomem o job em voo.
- **Recuperação:** O boot de `main.py` religa automaticamente runs órfãos (`recover_orphans`) sem duplicar cobrança ou descartar progresso já salvo em disco.

---

### V4-00.10 — Matriz de Critérios de Aceite da Fase V4-00

| ID | Critério de Aceite | Evidência Rastreável | Status |
|---|---|---|:---:|
| **AC-01** | Mapeamento completo dos 5 módulos centrais e seus invariantes | `FS-08-dependency-map.md` e Seção 2 deste relatório | **PASS** |
| **AC-02** | Runtimes e dependências canônicas validadas sem segredos | Seção 2 e `secret_hygiene.py scan` (código 0) | **PASS** |
| **AC-03** | Zero regressões críticas na suíte canônica e novos testes verdes | RUN-13 + `test_v4_baseline_metrics.py`, `test_v4_subtitles_ticks_regression.py`, `test_v4_production_flow_pilot.py` e `test_v4_studio_real_flow_pilot.py` (191 pass) | **PASS** |
| **AC-04** | Fixture técnica de 60–90s gerada e documentada com conformidade | `v4_fixture_tecnica_60s.mp4` (63,52s, -16,3 LUFS, SHA `904eb8c9...`) | **PASS** |
| **AC-05** | Piloto audiovisual de 5–8 min original produzido no pipeline atual | `v4_piloto_audiovisual_5min.mp4` (**345,60s**, 18 cenas, -15,5 LUFS, SHA `9b20e2e7...`) | **PASS** |
| **AC-06** | Métricas de CPU, RAM (desacoplada pai/filhos), tempo, custo e hashes catalogadas | `storage/output/v4_baseline_metrics.json` e `docs/.../v4_baseline_metrics.json` | **PASS** |
| **AC-07** | Comparação AS-IS vs TO-BE e limitações do FFmpeg catalogadas | Seções 2.6 e 2.7 deste relatório | **PASS** |
| **AC-08** | Proposta de contratos para V4-01 especificada sem acoplamento | Seção 2.8 deste relatório | **PASS** |
| **AC-09** | **Revisão humana dos vídeos gerados** | Links e frames disponibilizados para o operador | **PENDENTE DE AVALIAÇÃO HUMANA** |

---

## 3. Decisão Final da Fase V4-00

> **DECISÃO: CONCLUÍDA TECNICAMENTE — CONDITIONAL GO (AGUARDANDO AVALIAÇÃO HUMANA DO OPERADOR)**
>
> Todas as pendências técnicas da fase V4-00 foram rigorosamente sanadas:
> 1. A duração do piloto documental (345,60s) cumpre a faixa estrita de 300–480s sem artifícios.
> 2. O teste com handlers simulados foi corretamente classificado como teste de integração do coordenador.
> 3. Foi adicionada a jornada real completa pelo fluxo do Studio (`tests/test_v4_studio_real_flow_pilot.py`) com FFmpeg e QA reais.
> 4. Foram adicionados 178 testes específicos de ticks e legendas comprovando a ausência de overlaps e a precisão do Core.
> 5. A métrica de RAM foi corrigida, desacoplando pai e filhos e documentando a limitação técnica do kernel.
> 6. As saídas históricas foram preservadas em diretórios exclusivos versionados.
> 7. Os critérios de QA rejeitam métricas essenciais ausentes em regime de falha fechada.
> 8. O impedimento técnico de Node/Playwright foi formalmente auditado e registrado.
> 
> Em estrito cumprimento ao `MASTER-PROMPT.md` e `V4-00-baseline.md`, **o avanço para a V4-01 NÃO deve ocorrer de forma automática**, ficando condicionado à revisão e homologação humana dos arquivos de vídeo disponibilizados.
