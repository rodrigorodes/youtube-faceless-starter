# Painel e experiência

**Prefixo dos cenários:** `UX`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

O painel usa navegação de servidor, contexto de canal e áreas do vídeo. Helpers traduzem erros da API e resultados de publicação. Suites de browser existentes cobrem navegação, DOM, aprovação e três larguras de tela.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `UX.R01` | Links de páginas permitidas propagam canal; vídeo conserva projeto proprietário; área inválida normaliza para cenas e nav usa aria-current. | `renderer/app/studio/api/active_channel.py:22-69`, `renderer/app/studio/api/panel_video_nav.py:13-66` | [UX-01](#ux-01), [UX-02](#ux-02), [UX-08](#ux-08) |
| `UX.R02` | Resultado de publicação só é sucesso quando UPLOADED; demais resultados explicam próximo passo em português. | `renderer/app/studio/api/publicacao_js.py:18-46`, `renderer/app/studio/api/publicacao_js.py:68-86` | [UX-02](#ux-02), [UX-04](#ux-04), [UX-05](#ux-05) |
| `UX.R03` | Helper traduz 422/409/429/5xx; ações devem manter feedback legível e recuperável sem JSON cru ou sucesso falso. | `renderer/app/studio/api/erro_js.py:14-83`, `renderer/app/studio/api/panel_video.py:187` | [UX-03](#ux-03), [UX-04](#ux-04), [UX-07](#ux-07), [UX-08](#ux-08) |
| `UX.R04` | Garantir uso em 390/768/1280 px, navegação por teclado, foco e anúncio de erro; suites atuais não equivalem a auditoria completa. | `tests/e2e_ux/test_e2e_responsive.py:9-94`, `tests/e2e_ux/test_e2e_dom_behavior.py:23-37`, `renderer/app/studio/api/panel_video.py:59` | [UX-06](#ux-06), [UX-07](#ux-07) |
| `UX.R05` | Duplo clique não deve repetir efeito; ação pendente deve mostrar progresso e liberar interação após falha. | `tests/test_publication_execution.py:519-529`, `renderer/app/studio/api/panel_video.py:635-660` | [UX-05](#ux-05) |

## Resumo dos cenários

Total: 8 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [UX-01](#ux-01) | Navegação mantém contexto e área ativa | feliz/regressao | UX.R01 | `A_PROJETAR` |
| [UX-02](#ux-02) | Estados vazio, produção e aprovação são distintos | borda | UX.R01, UX.R02 | `A_PROJETAR` |
| [UX-03](#ux-03) | Falhas de formulário e transporte preservam feedback | erro | UX.R03 | `A_PROJETAR` |
| [UX-04](#ux-04) | Todos os resultados da publicação são honestos | regressao | UX.R02, UX.R03 | `A_PROJETAR` |
| [UX-05](#ux-05) | Duplo clique com latência e falha | concorrencia | UX.R05, UX.R02 | `A_PROJETAR` |
| [UX-06](#ux-06) | Responsividade com conteúdo longo | volume/borda | UX.R04 | `A_PROJETAR` |
| [UX-07](#ux-07) | Teclado, foco e anúncio de erros | borda/regressao | UX.R04, UX.R03 | `A_PROJETAR` |
| [UX-08](#ux-08) | Edição concorrente em duas abas | concorrencia/erro | UX.R03, UX.R01 | `A_PROJETAR` |

## Cenários

### UX-01 — Navegação mantém contexto e área ativa

- **Tipo:** feliz/regressao
- **Regras:** UX.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar troca silenciosa de canal durante navegação.
- **Pré-condições:** Canais A/B e um vídeo pertencente a A; página inicialmente em B.
- **Dados:** project_id de B; links Início, Tendências, Desempenho, Configurações; vídeo de A.
- **Passos:**
  1. Navegar pelos sete itens canônicos e usar voltar/avançar.
  2. Abrir vídeo de A e percorrer áreas.
  3. Abrir área inexistente e observar destino.
- **Esperado:** Páginas de canal preservam B; vídeo permanece de A; área ativa é identificada uma vez no menu correspondente; área inválida cai em cenas; links externos/downloads não recebem project_id.
- **Limitações:** Propagação de URL não é autorização; testar diretamente o dono retornado pela API.
- **Automação:** camada `browser`; referência `Existentes: tests/e2e_ux/test_e2e_shell_navigation.py:22-54; tests/test_active_channel.py; extensão multicanal proposta.`

### UX-02 — Estados vazio, produção e aprovação são distintos

- **Tipo:** borda
- **Regras:** UX.R01, UX.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Não sugerir que aprovação significa publicação.
- **Pré-condições:** Fixtures sem vídeos, em produção, awaiting_approval, failed e approved sem YouTube.
- **Dados:** Cinco estados em projetos separados; publicação ausente.
- **Passos:**
  1. Abrir lista e detalhe de cada fixture.
  2. Seguir ação principal sugerida.
  3. Recarregar estado approved sem destino.
- **Esperado:** Vazio orienta criação; awaiting_approval abre qualidade; failed abre produção; approved mostra pendente e sem destino, sem ID/URL YouTube inventados.
- **Limitações:** Texto e ordem visual podem evoluir; validar significado e ação real, não snapshot isolado.
- **Automação:** camada `browser`; referência `Existentes: tests/e2e_full/test_journey_piloto.py:74-85; tests/test_home_v3.py; proposta matriz de estados.`

### UX-03 — Falhas de formulário e transporte preservam feedback

- **Tipo:** erro
- **Regras:** UX.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Permitir recuperação compreensível após recusa.
- **Pré-condições:** Browser isolado com interceptação das respostas; formulário preenchido com dados sintéticos.
- **Dados:** 422 com loc body/title; 409 stale; 429; 503; conexão interrompida.
- **Passos:**
  1. Enviar formulário em cada variante.
  2. Ler mensagem e observar indicador pendente.
  3. Corrigir dado ou restabelecer resposta e reenviar.
- **Esperado:** Erro conhecido orienta em português; 422 nomeia campo; 409 sugere atualizar; sem JSON cru; desejado: entrada editável preservada e indicador encerrado após falha, sem sucesso falso.
- **Limitações:** Preservação e tratamento de conexão interrompida variam por tela e precisam de teste proposto; helper sozinho não garante renderização segura.
- **Automação:** camada `browser`; referência `Existente: tests/test_erro_js.py; proposta matriz browser em criação, edição e publicação.`

### UX-04 — Todos os resultados da publicação são honestos

- **Tipo:** regressao
- **Regras:** UX.R02, UX.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Não chamar retry ou reconciliação de sucesso.
- **Pré-condições:** Aba publicação com backend mock; nenhum envio real.
- **Dados:** UPLOADED com ID; IDLE, RETRY, RECONCILE, BLOCKED, DEAD_LETTER e resultado desconhecido.
- **Passos:**
  1. Acionar publicar com cada resposta.
  2. Inspecionar mensagem e cor/semântica de feedback.
  3. Recarregar com falha persistida.
- **Esperado:** Só UPLOADED confirma publicação; RETRY diz tentativa agendada; RECONCILE orienta não reenviar; desconhecido não confirma; causa persistida e resultado do clique mantêm significado compatível.
- **Limitações:** UPLOADED mockado não atesta existência remota; segredo/sessão não devem compor fixtures de mensagens.
- **Automação:** camada `browser`; referência `Existentes: tests/test_publicacao_acao.py; tests/test_publication_api.py:111-124; extensão browser proposta.`

### UX-05 — Duplo clique com latência e falha

- **Tipo:** concorrencia
- **Regras:** UX.R05, UX.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Proteger usuário de ações repetidas durante espera.
- **Pré-condições:** API local instrumentada com efeito de upload fake; atraso controlado de 2 s.
- **Dados:** Dois cliques rápidos em Publicar agora; variante 503; dois cliques em iniciar produção.
- **Passos:**
  1. Disparar cliques e contar requests e efeitos.
  2. Aguardar resposta e observar botão/feedback.
  3. Repetir após falha conhecida e após sucesso.
- **Esperado:** Desejado: pendência visível e controle indisponível enquanto aguarda; backend limita efeito único mesmo se receber repetição; falha permite ação apropriada; sucesso não gera outro upload.
- **Limitações:** Não pressupor que todos os botões já implementam desabilitação; backend e UI são oráculos separados.
- **Automação:** camada `browser`; referência `Existentes: tests/test_publication_execution.py:529; proposta de browser com atraso e contador de efeitos.`

### UX-06 — Responsividade com conteúdo longo

- **Tipo:** volume/borda
- **Regras:** UX.R04
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Manter controles acessíveis em telas estreitas.
- **Pré-condições:** Browser local; lista com 50 vídeos e títulos longos sintéticos.
- **Dados:** Viewports 390x844, 768x1024 e 1280x800; título com 100 caracteres e mensagem de erro longa.
- **Passos:**
  1. Abrir início, criação, canais, storyboard e publicação em cada viewport.
  2. Percorrer controles e abrir diálogo.
  3. Verificar overflow, sobreposição, IDs e ação principal.
- **Esperado:** Desejado: nenhum overflow horizontal global ou controle essencial oculto; texto quebra de forma legível; diálogo permite cancelar/confirmar; IDs únicos. Tabelas podem ter rolagem local identificável.
- **Limitações:** Suites atuais cobrem início/criação/canais; storyboard e publicação com volume são ampliação. Não há medição visual nesta tarefa.
- **Automação:** camada `browser`; referência `Existente: tests/e2e_ux/test_e2e_responsive.py:16-94; extensão de telas e volume proposta.`

### UX-07 — Teclado, foco e anúncio de erros

- **Tipo:** borda/regressao
- **Regras:** UX.R04, UX.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Operar fluxos essenciais sem mouse e perceber feedback.
- **Pré-condições:** Browser e leitor de tela local; diálogo de pilares e pedir ajustes disponíveis.
- **Dados:** Tab/Shift+Tab/Enter/Escape; zoom 200%; erro 422 de campo obrigatório.
- **Passos:**
  1. Percorrer navegação e abrir diálogo só por teclado.
  2. Fechar com Escape e verificar retorno de foco.
  3. Provocar erro e ouvir anúncio; revisar nomes e foco visível em zoom.
- **Esperado:** Critério desejado: foco previsível, visível e contido no modal; retorno ao disparador; campos com nomes; erro anunciado sem depender apenas de cor; operação possível em zoom.
- **Limitações:** ARIA encontrado é evidência estrutural apenas; compatibilidade real com leitor de tela exige execução manual; não declarar conformidade WCAG completa.
- **Automação:** camada `manual`; referência `Base existente: tests/e2e_ux/test_e2e_dom_behavior.py:23-37; roteiro manual e assertions de foco propostos.`

### UX-08 — Edição concorrente em duas abas

- **Tipo:** concorrencia/erro
- **Regras:** UX.R03, UX.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar sobrescrita silenciosa e contexto desatualizado.
- **Pré-condições:** Duas abas do mesmo vídeo, versão de roteiro inicial compartilhada; banco local.
- **Dados:** A edita cena para fato válido X; B mantém versão antiga e tenta fato válido Y.
- **Passos:**
  1. Salvar em A.
  2. Salvar em B sem recarregar.
  3. Observar mensagem e recarregar B; verificar versão na API.
- **Esperado:** Critério desejado apoiado no erro stale: alteração obsoleta é recusada ou exige resolução explícita; feedback informa atualizar; B não anuncia sucesso nem apaga X silenciosamente.
- **Limitações:** Helper traduz conflito, mas não comprova proteção de todas as rotas de edição; testar contrato real antes de tratar como garantia implementada.
- **Automação:** camada `browser`; referência `Base: renderer/app/studio/api/erro_js.py:33-35; teste multia ba proposto, complementar a tests/e2e_full/test_journey_diretor.py.`

## Resumo do capítulo

Oito cenários documentais A_PROJETAR. Contratos encontrados e melhorias de cobertura propostas são explicitamente separados; nenhuma sessão de navegador foi executada.
