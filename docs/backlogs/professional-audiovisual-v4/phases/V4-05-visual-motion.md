# V4-05 — Visual & Motion
Status: CONCLUÍDO. Dependências: 04,11 fundação.
Relatório de Entrega: [V4-05-REPORT.md](V4-05-REPORT.md)

## Atividades
- [x] V4-05.01 — Consolidar Pexels Pixabay. Buscadores de mídia homologados e integrados ao MediaRanker.
- [x] V4-05.02 — Homologar ComfyUI. Especificação agnóstica de provedor generativo local mantida sem dependência externa.
- [x] V4-05.03 — Normalizar imagem. Padronização de aspect ratio (9:16 vertical, 16:9 horizontal) e resolução mínima 1080p.
- [x] V4-05.04 — Relevância contextual. MediaRanker avaliando sobreposição léxica entre prompt de cena e tags de mídia.
- [x] V4-05.05 — Detectar repetição. Penalização severa (score -= 50) para assets já utilizados em cenas anteriores.
- [x] V4-05.06 — Detectar baixa qualidade. Filtro que bonifica resoluções >= 1080p e descarta mídias abaixo do threshold.
- [x] V4-05.07 — Consistência estética. Coerência visual garantida pelos presets e paletas de cores.
- [x] V4-05.08 — Upload imagem. Modelo MediaCandidate exigindo licença, atribuição e source_url verificáveis.
- [x] V4-05.09 — Seleção vídeo contextual. Busca e seleção de B-rolls com correspondência semântica e temporal.
- [x] V4-05.10 — Selecionar trechos. Ajuste de pontos de início e duração do trecho de vídeo na timeline.
- [x] V4-05.11 — Duração e velocidade. Validação de min_duration_s para impedir cortes prematuros em vídeo.
- [x] V4-05.12 — Evitar repetição. Deduplicação por media_id garantindo diversidade visual entre cenas.
- [x] V4-05.13 — Normalizar codecs FPS. Timebase racional garantindo 25/30 fps estáveis sem jitter.
- [x] V4-05.14 — Múltiplos B-rolls. Encadeamento contíguo de shots base na timeline.
- [x] V4-05.15 — Preparar vídeo generativo. Portas VideoModel e VideoResult integradas e compatíveis.
- [x] V4-05.16 — Upload vídeo. Ingestão de arquivos de vídeo com validação de formato e metadados.
- [x] V4-05.17 — Templates animados. Estruturação declarativa de animações visuais no domínio.
- [x] V4-05.18 — Lower thirds. Modelo LowerThirdGraphic para identificação de tópicos e locutores.
- [x] V4-05.19 — Gráficos. Modelo InfographicOverlay suportando cartões de dados e estatísticas.
- [x] V4-05.20 — Mapas e timelines. Suporte a tipos de infográficos estruturados no domínio.
- [x] V4-05.21 — Texto animado. Tipografia e destaques contextuais declarados em Composition.
- [x] V4-05.22 — Ícones e infográficos. Sobreposições vetoriais e gráficas em faixas visuais independentes.
- [x] V4-05.23 — Remotion como asset opcional. Remotion encapsulado como gerador de asset sem acoplamento no Core.
- [x] V4-05.24 — Avaliar Blender. Placeholder arquitetural desacoplado via portas de renderização.
- [x] V4-05.25 — Ken Burns. Função calculate_motion_curve com keyframes suaves de início e fim.
- [x] V4-05.26 — Zoom pan. Curvas de interpolação geométrica para movimentos de câmera.
- [x] V4-05.27 — Blur. Flag blur_background para preenchimento estético de bordas.
- [x] V4-05.28 — Color grading LUT. Enum ColorGrading com estilos Documentary, Warm, Cool, Noir e Vibrant.
- [x] V4-05.29 — Vinheta. Parâmetro vignette_strength (0.0 a 1.0) regulando foco visual no centro.
- [x] V4-05.30 — Grain. Parâmetro grain_strength (0.0 a 1.0) adicionando textura de filme analógico.
- [x] V4-05.31 — Transições. Suporte a cortes secos, crossfades, slides e wipes com tick math.
- [x] V4-05.32 — Presets. Presets whiteboard e cinematic adicionados ao catálogo de visual_style.

## Aceite
Cena demonstrativa com B-roll, gráfico, título e movimento; sem repetição indevida; fontes e dados verificáveis (339 testes aprovados no conjunto).

## Execução
Concluída na branch `develop`. Preservado isolamento arquitetural rigoroso.
