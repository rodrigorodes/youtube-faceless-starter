# Fidelidade ao protótipo V4/V3

Referência: `docs/backlogs/faceless-visual-evolution 2/prototype-v4-v3/index.html`
e seu `v3.js`. Dados e operações continuam sendo os do produto.

## Estado
Referência: `index.html` + `v3.js` (que redefine `pgHome`, `pgNew`, `pgWizard`, `pgVideo`).
Evidência final: `docs/visual-evidence/run6/` (Início/Criar vídeo/Vídeos/Config) e `docs/visual-evidence/video-after/` (workspace do vídeo, todas as abas) (Chromium headless, `scripts/compare_visual_reference.py`,
referência × produto em 1440 e 390 px, mais estilos computados).

## Alinhado (comparado nas capturas)
- Casca: dark nativo, fonte Inter só como fallback (sem Google Fonts), ícones de menu em glifos, sem toggle de tema, sem breadcrumb.
- Início: hero → "Precisa de você" (só vídeos que dependem do usuário, até 3 + link) → "Primeiros passos" (canal sem vídeo) → "Comece por uma tendência no seu nicho". Praticamente idêntico à referência em 1440 e 390.
- Criar vídeo: divulgação progressiva, resumo à direita; idioma e nota do canal passam a refletir o perfil real.
- Criar canal: página (`/studio/canais/novo`), não modal.
- Configurações: quatro abas como `pgSettings`; Canais é lista de cartões do `ChannelProfile` real (o canal ativo primeiro, excedentes recolhidos). `/studio/configuracoes` abre essa lista. "Avançado" vive dentro de "Conexões & Equipe".
- Vídeos: pills com contagem real (Todos, Para aprovar, Rascunhos, Com falha, Publicados), busca, tabela.

- Criar vídeo: Resumo (Modo/Formato/Voz/Estilo/custo), bloco recolhível "✓ Pronto para produzir" / "Configuração precisa de atenção" com Providers do canal por etapa real, nota do canal, botão por modo (⚡ / 🎬).
- Workspace do vídeo (`/studio/panel/videos/{id}/cenas` e demais abas), conforme `pgVideo`/`v3.js`: cabeçalho (← Vídeos, eyebrow de modo, pills de estado/formato/voz/estilo, Histórico de versões, Ver progresso / Diagnóstico), abas com ponto em Qualidade, Cenas (cena em foco, pills, Desfazer/Refazer, player de narração com ações reais, roteiro completo, dock), Composição (prévia, linha do tempo, Parâmetros), Qualidade (prévia, pontos para revisar, aprovação), Publicação, Fontes (diálogo "Adicionar fonte"), Produção (etapas e custo).

## Diferenças conscientes (dado que o produto não tem)
- Tabela de Vídeos sem as colunas Modo e Cenas (o painel não fornece esses dados); no lugar, "Atualizado".
- Sem botão "Roteiro da demo", sem barra de orçamento e sem selo "Mockup" (dependem de dados ilustrativos).
- Cartões de canal mostram "sem perfil editorial" quando o canal não tem `ChannelProfile`; não há nicho, estilo, YouTube nem providers inventados.
- Workspace: sem cenas (nenhum dos 42 vídeos locais tem), a aba Cenas mostra o vazio do protótipo ("Storyboard integrado" + "Sem cenas."); o storyboard com cenas foi validado renderizando cenas de amostra no Chromium (`docs/visual-evidence/video-after/sample-*.png`), não com vídeo real do banco.
- Criar vídeo só cria o rascunho (não inicia produção), então o texto sob o botão diz isso em vez de "O vídeo será gerado inteiro…". "Estimativa de custo", gradiente de estilo na prévia, "Histórico de versões" (só a versão atual) e músicas/resolução/fps (desabilitados, "Em breve") seguem o que o produto realmente tem.
- O banco local tem dezenas de canais/vídeos de E2E, o que alonga as listas em relação ao mockup de 2–3 itens.

## Validação
- `pytest tests --ignore=tests/e2e_ux`: 2541 passed; 4 falhas já existentes no HEAD, sem relação (`test_contracts_snapshot`, `test_schema_docs`, `test_secrets_hygiene`, `test_publishing::test_preview_page_renders_sidebar_navigation`).
- `tests/test_reference_browser.py`: 4 passed (geometria da casca contra o protótipo no Chromium).
- Testes antigos presos à proposta anterior (breadcrumb, "Continuar de onde parou", cartões de Vídeos, redirect de Canais) foram atualizados ao protótipo V4/V3, com os motivos nos próprios testes.
- Não há afirmação de equivalência pixel a pixel: a conferência foi visual, tela a tela.


## Rodada Fidelity Gate (fonte: `prototype-v4-v3/index.html` + `v3.js`)
`scripts/fidelity_gate.py` renderiza protótipo e app em 1440×1000, 768×1000 e 390×844 e grava, por tela,
texto/campos/estilos computados/overflow/diff de pixels e a imagem lado a lado em `docs/visual-evidence/fidelity/`
(`summary.json`, `<tela>/<vp>-{report.txt,side.png}`). 17 telas × 3 viewports; sem overflow horizontal no app.

Telas portadas ao protótipo nesta rodada: Início, Criar vídeo (painel Personalizar), Vídeos (colunas Vídeo/Modo/Formato/Estado/Cenas/Custo),
Tendências (`pgIdeas`), Desempenho (`pgAnalytics`), Biblioteca (`pgLibrary`: abas, cartões com ✓ Ativo no canal / Vincular ao canal,
diálogo "Criar novo estilo"), Configurações (subtítulo "Canal: …", Canais, Marca & Editorial em dois cartões,
Conexões & Equipe em página única: cartão YouTube + Equipe, Providers externos por tarefa, "Avançado e diagnóstico"), assistente Criar canal (`pgWizard`).

### Exceções funcionais (dado ou backend que o produto não tem)
- Dados ilustrativos do mockup não entram (Mary Celeste, selo "Mockup", orçamento fictício, "Roteiro da demo", números/tendências fictícios).
- Biblioteca: Vozes, Músicas e Modelos de roteiro não têm catálogo; a aba diz isso. Estilos reais usam a paleta real como gradiente; descrição/instrução de arte gravadas em `params.extra`.
- Desempenho: sem gráfico diário (não há série real). Criar vídeo: a duração do painel Personalizar não é enviada ao backend.
- Conexões: "+ Adicionar provider"/"Configurar" não existem no backend; a gestão real de contas Google (vincular/revogar) fica em "Avançado e diagnóstico".
  Equipe: "+ Convidar" leva à página de Equipe; sem organização, mostra texto explícito.
- `.hero` usa `var(--hero)` (gradiente do tema) em vez do literal do protótipo; botão de guia "Roteiro da demo" ausente.
- Alturas de Vídeos/Tendências/Produção diferem porque o banco local tem dezenas de itens reais contra 3 do mockup.
- Pendente de revisão visual fina: abas do vídeo (composição/qualidade/publicação) e Produção & Orçamento ainda têm diferenças de estrutura reportadas nos `*-report.txt`; não declaradas como idênticas.
- Não há afirmação de equivalência pixel a pixel; o diff de pixels do gate é maior que zero em todas as telas por causa de dados reais.

Validação: suíte completa 2545 passed, 4 falhas pré-existentes (as mesmas listadas acima); testes que dependem de Postgres são pulados (`STUDIO_TEST_DSN` ausente).

## Rodada: Criar vídeo (estilo), Configurações (todas as abas) e "+ Nova cena"
- Criar vídeo: estilo visual agora é a grade `.grid3` de `.choice` do protótipo (herança do canal + estilos reais).
- Configurações → Produção & Orçamento: perfil em `.choice`, "Orçamento e saída" (sliders de teto), roteamento por tarefa;
  Resolução/Quadros/mídia/falha de provider/B-roll aparecem desabilitados ("em breve"); alertas soft preservados como campos ocultos.
- Marca & Editorial: adicionados Cor da marca e Fonte/Estilo da legenda (desabilitados, "em breve" — sem campo no perfil real).
- Conexões: `code.mono` e `details.diag` alinhados ao protótipo (CSS legado removido).
- CSS legado `.choice` de `panel_channels` restringido a `.perfis-escolha` (sobrescrevia fonte do protótipo).
- Perfil econômico: `FRUGAL` → `ECONOMY` (valor real do domínio).
- Workspace do vídeo → "+ Nova cena": ação na própria bancada (POST `/script/scenes`, texto-padrão do protótipo, foco e toast), sem ir ao roteiro.
- Exceções funcionais: voz/duração por vídeo não enviadas ao backend; catálogos de voz/estilos/música do protótipo ausentes; "+ Nova cena" validada só com rotas mockadas.

## Rodada VE-08: workspace do vídeo (Vídeos, Storyboard, Mídia/B-roll, Gerar/Renderizar, Progresso, Composição)
- Storyboard: todos os `sceneCard()` na bancada, Desfazer/Refazer completo, B-roll por cena (`POST …/scenes/{id}/broll`), preview real (`GET …/scenes/{id}/asset`), nova cena sem recarregar, modais `<dialog>`.
- Gerar/Renderizar: diálogo "Atualizar esta versão", execução única, cartão de progresso com etapas reais, retoma após reload; página de execução no padrão `tabProd`.
- Composição: trilhas com origem real da mídia e voz, prévia viva dos parâmetros.
- Evidências e divergências: `docs/visual-evidence/ve-08/` (`VE-08-DIVERGENCES.md`, `fidelity-report.md`); testes `tests/ve08` (Playwright, backend simulado).
- Não declarado 100% idêntico; ver D1–D21.
