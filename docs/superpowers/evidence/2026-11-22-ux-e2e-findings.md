# Relatório de Evidências e Achados: Suíte E2E de UX e Jornadas

**Data:** 2026-11-22  
**Ambiente:** Host macOS (Darwin arm64, Python 3.11.9, Playwright Chromium v1255)  
**Alvo:** Faceless Studio local em `http://localhost:8000` (Docker Compose preview)  
**Status da Suíte:** **22/22 PASSED** (Duração: ~12s)

---

## 1. Resumo Executivo

Foi projetada e implementada uma suíte completa de testes de ponta a ponta (E2E) com **Playwright Chromium real** no diretório `tests/e2e_ux/`, orquestrada pelo script hermético `scripts/run-e2e-tests.sh`.

Diferente dos testes legados em strings HTML (que validam apenas regex e sintaxe), a nova suíte valida o **DOM vivo**, o motor de renderização de CSS, a execução de JavaScript client-side (como `<dialog>`, filtros de pílulas de tendências, alternância de tema) e a experiência ergonômica do operador ao longo de jornadas completas.

---

## 2. Cobertura da Suíte Implementada

| Módulo de Teste | Cenários Cobertos | Status |
|---|---|---|
| `test_e2e_smoke.py` | Conectividade, integridade de layout e ausência de IDs duplicados na Home | ✅ PASSED |
| `test_e2e_shell_navigation.py` | Presença e ativação dos 7 itens canônicos da casca V3, botão `#btn-tema` | ✅ PASSED |
| `test_e2e_journey_creation.py` | Jornada J1: Criação de canal via modal `#dlg-canal`, seleção ativa, criação de vídeo em 3 etapas | ✅ PASSED |
| `test_e2e_journey_workspace.py` | Jornada J2: Navegação pelas 8 áreas do workspace (`visao-geral` a `producao`), aviso de honestidade de fontes | ✅ PASSED |
| `test_e2e_journey_approval.py` | Jornada J3: Prévia unificada, checklist de QA, regra R3 (nunca exibir US$ 0,00 falso) e crumb de retorno | ✅ PASSED |
| `test_e2e_settings.py` | Configurações: Canais, cartões de perfil econômico (`ECONOMY`, `BALANCED`, `PREMIUM`), matriz de papéis RBAC | ✅ PASSED |
| `test_e2e_dom_behavior.py` | Diálogo de pilares de tendências (`#dialog-pilares`), fechamento por tecla `Escape`, atalho "Criar vídeo deste tema" | ✅ PASSED |
| `test_e2e_responsive.py` | Responsividade e ausência de overflow horizontal em 3 viewports: Mobile (390px), Tablet (768px), Desktop (1280px) | ✅ PASSED (9/9) |

---

## 3. Achados e Bugs Verificados (com Prova RED → GREEN)

### Achado #1: Overflow Horizontal Crítico em Mobile 390px (`/studio/canais`) — **CORRIGIDO**
- **Sintoma:** Ao carregar a tela de canais em viewport de 390px (padrão iPhone 12/13/14), a página sofria overflow horizontal massivo de **723px** de largura total (`scrollWidth: 723px > innerWidth: 390px`), quebrando o alinhamento de leitura e exigindo rolagem horizontal.
- **Causa Raiz Identificada via Playwright:**
  1. A classe `.cost` em `panel_channels.py` possuía a regra `white-space: nowrap;`.
  2. Quando um provider está com custo `UNKNOWN` (ex.: OpenCode Luna), o texto descritivo gerado é longo (*"Custo desconhecido — nenhum preço confirmado; não é tratado como zero (preço do bridge)"*, ~90 caracteres).
  3. Sem permissão para quebra de linha, o `<span>` forçava uma largura mínima contínua de mais de 600px.
  4. Adicionalmente, `.grade-providers` possuía `grid-template-columns: 1fr;` no media query de 820px, que no padrão CSS Grid tem piso implícito em `minmax(auto, 1fr)`.
- **Correção Aplicada:**
  - `renderer/app/studio/api/panel_channels.py`:
    - `.cartao-provider`: adicionado `min-width: 0;`
    - `.cost`: substituído `white-space: nowrap;` por `overflow-wrap: anywhere;`
    - `.porta-spec code, .cartao-provider-modelo`: adicionado `word-break: break-all;`
    - `@media (max-width: 820px)`: `.grade-providers` atualizado para `grid-template-columns: minmax(0, 1fr);`, `.cartao-provider { min-width: 0; }` e `.cost { white-space: normal; }`.
- **Evidência do Teste:**
  - *Antes:* `test_channels_settings_responsive_no_overflow[mobile-390-844]` falhava com `scrollWidth (723px) > innerWidth (390px)`.
  - *Depois:* O teste passa com `scrollWidth: 390px == innerWidth: 390px` (**0px de overflow**).

### Achado #2: Rastreamento e Mapeamento de Tópicos entre Telas — **RESOLVIDO**
- **Observação:** O botão "Criar vídeo deste tema" nos cards de tendências encaminha para `/studio/panel?topic=...` (preenchendo o `#topic` do hero do Início), enquanto a tela dedicada de criação (`/studio/panel/novo-video`) utiliza o ID `#tema-novo`.
- **Tratamento:** O Page Object `NewVideoPage` e o teste `test_e2e_dom_behavior.py` foram alinhados semanticamente para localizar o campo tanto pelo rótulo acessível (`Sobre o que é o vídeo?` / `Tema do vídeo`) quanto pelos seletores `#topic, #tema-novo`, garantindo robustez a qualquer variação de fluxo.

### Achado #3: Paridade de Nomes de Papéis RBAC na Tela de Equipe — **RESOLVIDO**
- **Observação:** O protótipo ilustrativo exibia os papéis em Title Case (`Owner`, `Editor`), mas o backend real (`panel_team.py`) renderiza com fidelidade absoluta ao enum do domínio `domain/saas.Role` (`owner`, `editor`, `reviewer`, `viewer`).
- **Tratamento:** O teste `test_settings_team_page_roles_matrix` foi atualizado para validar a presença dos quatro papéis reais do RBAC em minúsculas, refletindo com precisão as permissões aplicadas pelo servidor.

---

## 4. Telemetria de Ergonomia de UX (Métricas Canônicas)

- **Criação de Canal:** 1 interação de abertura de modal (`#btn-novo-canal`), preenchimento simples de nome/nicho e 1 clique de submissão. Redirecionamento e seleção de canal ativo instantâneos.
- **Criação de Vídeo (Hero vs. Wizard):**
  - No Hero (`/studio/panel`): 1 campo de tema + seleção de formato + 1 clique no botão `✦ Criar vídeo →`.
  - No Wizard (`/studio/panel/novo-video`): 3 etapas explícitas (Conceito → Revisão → Sucesso) com feedback visual claro e link direto para o Workspace.
- **Workspace:** Transições entre as 8 áreas (`Visão geral`, `Fontes`, `Narração`, `Cenas`, `Composição`, `Qualidade`, `Publicação`, `Produção`) ocorrem sem quebra de contexto e sem duplicação de IDs em nenhum dos estados.
- **Acessibilidade:**
  - Tecla `Escape` fecha os diálogos `<dialog>` nativamente.
  - Zero elementos indisponíveis com atributos de foco indevidos.

---

## 5. Como Executar a Suíte

Para rodar em modo headless (rápido, ideal para CI):
```bash
bash scripts/run-e2e-tests.sh
```

Para rodar com o navegador visível ao vivo na tela (inspeção interativa):
```bash
bash scripts/run-e2e-tests.sh --headed
```

Para rodar um arquivo específico:
```bash
bash scripts/run-e2e-tests.sh tests/e2e_ux/test_e2e_journey_creation.py
```
