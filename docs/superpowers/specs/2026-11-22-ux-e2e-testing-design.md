# Design: Automação de Testes de UX, Jornadas e Comportamento E2E

**Data:** 2026-11-22  
**Status:** Proposto / Em aprovação  
**Alvo:** `/Users/rodrigomendes/youtube-faceless-starter`  
**Referências:**
- Protótipo de UX: `docs/backlogs/faceless-visual-evolution 2/prototype/index.html`
- Proposta visual V3: `docs/backlogs/ux/faceless-studio-v3-proposta-ptbr.html`
- Catálogo de Aceite Canônico: `docs/backlogs/faceless-visual-evolution 2/qa/ACCEPTANCE.md` (Cenários A01–A37)
- Contrato Canônico de UX: `tests/test_ux_contract.py`

---

## 1. Contexto e Motivação (O Porquê)

O Faceless Studio concluiu recentemente as fases W0–W5 e S3–S5 da evolução visual V3, introduzindo navegação consolidada em 7 itens, workspace com abas de produção, edição granular por cena, radar de tendências e tela de configurações canônica.

Hoje, a qualidade de UX é aferida por ~180 arquivos de teste que executam sobre **strings HTML** renderizadas no backend (`test_ux_contract.py`, `test_home_v3.py`, etc.). Embora essenciais para garantir que certas regras não regridam (ex.: custo honesto, ausência de stack traces, ausência de dados do mockup vazando), esses testes possuem um ponto cego crítico:
1. **Não exercitam o DOM vivo do navegador:** bugs reais de colisão de elementos — como o Bug B2, em que IDs duplicados no modal faziam o `document.getElementById` ler dados do perfil em vez do formulário — escapam da validação estática.
2. **Não validam comportamento de scripts clientes:** abertura e fechamento de `<dialog>`, atalhos de teclado (Tab, Escape), alternância de tema escuro/claro, filtros dinâmicos de pílulas de tendências sem reload e prevenção de duplo clique.
3. **Não testam a jornada humana ponta a ponta:** não respondem se um operador consegue navegar, criar canal, puxar um tema em alta, revisar cenas, inspecionar a prévia e aprovar o render sem ficar desorientado ou encontrar bloqueios inesperados.

Este projeto estabelece uma suíte de testes de ponta a ponta (E2E) com **Playwright em Chromium real**, guiada por jornadas de usuário, para descobrir bugs comportamentais e blindar o produto contra regressões silenciosas.

---

## 2. Objetivos, Não-Objetivos e Anti-Objetivos

### Objetivos (Goals)
1. **Automação de Jornadas Críticas Fiel ao Operador:** Automatizar os cenários A01–A37 do catálogo de aceite (`qa/ACCEPTANCE.md`), priorizando a esteira de criação e aprovação.
2. **Validação de DOM Vivo e Acessibilidade:** Detectar programaticamente IDs duplicados, traps de foco, acessibilidade por teclado, e comportamento interativo de componentes client-side.
3. **Verificação de Breakpoints Responsivos:** Validar a integridade da interface nos três tamanhos canônicos: Mobile (390px), Tablet (768px) e Desktop (1280px / 1440px), assegurando ausência de overflow horizontal ou elementos inacessíveis.
4. **Execução Ágil e Inspecionável:** Executar no host macOS via Playwright Python com suporte a `--headed`, permitindo ao operador ver a execução ao vivo no navegador para triagem rápida.
5. **Aferição de Métricas de Ergonomia:** Contar programaticamente ações e cliques necessários para cumprir tarefas-chave (≤2 ações para criar rascunho, ≤3 ações para trocar mídia de cena).

### Não-Objetivos (Non-Goals)
1. **Regressão Visual de Pixel-Perfect / Diff de Imagem:** O protótipo (`prototype/index.html`) é uma simulação com dados ilustrativos. Os testes não comparam capturas de tela pixel a pixel, mas sim conformidade estrutural, hierarquia visual e estados de transição.
2. **Alterar Lógica de Negócio do Core:** A suíte de teste destina-se a validar e encontrar bugs na UX e nos contratos, sem alterar a semântica do backend nem enfraquecer regras preexistentes.

### Anti-Objetivos (Anti-Goals)
1. **Testes Frágeis com Delays / `sleep()` Arbitrários:** Todo teste deve aguardar estados explícitos de DOM ou eventos de rede usando os mecanismos nativos de espera do Playwright (`expect(locator).to_be_visible()`).
2. **Seletores Baseados em Classes Internas CSS Frágeis:** O teste deve navegar usando **Acessibilidade e Rótulos Visíveis** (`getByRole`, `getByLabel`, `getByText`), espelhando como o operador humano enxerga a tela.
3. **Efeitos Colaterais Destrutivos:** Nenhum teste pode realizar upload público ou deletar dados de contas reais. Testes reais de YouTube usam modo privado e canais de sandbox autorizados.

---

## 3. Decisões do Operador (O "Como" Decidido)

1. **Estratégia de Fases (Ordem de Ataque):**
   - **Fase A (Crítica de Operações + Configurações Essenciais):**
     - Jornada Início → Criar Vídeo / Tendência → Workspace/Cenas → Preview/Aprovação.
     - Telas de Configuração que alimentam a produção: **Canais** (identidade/troca de canal) e **Produção/Orçamento** (perfil econômico e teto).
   - **Fase B (Configurações Restantes):**
     - Estratégia Editorial, Marca e Estilo, Conexões e Providers, Conta e Equipe (matriz de papéis), Avançado.
   - **Fase C (Operações Estendidas e Métricas Avançadas):**
     - Desempenho/Analytics, histórico de versões, reabertura de vídeo publicado, medição rigorosa de cliques e tempos de transição.
2. **Ambiente do Navegador:**
   - Playwright Python rodando **direto no host macOS**, interagindo com o Studio em `http://localhost:8000`. Permite modo `--headed` para acompanhar visualmente.
3. **Massa de Dados e Backend:**
   - Modo padrão hermético: `STUDIO_TEXT=demo`, imagens `placeholder`, voz `piper` local, render local FFmpeg e PostgreSQL descartável (tmpfs) verificado por token de segurança.
   - Suporte autorizado para testes de ponta a ponta com credenciais reais da conta, exclusivamente com privacidade **Privada** e sem publicação pública automática.
4. **Protocolo de Triage, Falhas e Correções em Paralelo:**
   - **Continuidade (Fail-Continue):** A falha em um cenário de teste não interrompe a suíte inteira; o runner registra a falha com evidência e prossegue para os próximos cenários.
   - **Registro Sistemático de Achados:** Toda falha, inconsistência de UX ou oportunidade de melhoria é registrada imediatamente com evidência (rota, seletor, print/DOM e impacto real), alimentando a lista de achados verificados.
   - **Correções em Paralelo:** Bugs e desvios de baixo risco identificados durante os testes podem ser corrigidos diretamente, acompanhados de verificação imediata (vermelho → verde) para não travar a evolução.

---

## 4. Arquitetura da Solução de Testes E2E

### 4.1 Estrutura de Diretórios
```
tests/
  ├── e2e_ux/
  │   ├── __init__.py
  │   ├── conftest.py                   # Fixtures de navegador, contexto, login e URL base
  │   ├── helpers.py                    # Assertions de DOM (ex: detector de IDs duplicados, overflow)
  │   ├── pages/                        # Page Objects semânticos
  │   │   ├── base_page.py              # Shell V3, topbar, seletor de canal, tema, sidebar (7 itens)
  │   │   ├── home_page.py              # Funil, lista de vídeos, atalhos
  │   │   ├── new_video_page.py         # Formulário de tema, roteiro colado, formato
  │   │   ├── workspace_page.py         # 8 abas, editor de cenas, troca de mídia, prévia
  │   │   ├── preview_approval_page.py  # Player, checagem factual, aprovação atômica
  │   │   ├── trends_page.py            # Chips de filtro, cards de tendências, busca agora
  │   │   └── settings_pages.py         # Canais (modal e lista), Produção/Orçamento (perfil em cartões)
  │   ├── test_e2e_journey_operations.py # Jornadas A01, A03, A06, A07, A08, A17, A18, A21
  │   ├── test_e2e_dom_behavior.py      # Modais, IDs únicos, chips interativos, theme toggle
  │   ├── test_e2e_settings.py          # Configurações: Canais, Orçamento, Equipe
  │   └── test_e2e_responsive.py        # Validação nos viewports 390px, 768px, 1280px (A27)
scripts/
  └── run-e2e-tests.sh                  # Runner prático com flags para headless ou headed
```

### 4.2 Page Objects e Contratos de Interação
Os Page Objects encapsulam o comportamento da casca do Studio:
- `BasePage`: Provê navegação pelos 7 itens do menu lateral (`NAV_OPERACAO`), alternância de canal no dropdown global e troca de tema claro/escuro.
- `WorkspacePage`: Modela a seleção de cenas, edição de narração no `textarea`, substituição de mídia e transições entre abas de Conteúdo, Edição e Publicação.
- `SettingsPages`: Cobre o diálogo de novo canal (`#dlg-canal`), seleção do perfil econômico em cartões (`fieldset[name="economic_profile"]`) e verificação de matriz de papéis.

### 4.3 Verificadores Especiais de DOM e UX
1. **Detector de IDs Duplicados (`assert_no_duplicate_ids(page)`):**
   - Executa no browser: `document.querySelectorAll('[id]')` e agrupa por ID. Se qualquer ID aparecer mais de uma vez na página ativa ou em modal aberto, o teste falha com os seletores colidentes.
2. **Detector de Overflow Horizontal (`assert_no_horizontal_overflow(page)`):**
   - Garante que `document.documentElement.scrollWidth <= window.innerWidth` em todos os breakpoints.
3. **Rastreador de Cliques da Jornada (`ActionCounter`):**
   - Conta cliques e submissões entre o início da tarefa e a confirmação, comparando com as metas do `ACCEPTANCE.md` (≤2 para criar rascunho, ≤3 para trocar mídia).

---

## 5. O que fica a cargo do construtor (Builder's Scope)

1. Instalação e verificação de dependências locais (`pytest-playwright`, binário do Chromium).
2. Implementação detalhada dos localizadores semânticos nos Page Objects.
3. Ajustes de tolerância e espera de transições de animação/render nos testes assíncronos.
4. Criação do script de conveniência `scripts/run-e2e-tests.sh` para facilitar a execução interativa pelo desenvolvedor.
