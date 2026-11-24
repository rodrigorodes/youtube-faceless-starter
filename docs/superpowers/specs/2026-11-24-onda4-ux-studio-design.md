# Onda 4 — UX Studio: Reuso da UX V3, Bancada da Cena & Timeline

**Data:** 2026-11-24  
**Status:** Aprovado  
**Contexto:** Evolução do Faceless Studio para produção de vídeos com qualidade profissional (Onda 4 de 6).  

---

## 1. Intenção e Justificativa

As Ondas 1, 2 e 3 entregaram o motor de estúdio profissional:
- `RenderPlan v2` com múltiplos shots por cena (`0050_scene_assets.sql`).
- `CreativeDirector` com briefing editorial tipado e inteligência de mídia multi-provedor Pexels/Pixabay (`0051_scene_media_intelligence.sql`).
- `PacingEngine` com cortes dinâmicos, `AudioDirector` com ducking de música CC0 e `AssSubtitleRenderer` com legendas dinâmicas.

A **Onda 4** conecta essas capacidades de ponta à ponta na interface web do Faceless Studio (UX V3):
1. **Novo Vídeo com Controles Ativos:** Conectar meta de duração real, voz, idioma, perfil de qualidade, preset de pacing (`dynamic`, `balanced`, `cinematic`) e teto de custo orçamentário.
2. **Aba Direção (CreativeBrief):** Exibir e permitir edição/aprovação do briefing de direção criativa antes ou durante a produção do roteiro.
3. **Bancada da Cena & Multi-Mídia:** Interface do storyboard permitindo vincular múltiplos assets por cena (usando a tabela `studio.scene_assets`), definir transição (`cut`, `crossfade`) e duração por beat.
4. **Timeline e Download:** Exibição clara do vídeo gerado, botão direto de download do MP4 aprovado e estados robustos de loading/erro.

---

## 2. Domínios Independentes para Paralelização

A UX pode ser decomposta em 4 módulos independentes com superfícies de arquivo isoladas:

- **Módulo A: Novo Vídeo & Parâmetros Ativos (`api/panel_new_video.py`, `api/routes.py`)**
  - Formulário `Novo Vídeo`: campos reais para `pacing_preset`, `target_duration_s`, `voice`, `budget_cap`.
  - Endpoint `POST /studio/videos`: recebe e persiste esses parâmetros em `VideoSettings` / `VideoConfig`.
  
- **Módulo B: Aba Direção Criativa (`api/panel_video_workspace.py`, `api/panel_video_nav.py`)**
  - Adiciona aba "Direção" na navegação do vídeo ao lado de "Roteiro" e "Produção".
  - Renderiza o card do `CreativeBrief` (`hook`, `visual_direction`, `pacing`, `tone`, `audio_guidance`).
  - Endpoint `POST /studio/videos/{id}/direction`: permite gerar ou atualizar o briefing criativo.

- **Módulo C: Bancada da Cena & Múltiplos Assets (`api/panel_video_storyboard_js.py`, `adapters/postgres/editorial_repo.py`)**
  - Expansão do card da cena no storyboard para exibir lista de assets vinculados (múltiplos shots).
  - Ações para adicionar mídia extra, remover e escolher transição (`cut`, `crossfade`).
  - Endpoints `POST /studio/videos/{id}/scenes/{scene_id}/assets` e `DELETE .../assets/{asset_id}`.

- **Módulo D: Download & Timeline de Entrega (`api/preview.py`, `api/panel_production.py`, `api/routes.py`)**
  - Rota `GET /studio/videos/{id}/download` que serve o MP4 aprovado diretamente como anexo com cabeçalho `Content-Disposition`.
  - Card de entrega com botão destacado "Baixar vídeo (.mp4)".
  - Exibição de resumo audiovisual (música selecionada, ducking ativo, legendas ASS).

---

## 3. Estratégia de Testes

- `tests/test_panel_new_video_active.py`: formulário e submissão com parâmetros ativos.
- `tests/test_panel_direction_tab.py`: aba de direção criativa e persistência.
- `tests/test_panel_scene_multimedia.py`: gerenciamento de múltiplos assets por cena no storyboard.
- `tests/test_video_download_api.py`: rota de download e entrega do MP4 aprovado.
- Regressão completa no contêiner com `scripts/test-container.sh`.
