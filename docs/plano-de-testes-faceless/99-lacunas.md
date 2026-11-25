# Lacunas, riscos e limites da campanha

**As lacunas e os riscos abaixo não são resultados de execução.** A revisão é estática e
orientada ao planejamento; não é auditoria exaustiva nem certificação de segurança.
A seção "Estado da suíte no ambiente canônico" é a única com execução real, referenciada
em `evidencias/`.

## Lacunas confirmadas na infraestrutura de validação

| ID | Prioridade | Evidência | Impacto / ação antes da campanha |
|---|---|---|---|
| LAC-01 | alta | `scripts/test-container.sh:49-55,100-109`; `requirements-dev.txt:1-2`; `renderer/requirements.txt:1-10`; `tests/e2e_full/conftest.py:19` | Runner padrão coleta `tests`, mas a instalação declarada não inclui Playwright. Há import na coleta E2E. Confirmar dependências da imagem limpa e separar suites ou preparar dependências em tarefa própria; não alegar suíte integral executável sem conferência. |
| LAC-02 | alta | `docker-compose.test.yml:1-14`; `tests/conftest.py:10-46,96-105` | Compose simples de banco não monta a prova de descartabilidade. Usar o runner que já cria a prova, não contornar a fixture. |
| LAC-03 | alta | `scripts/run-e2e-tests.sh:13-39` | Runner UX usa por padrão a stack de uso na porta 8000. Conferir destino real consumido pelas fixtures antes de rodar; preflight HTTP não comprova isolamento. |
| LAC-04 | media | `scripts/test-container.sh:102-109` | Checkout montado read-only e contêiner removido: relatório JUnit não persiste automaticamente. Planejar exportação segura, não prometer caminho gravável inexistente. |
| LAC-05 | alta | `docker-compose.e2e.yml:35-41`; `tests/e2e_full/conftest.py:1-8` | Demo/placeholder, orçamento desabilitado e limite 60 s: E2E não prova fornecedores reais, budget ou longform. Campanhas separadas. |
| LAC-06 | alta | `scripts/run-e2e-full.sh:18-31` | Nome fixo `faceless-e2e` e `down -v`: duas campanhas concorrentes podem destruir a stack uma da outra. Reservar execução exclusiva; não rodar sobre dados que devam ser preservados. |
| LAC-07 | media | `tests/conftest.py:79-83`; `tests/e2e_full/conftest.py:36-50` | Guardas podem produzir skips. Exit 0 não equivale a execução das atividades dependentes de banco/browser. Exigir resumo de skips e motivos. |

Esses pontos são evidência de configuração e limites, não falhas reproduzidas do
produto. Não foram corrigidos nesta tarefa.

## Achados de produto (decisão do usuário em 2026-11-25)

O usuário decidiu **corrigir ACH-01 e ACH-04..08 no produto** e manter **ACH-09 como
intencional**. As correções foram aplicadas e verificadas por testes de subconjunto; a
execução completa pós-correção está em `evidencias/RUN-2026-11-25-container/RUN-07-ach-fixes.md`.

| ID | Prioridade | Evidência | Impacto / ação |
|---|---|---|---|
| ACH-01 | alta | `renderer/app/studio/api/panel_video_workspace.py:1105-1119` (trilha, volume e ducking no formulário) x `renderer/app/studio/api/panel_video_workspace.py:2280-2283` (payload do `style-patch` só com `music.bpm` e `music.seed`) | **Corrigido:** os controles de trilha, volume e ducking foram removidos; a tela mantém BPM/seed (que o patch persiste) e explica que a trilha é sintetizada e a mixagem é aplicada pelo motor. Evita prometer um salvamento que não existe. |
| ACH-02 | baixa | `renderer/app/studio/api/panel_video_storyboard_js.py` (dois botões por cena: "Trocar/Adicionar mídia" e "+ Adicionar mídia") | Duplicidade de affordance na mesma cena; o teste existente `tests/ve08/test_storyboard_functional.py::test_media_modal_changes_only_the_target_scene` selecionava a cena errada por `.first`. Corrigido o teste (escopo por cena), não a UI. |
| ACH-03 | baixa | `renderer/app/studio/api/shell_v3.py` (WIP local com `nav-glyph` e CSS) | A nav atual usa `<span aria-hidden="true">{glifo}</span>{rótulo}`; o teste de referência espera o glifo e os testes de Configurações esperam só o rótulo. Decidir o contrato de UI (glifo visível ou não) e alinhar os testes. A suíte canônica registra falhas de rótulo em `test_settings_sections.py`, `test_channels_page.py`, `test_styles_page.py` e `test_connections_page.py` (2 falhas confirmadas nestes dois últimos). |
| ACH-04 | media | `renderer/app/studio/api/shell_v3.py:429` (JS `$('#btn-novo-canal')`) x ausência do `id` no HTML gerado | **Corrigido:** o diálogo modal e o JS morto foram removidos. O caminho de novo canal é o item "＋ Novo canal…" do seletor (assistente em `/studio/canais/novo`), que já era o comportamento alcançável. Teste atualizado para o desenho atual. |
| ACH-05 | media | `renderer/app/studio/api/panel_analytics.py:315` (`_filters_html` definido) x `:353-520` (`render_analytics` não o chama) | **Corrigido:** os filtros de vídeo/pilar e os chips de período voltaram a ser renderizados; o canal continua no seletor global da casca. A rota aceita `project_id` (seletor do topo) e `project` (endereço antigo), e o JS morto de `#analytics-project` foi removido. |
| ACH-06 | media | `renderer/app/studio/api/panel_new_video.py:283` (rótulo de herança = nome do estilo) x `renderer/app/studio/api/panel_video.py:36` ("Herdar do canal (nome)") | **Corrigido:** a opção de herança no novo vídeo passou a usar o mesmo texto da tela de vídeo: "Herdar do canal (nome do estilo)". |
| ACH-07 | media | `renderer/app/studio/api/routes.py:1889-1900` (`panel_settings.render_channel_list`) x `renderer/app/studio/api/panel_channels.py:691` (`id="painel-perfil"`) | **Corrigido:** `/studio/configuracoes/canais` passou a redirecionar (302) para a lista canônica `/studio/canais`; o renderizador duplicado foi removido. Um único endereço mostra a lista de canais. |
| ACH-08 | baixa | `renderer/app/studio/api/panel_new_video.py` (preset ausente) x `_language_label` sem uso | **Corrigido:** a tela de novo vídeo voltou a mostrar o cartão "Predefinição do canal" com idioma, voz e estilo herdados; `_language_label` voltou a ser usado. O Resumo do protótipo continua sem linha de idioma. |
| ACH-09 | media | `renderer/app/studio/composition/settings.py:71` (`publication_enabled: bool = True`) x `renderer/app/studio/application/production.py:609-611` (`PublishHandler` sempre que `publish` é injetado) | **Intencional (confirmado pelo usuário):** a publicação vem habilitada por padrão e a recusa acontece na execução da etapa. **Coberto no plano por PUB-13:** a campanha deve executar o caminho `STUDIO_PUBLICATION_ENABLED=0` (BLOCKED, sem claim/upload) e o padrão ligado; o risco de upload real permanece. Não é bug. |

### Achados que afetam cenários do plano

ACH-04..ACH-08 foram corrigidos; os cenários abaixo voltaram a ter controle na UI. ACH-09
continua como decisão de campanha.

| Achado | Cenários afetados | Efeito no passo |
|---|---|---|
| ACH-04 | [CFG.C01](02-canais-configuracao-e-conexoes.md), [UX-01](10-painel-e-experiencia.md) | **Resolvido:** o caminho é o item "＋ Novo canal…" do seletor, que leva ao assistente `/studio/canais/novo`. |
| ACH-05 | [ANA-04](09-analytics-e-aprendizado.md) | **Resolvido:** os filtros de vídeo/pilar e os chips de período voltaram à tela; o canal é o seletor global. |
| ACH-06 | [CFG.C05](02-canais-configuracao-e-conexoes.md), [DRC-04](13-direcao-e-composicao.md) | **Resolvido:** a opção de herança se anuncia como "Herdar do canal (nome)". |
| ACH-07 | [CFG.C04](02-canais-configuracao-e-conexoes.md), [UX-01](10-painel-e-experiencia.md) | **Resolvido:** `/studio/configuracoes/canais` redireciona para `/studio/canais`. |
| ACH-08 | [CFG.C01](02-canais-configuracao-e-conexoes.md) | **Resolvido:** o cartão "Predefinição do canal" mostra idioma, voz e estilo herdados. |
| ACH-09 | [PUB.R05](08-aprovacao-e-publicacao.md), [UX-04](10-painel-e-experiencia.md) | **Coberto por PUB-13:** o caminho "publicação desabilitada" (`STUDIO_PUBLICATION_ENABLED=0`) tem cenário próprio; o padrão ligado também é verificado. A campanha deve executar os dois. |

## Estado da suíte no ambiente canônico (execução real)

Evidência: `evidencias/RUN-2026-11-25-container/RUN-02-container-suite.md`,
`RUN-03-triage.md`, `RUN-04-container-suite-after-triage.md`,
`RUN-05-group-a-refined.md`, `RUN-06-container-suite-after-group-a.md`,
`RUN-07-ach-fixes.md`, `RUN-10-suite-verde.md` e `RUN-11-cobertura-100.md`.

- Comando: `scripts/test-container.sh tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -q`.
- Resultado da execução RUN-02: **39 failed, 4019 passed, 20 skipped** (636 s, exit 1).
  A primeira execução do mesmo comando deu 40 failed / 4018 passed; uma falha não se
  repetiu (teste flaky ou dependente de ordem).
- Resultado da execução RUN-04 (após a triagem): **32 failed, 4026 passed, 20 skipped**
  (691 s, exit 1). As 7 falhas removidas são os grupos B (3), C (2) e D (2).
- As falhas se concentram em quatro grupos: (A) drift de UI/casca após o WIP V4/V3
  (32 falhas, principalmente `test_panel_page.py`, `test_settings_sections.py`,
  `test_channels_page.py`, `test_video_style_api.py`, `test_analytics_page.py`,
  `test_panel_production_page.py` e `test_script_page.py`); (B) artefatos gerados
  desatualizados (3); (C) lista de migrações esperada desatualizada (2); (D) fluxo de
  produção com banco (2).
- Resultado da execução parcial RUN-05 (9 arquivos do grupo A, com `--tb=short`):
  **32 failed, 165 passed** (86 s, exit 1). O detalhamento das 32 falhas está em
  `evidencias/RUN-2026-11-25-container/RUN-05-group-a-refined.md` e resume-se em:
  A1 asserção mais estrita que o HTML atual (4), A2 texto/markup da UI mudou (20),
  A3 mudança funcional com decisão de produto pendente (6), A4 comportamento já
  commitado que os testes não acompanharam (2). Depois de corrigir A1 e A4:
  **29 falhas** (24 de A2, 5 de A3).
- Resultado da execução completa RUN-06 (após as correções de A1/A4): **29 failed,
  4029 passed, 20 skipped** (629 s, exit 1). Série: RUN-02 39 → RUN-04 32 → RUN-06 29.
  As 3 falhas removidas são exatamente as de A1/A4.
- Resultado da execução completa RUN-08 (após as correções de ACH-01 e ACH-04..08):
  **23 failed, 4035 passed, 20 skipped** (767 s, exit 1). As 5 falhas de A3 saíram; as 23
  restantes são todas A2 (texto/markup do WIP V4/V3). O flake de TTS, que falhou na RUN-07,
  passou na RUN-08.
- Resultado da execução completa RUN-10 (após o merge do WIP V4/V3 na base `79e3585` e
  dos ajustes de A2): **4059 passed, 20 skipped, 0 failed** (748,70 s, exit 0). A suíte
  canônica ficou verde. Série: RUN-02 39 → RUN-04 32 → RUN-06 29 → RUN-07 25 → RUN-08 23
  → RUN-10 0. O flake de TTS passou nesta execução; a higiene de segredos passou após
  remover do índice o artefato de debug `tests/_debug_trend.py`.
- Resultado da execução completa RUN-11 (após a cobertura de PUB-13 e a correção do flake
  de TTS): **4059 passed, 20 skipped, 0 failed** (682,07 s, exit 0). Série: RUN-02 39 →
  RUN-04 32 → RUN-06 29 → RUN-07 25 → RUN-08 23 → RUN-10 0 → RUN-11 0. A suíte ficou
  verde e o teste de TTS passou com a expectativa baseada na evidência.
- **Triagem concluída:** os grupos B, C e D foram corrigidos como artefatos de teste
  desatualizados (não bugs de produto). O grupo A foi refinado em RUN-05: A1 são
  defeitos de teste (asserção em markup exato) e A4 é atraso de teste em relação a
  comportamento já commitado — ambos corrigíveis sem tocar no produto. A3 (ACH-04..08)
  foi corrigido no produto na RUN-07; A2 foi resolvido na RUN-10 com o WIP aprovado e os
  testes alinhados. Nenhuma falha do grupo A foi confirmada como regressão de produto;
  ACH-09 é intencional e está coberto por PUB-13.
- **Nenhum cenário do plano foi promovido a PASS por esta execução.** A suíte existente
  não é o plano; o WIP de UI foi aprovado e mergeado na base `79e3585`, e a suíte ficou
  verde na RUN-11. O plano cobre 88 regras com 131 cenários, todos ainda `A_PROJETAR`.
- O host macOS não é ambiente válido (ffmpeg Homebrew sem libass): 19 falhas de
  render/subtitles no host; os mesmos arquivos passam no container (74 passed, 1 skipped).

## Triagem por grupo (RUN-02/RUN-03)

A triagem abaixo separa artefato de teste de produto. Nenhum item do grupo A foi
confirmado como regressão de produto. A1, A4 e A3 (ACH-04..08) já foram corrigidos; A2
depende da aprovação do WIP V4/V3 e ACH-09 foi mantido como intencional e coberto por PUB-13.

| Grupo | Falhas | Classificação | Evidência / ação |
|---|---|---|---|
| A. Drift de UI/casca | 32 | **Misto: 4 defeitos de teste (corrigidos), 24 textos/markup do WIP, 5 mudanças funcionais, 2 atrasos de teste (corrigidos)** | Refinado na RUN-05 (`evidencias/RUN-2026-11-25-container/RUN-05-group-a-refined.md`). A1: 4 asserções em markup exato — corrigidas; 1 falha resolvida e 3 seguem em A2. A2: a nav ganhou glifos (`⌂ Início`), Configurações passou de 7 para 4 seções, Tendências virou "Tendências e ideias", o vazio virou "Primeiros passos", a nota de custo saiu de `<p class="nota-custo">` para o rodapé, o breakpoint foi para 1000 px, o `aside.side` ganhou `aria-label`, o eyebrow "ESTÚDIO DO CANAL" saiu da prévia e do Roteiro. A3: ACH-04 a ACH-08 — corrigidos no produto na RUN-07. A4: `auto_research` e `publication_enabled` já commitados — corrigido na fixture. A2 foi resolvido na RUN-10 (WIP aprovado e testes alinhados); restam 0 falhas. |
| B. Artefatos gerados | 3 | **Artefato gerado no host, não no container** | `contracts/v1/project.schema.json` tinha `minimum: 0.0` (geração no host) e o container gera `0`; `docs/22-modelo-de-dados.md` estava em 41 migrações. Corrigido: contratos regenerados dentro do container e `docs/22` regenerado com `scripts/export_schema.py --build` contra Postgres 16 efêmero. 39 passed nos 3 arquivos. |
| C. Lista de migrações | 2 | **Teste desatualizado** | `tests/test_db.py` esperava 41 migrações; a árvore tem 48 (0047–0053). Atualizada a lista esperada; 22 passed com o grupo D. |
| D. Fluxo de produção | 2 | **Teste desatualizado** | A fixture não desligava `auto_research` (padrão `True` desde a pesquisa Wikipédia) e o teste esperava a pipeline clássica; a guarda de estágio indisponível testava `RESEARCH`, que agora está disponível. A fixture passou a usar `auto_research=False` e o teste de guarda continua válido; a pipeline com pesquisa tem cobertura em `tests/test_pesquisa_automatica.py`. 22 passed com o grupo C. |

### Achados menores no grupo A (não bloqueiam a triagem)

Os itens abaixo são observações menores; os que ganharam ID próprio estão em ACH-04 a
ACH-09. O último item foi resolvido na RUN-07.

- `tests/test_tts_calibration.py`: a medição de pausa por pontuação ficou em 2,96 s contra
  4,0 ± 1,0 s na RUN-07 (limiar inferior 3,0 s) e passou na RUN-08 e na RUN-10. A causa era
  a expectativa errada: o delta real entre prosa com e sem pontuação é ~3,25 s (média das
  três execuções de evidência), não `10 × 0,40 s` — o ponto final já tem silêncio de borda
  nas duas leituras. O teste passou a comparar com a média registrada, com tolerância de
  15% para a variância da diferença entre duas sínteses estocásticas. Não é regressão de
  produto; a medição agora reflete o áudio real.
- `renderer/app/studio/api/shell_v3.py`: Configurações passou de 7 seções (W1) para 4
  seções principais (V4/V2), com Equipe e Avançado dentro de Conexões. É uma mudança de
  desenho; o WIP foi aprovado e os testes de navegação foram alinhados na RUN-10.
- `renderer/app/studio/api/shell_v3.py`: a classe CSS `.nota-custo` existe, mas a nota de
  custo é renderizada como `<span class="sub">`; o seletor do teste ficou órfão. Decidir se
  a nota deve voltar a usar a classe ou se o CSS deve ser removido. As quatro categorias
  continuam no texto (`cost_summary_text`), então não há perda de informação.
- `renderer/app/studio/api/panel_oauth.py`: o retorno com `state` desconhecido passou a
  redirecionar (303) para Conexões em vez de renderizar a mensagem "Não foi possível
  identificar o canal". O teste antigo esperava a mensagem. Confirmar que o redirecionamento
  não vira beco sem saída e que o erro é explicado na tela de Conexões.
- Diálogo de novo canal (`#btn-novo-canal`) e preset de idioma na tela de novo vídeo:
  resolvidos em ACH-04 e ACH-08. As asserções em `<aside class="side">` seguem a subclasse
  A1 da RUN-05.

## Pendências de projeto da campanha

- Mapear cada cenário ao nodeid/assertions completos; referências a arquivos de teste são ponto de partida.
- Definir ambiente/fixtures, proprietário e executor para cada rodada antes de promover A_PROJETAR.
- Estabelecer limites de desempenho com hardware, duração de vídeo, mídia e concorrência documentados.
- Avaliação humana da voz, conteúdo, licença e estética precisa de critérios e amostras; QA técnico não a substitui.
- Decidir campanha live separada, canal de teste, visibilidade e teto de custo. Ausência de credencial não deve ser contornada.
- Confirmar comportamento sob reinício, falha parcial e concorrência com banco real descartável; mocks não demonstram atomicidade.
- Conferir os trechos locais modificados novamente antes de executar: o plano foi produzido em árvore dirty e pode haver edição paralela.
- Não presumir isolamento multitenant a partir de entidades de canal/equipe.

## Escopo de cobertura

Os capítulos organizam as atividades por áreas de produto, operação e riscos.
Não significam que cada combinação de configuração, endpoint e fornecedor foi enumerada.
A matriz de regras mede **cobertura planejada**, não cobertura executada nem cobertura
de código. Novas rotas/regras descobertas na campanha devem gerar cenários adicionais.

## Revisões complementares

Os fragmentos de revisão das três áreas ficam em `fragmentos/`. Eles distinguem
achados fundamentados de hipóteses e registram as fontes dos capítulos. Sua existência
não promove qualquer cenário para PASS.
