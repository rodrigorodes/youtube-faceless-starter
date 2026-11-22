# Avaliação de UX — Configurações (atual) × protótipo

Data: 2026-11-22 · Autor: agente (execução direta, sem runtime de workflow) · Pedido do PO:
"avaliar UX das configurações atual vs protótipo — o do protótipo tem uma usabilidade mais interessante".

## 1. Escopo e método

Comparação entre as **sete seções de Configurações** e o protótipo.

| Seção (menu) | Rota real | Rótulo no protótipo (`CFG`, linha 585) |
| --- | --- | --- |
| Canais | `/studio/canais` (canônica) | `channels` |
| Estratégia editorial | `/studio/configuracoes/estrategia` | `strategy` |
| Marca e estilo | `/studio/configuracoes/marca` | `brand` |
| Produção e orçamento | `/studio/configuracoes/producao` | `production` |
| Conexões e providers | `/studio/panel/conexoes` | `connections` |
| Conta e equipe | `/studio/panel/equipe` | `team` |
| Avançado e diagnóstico | `/studio/panel/avancado` | `advanced` |

Fontes do protótipo (`prototype/index.html`): casca `settings` (622), painéis `settingsChannels`
(623), `settingsStrategy` (624), `settingsBrand` (625), `settingsProduction` (627),
`settingsConnections` (628), `settingsTeam` (629), `settingsAdvanced` (630); utilitários
`heading` (520), `savedbar` (601), `channelTop` (602); CSS `cfg/cfgmenu` (488), `pillrow/choice`
(488), `feature-preview` (488), `matrix` (488), `savedbar` (488).

Evidência do atual: HTML **renderizado** da instância local (`/health` ok, porta 8000) das sete
páginas, mais leitura de `api/panel_channels.py`, `api/panel_settings.py`, `api/shell_v3.py`,
`api/panel_connections.py`, `api/panel_team.py`, `api/panel_advanced.py`.

## 2. O que a estrutura atual já tem de igual

- **Menu lateral de seções** (`nav[aria-label="Seções de configuração"]`) com os **mesmos sete
  rótulos** do `CFG` do protótipo, cada um levando ao canal ativo (`project_id`).
- **Canal ativo no topo** (`#canal-ativo-card`) — equivalente ao `channelTop()`; a nota "vídeos
  existentes preservam o snapshot deles" existe.
- **Cartões por seção** com título + subtítulo, e `formgrid` equivalente (`grid-2`/`field`).
- **Sanfonas abrem sozinhas**: o JS (`panel_channels._channels_page_js`) faz `det.open = true` em
  todas as `details.painel-sanfona`, exceto `canais-avancado` e `painel-identidade`. Ou seja, na
  prática o conteúdo aparece aberto como no protótipo (a sanfona é só o invólucro visual).

## 3. Onde o protótipo é mais interessante (gaps reais)

### 3.1 Escolha do perfil econômico em cartões (gap principal)
- Protótipo: `pillrow` com três `.choice` **clicáveis**, cada um com `<strong>` (Econômico /
  Equilibrado / Maior qualidade) e `<span class="sample">` explicando o que o perfil prioriza
  (`settingsProduction`, 627). Uma decisão, um clique, o "porquê" ao lado.
- Atual: `<select id="perfil-economico">` + `<ul class="perfis-lista">` **somente leitura** com a
  mesma informação (`panel_channels._budget_card`). Duas etapas (abrir o select, escolher) e a
  explicação fica separada do controle.
- **Ação tomada: implementado.** O perfil virou um `fieldset` de cartões de escolha (radio
  nativo, sem JS), mantendo o **mesmo nome de campo** `economic_profile`, o mesmo endpoint
  (`PUT /studio/projects/{id}/budget`) e a marcação do perfil ativo.

### 3.2 Cabeçalho da área
- Protótipo (`settings`, 622): eyebrow **CONFIGURAÇÕES** · h1 **"Seu estúdio, do seu jeito"** ·
  lead **"Identidade do canal, produção, integrações e controles avançados."**
- Atual (`shell_v3.render_settings_page_body`): eyebrow **SEU ESTÚDIO** · h1 **"Configurações"** ·
  lead **"Fora do caminho quando você está criando."** — o h1 repete o nome do menu e o lead não
  diz o que há lá dentro.
- **Ação tomada: implementado** (textos do protótipo).

### 3.3 Matriz de papéis
- Protótipo (`settingsTeam`, 629): tabela `matrix` **Papel × Editar/gerar · Aprovar · Publicar**,
  com Owner/Editor/Reviewer/Viewer. Comunica permissão de relance.
- Atual (`panel_team._roles_card`): lista de papéis com descrição em texto, sem matriz.
- **Fonte real disponível**: `domain/saas.ROLE_PERMISSIONS` (4 papéis × 11 permissões) e
  `ROLE_DESCRIPTIONS`. Dá para gerar a matriz do dado real, sem inventar.
- **Ação tomada: implementado.** `panel_team._permissions_matrix` gera a tabela a partir de
  `ROLE_PERMISSIONS` (colunas = `EDIT_VIDEO`, `APPROVE_PREVIEW`, `PUBLISH`). **Diverge de
  propósito** do protótipo: o protótipo é ilustrativo (Editor sem publicar); aqui vale o RBAC que o
  servidor aplica — **Editor publica**; Reviewer aprova e não publica; Viewer só lê. A matriz é dos
  papéis canônicos, então aparece também no estado vazio (sem organização). Testes:
  `tests/test_team_page.py::test_team_page_roles_matrix_comes_from_the_real_rbac` e
  `...::test_team_page_matrix_present_even_without_an_organization`.
- **Desvio consciente** da recomendação original: em vez de expor as permissões na `TeamView`
  (camada de aplicação), a matriz é montada na `api` lendo `ROLE_PERMISSIONS` — a `api` já depende do
  domínio (`panel_team` já importa `..domain.saas`) e é a camada de apresentação; evita mexer no
  contrato da `TeamView` e em todos os pontos que a constroem.

### 3.4 Prévia visual de estilo/voz (`feature-preview`)
- Protótipo (`settingsBrand`, 625): bloco `.feature-preview` com o nome do estilo e a voz —
  "prévia ilustrativa".
- Atual: não existe, por decisão explícita (`_appearance_card`: "nada de preview, cor ou
  percentual inventado"). A prévia do protótipo é decorativa.
- **Recomendação**: só trazer com dado real (ex.: frame do último render do canal). Baixo valor
  enquanto for ilustrativo.

### 3.5 Barra de salvamento com escopo (`savedbar` + `chipval "Escopo: canal"`)
- Protótipo: rodapé fixo "Alterações salvas localmente ao mudar cada campo." + chip de escopo.
- Atual: feedback **real** por formulário (`#budget-feedback`, `#channel-feedback`, ...), com
  estado de erro/sucesso e `aria-live`. É mais honesto que a barra estática do protótipo.
- **Recomendação**: manter o feedback real; opcionalmente acrescentar o chip de escopo
  ("Escopo: canal") ao lado do botão salvar, como reforço. Cosmético.

### 3.6 Onde ficam os providers
- Protótipo: "Providers por capacidade" na aba **Conexões** (628) e a escolha por tarefa na aba
  **Produção** (627).
- Atual: a escolha por tarefa ("Providers por tarefa") vive em Produção/Canais
  (`_providers_card`), e Conexões trata só de contas Google/YouTube + o que será pedido.
- **Recomendação**: manter. A separação "por tarefa" é mais útil no fluxo do canal; duplicar o
  catálogo em Conexões criaria dois lugares para a mesma verdade.

### 3.7 O que a seção "Canais" mostra
- Protótipo (`settingsChannels`, 623): **lista de canais** + destino YouTube + atalho para
  conexões.
- Atual: `/studio/canais` é a **página canônica** e mostra *todos* os cartões (canal ativo,
  identidade, estilo, providers, orçamento, YouTube, credenciais, preferências, avançado, novo
  canal). As seções `estrategia/marca/producao` **reusam** os mesmos cartões.
- Efeito: quem clica em "Canais" recebe tudo de uma vez; o protótipo dá só a lista. É uma
  divergência de arquitetura de informação **conhecida e coberta por testes**
  (`tests/test_settings_sections.py` exige `painel-perfil` em `/studio/configuracoes/canais`).
- **Recomendação**: decisão de produto. Trocar a canônica por uma lista enxuta melhora a leitura,
  mas mexe em vários testes e na expectativa de "a tela canônica é a dona do formulário".

## 4. Onde o atual é melhor que o protótipo (não regredir)

- **Dado real, sem número inventado**: gasto do mês separando real/estimado/sem custo/desconhecido;
  "US$ 0" dito por extenso em vez de "US$ 0,00".
- **Origem dos limites** ("padrão do servidor" vs "persistidos neste canal") e **fail-closed** do
  orçamento.
- **Isolamento por organização** e fronteira de tenant explícitas (Equipe/Avançado).
- **Feedback de escrita real** por formulário, com erro de servidor exibido ao operador.
- **Avançado read-only** com saúde medida e configuração efetiva sanitizada.

## 5. Recomendações priorizadas

1. ~~Perfil econômico em cartões de escolha~~ — **feito** (3.1).
2. ~~Cabeçalho com os textos do protótipo~~ — **feito** (3.2).
3. ~~Matriz de papéis a partir de `ROLE_PERMISSIONS`~~ — **feito** (3.3), na `api` (ver desvio).
4. Chip de escopo no rodapé dos formulários (3.5) — cosmético; **não feito** (o feedback real por
   formulário já comunica o escopo com mais honestidade).
5. `feature-preview` só com dado real (3.4) — depende de captura de frame; **não feito**.
6. Reavaliar a seção "Canais" como lista enxuta (3.7) — decisão de produto + testes; **não feito**.

## 6. Regra de decisão desta rodada (pedido do PO)

"Onde o atual for melhor, manter; o resto adequar ao protótipo, seguindo os docs de análise."
Aplicada assim:

- **Mantido** (atual melhor): feedback de escrita real por formulário; gasto com real/estimado/
  desconhecido e "US$ 0" por extenso; origem dos limites; fail-closed do orçamento; isolamento por
  organização; Avançado read-only com saúde medida.
- **Adequado ao protótipo**: menu principal (Configurações como 7º item), cabeçalho de Configurações,
  perfil econômico em cartões, matriz de papéis.
- **Não copiado** (protótipo é demonstração): "Reiniciar demo", faixa "protótipo navegável",
  `savedbar` estática, `feature-preview` decorativa, identidade de conta fictícia.
