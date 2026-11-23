# VE-08 — Divergências: protótipo v4-v3 × workspace de vídeo real

Fonte única: `docs/backlogs/faceless-visual-evolution 2/prototype-v4-v3/{index.html,v3.js}`.
Regra: UX = protótipo; backend real = autoridade de dados, persistência, geração e render.

## Inicial (auditoria antes do VE-08)
| # | Área | Estado encontrado | Impacto |
|---|------|-------------------|---------|
| I1 | Storyboard | Seletor de cenas + uma cena em foco (JS legado), ids `seletor-cenas`/`cena-em-foco` | Violava VE-08.1 (cards completos na mesma bancada) |
| I2 | Undo/Redo | Histórico só do texto da cena em foco | Mídia, B-roll, adicionar, excluir e reordenar não eram desfeitos |
| I3 | Mídia/B-roll | B-roll só existia numa cena em foco; mídia sem preview real; sem endpoint de B-roll | Não persistia por cena |
| I4 | Nova cena | Ação na bancada, mas recarregava a página | VE-08.4 exige sem recarregar |
| I5 | Gerar/Renderizar | Link para a página de produção; sem confirmação de impacto, sem progresso na bancada | VE-08.5/6 |
| I6 | Progresso | Página `production-runs/{id}` no layout antigo (`.act-card`) | VE-08.7 |
| I7 | Composição | Já no layout do `tabComp`, mas trilha de mídia dizia "com mídia", sem voz na trilha de narração, sem prévia viva | VE-08.8/9 |
| I8 | Vídeos | Já alinhado (0 diferenças de estilo; texto/alturas divergem só por dado real) | — |

## Final (resolvido)
- I1–I4: `_scene_card` reproduz `sceneCard()`; `#storyboard-cards` traz **todas** as cenas, na ordem do roteiro, com controles independentes (`panel_video_workspace.py`, `panel_video_storyboard_js.py`).
- I2: Desfazer/Refazer por snapshot (≤30) cobre texto, prompt, mídia, B-roll, adicionar, excluir e reordenar; edição nova invalida o Refazer. A reconciliação com o backend usa os endpoints existentes.
- I3: novo `POST /studio/videos/{id}/scenes/{scene_id}/broll` (`{enabled, note≤200}`) e `GET …/scenes/{scene_id}/asset` (preview do asset real, restrito à raiz de armazenamento).
- I4: nova cena sem navegar nem recarregar; numeração, duração e contagem do dock atualizadas; persiste (POST `/script/scenes`).
- I5/I6: `#btn-render` abre o diálogo "Atualizar esta versão" (`<dialog>` nativo), inicia **uma** execução (`Idempotency-Key`, clique repetido travado), mostra `#progress-card` com etapas reais e retoma após reload sem iniciar outra.
- I7: trilha de mídia usa a origem real do asset ("Arte IA", "Imagem stock", "Vídeo stock", "sem mídia"); narração mostra a voz; prévia da legenda segue os parâmetros antes de salvar; estados vazios honestos.
- I6: página de execução portada para `tabProd`.

## Divergências que permanecem (preservadas de propósito)
Cada linha: componente · diferença · motivo · impacto · correção necessária.

| # | Componente | Diferença | Motivo | Impacto | Correção necessária |
|---|-----------|-----------|--------|---------|---------------------|
| D1 | Storyboard | O v3 mostra seletor + 1 cena em foco; o app mostra todos os cards, com o cabeçalho do `tabScenes` base ("Storyboard integrado") | VE-08.1 manda cards completos; os dois textos são do protótipo (v3 sobrescreve `tabScenes`) | Visual: mais alto que o v3 | Nenhuma (decisão do pedido) |
| D2 | Cena › narração | "Áudio real da cena: gerado pelo estúdio, não simulado." no lugar de "Simulação visual, sem áudio real." | O áudio é real | Texto | Nenhuma |
| D3 | Dock/Impacto | "estimativa de custo não disponível" no lugar de "estimativa US$ 0,26" | Não há estimador de custo por vídeo | Texto | Estimador no backend |
| D4 | Mídia | Só dá para **trocar** a mídia, não remover | Backend não desvincula asset | Desfazer de "mídia nova → sem mídia" mantém a mídia e avisa | Endpoint de desvínculo |
| D5 | Texto/Prompt | Editar texto ou prompt limpa a mídia (e invalida o áudio) da cena | `_persist_scenes` limpa o vínculo da cena editada; a UI espelha | Igual ao backend | — |
| D6 | Edição | Só em IDEA/SCRIPTED com roteiro versionado; fora disso controles `disabled` com `title` explicativo | `_require_script_editable` | Vídeos em produção/aprovados ficam somente leitura | — |
| D7 | Modal de mídia | Abas "Do canal" e "Meus arquivos" mostram estado vazio honesto | Sem backend de biblioteca/upload | Abas sem conteúdo | Endpoints de biblioteca e upload |
| D8 | Modal de mídia | "Stock" busca candidatos reais (`/media/candidates`); sem chave do provedor mostra indisponível | Dado real | — | — |
| D9 | Histórico da voz | Só leitura, sem "Restaurar"/"Ouvir versão" | Sem backend para restaurar geração | Botão ausente | Endpoint de restauração |
| D10 | B-roll | Persiste e aparece na trilha, mas não altera o render | O compilador de render não consome B-roll (fora do escopo: "não mexer no core de render") | Metadado | Compilador consumir B-roll |
| D11 | Dock em andamento | "⚡ Produção em andamento…" no lugar de "Piloto automático trabalhando" | O app tem modos Diretor/Piloto | Texto | — |
| D12 | Progresso | Barra = etapas concluídas ÷ total; sem percentual textual | Não inventar percentuais | — | — |
| D13 | Execução (subagente) | Subtítulo com etapas reais; pill "Execução: …"; "!" (WAITING_HUMAN) e "×" (CANCELLED); linha "Etapa N de M"; 3 botões de retry em FAILED; sem pills de estilo/voz; custo por etapa "não medido"; Produção só via "Ver progresso"; botões do cabeçalho fora do `.row` | Mecanismos e dados reais existentes | Pequenas diferenças | Custo por etapa no `usage` |
| D14 | Composição | Música mostra "bpm · seed" (não nome/volume/ducking); Volume e Ducking `disabled` "Em breve"; Resolução/FPS fixos; Estilo "Destaque por palavra" e Transição "Deslizar" `disabled`; "Estilo visual" só leitura | Estilo real só tem bpm/seed; motor tem 25 fps e resolução fixas | Controles do protótipo sem efeito não fingem efeito | Suporte no motor/estilo por vídeo |
| D15 | Composição | Extras do app: "Distância da base", BPM, seed, "Cores da legenda" (`details`), "Salvar composição" e "Ver detalhes técnicos da composição" (`details`, plano persistido) | Parâmetros e plano **reais** (`style-patch`, `composition_view`) | Progressive disclosure que o protótipo não tem | Decidir se o plano técnico sai desta aba |
| D16 | Composição | Prévia sem gradiente do estilo/emoji (usa `var(--panel3)` e 🎞️) | Sem thumbnail renderizável por vídeo | Visual | Thumbnail real do 1º frame |
| D17 | Composição 390px | O protótipo estoura a largura (431 > 390) por causa das trilhas `nowrap`; o app não (`min-width:0` em `.two > *`/`.scene > *`) | Bug do protótipo não reproduzido | Mais correto que a referência | — |
| D18 | Vídeos | 44 vídeos reais × 3 do mockup; "Mockup · dados ilustrativos" e "Roteiro da demo" não entram | Dado real | Altura/texto | — |
| D19 | Dados | Nenhum dos 44 vídeos reais tem roteiro (`GET /script` = 404): o storyboard real só foi exercitado com o backend simulado (`tests/ve08/harness.py`) | Banco local | Sem verificação ponta a ponta com Postgres (sem `STUDIO_TEST_DSN`) | Rodar `tests/ve08` + testes de banco com DSN |
| D20 | Testes legados | `tests/test_video_storyboard_v3.py` e `tests/test_scene_broll_v3.py` afirmavam seletor/cena em foco/ids antigos; reescritos para o protótipo | VE-08: teste que contradiz o protótipo está errado | — | — |
| D21 | e2e_ux | `tests/e2e_ux` (contra o app em execução) falha em `#btn-criar-canal` (Configurações → canais), de uma rodada anterior, fora do VE-08 | Teste desatualizado de outra tela | — | Atualizar esses e2e |
