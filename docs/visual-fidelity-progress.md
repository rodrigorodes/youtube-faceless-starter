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
