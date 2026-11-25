# Catálogo profissional — V4-05/06
Evoluir VisualStyle/StylePatch, presets e APPLIED_GROUPS; declarar LOADED_ONLY_GROUPS. Identidade congelada por run. Preset = políticas de pacing, shots, paleta, tipografia, voz, música, efeitos, captions, transições e componentes; não pipeline separado.
| Estilo | Mídia e composição | Política |
|---|---|---|
| Documentary Cinematic | stock/acervo, mapa, lower third | ritmo narrativo, áudio contextual |
| Whiteboard Explainer | SVG/2D, personagens simples, diagramas | cortes didáticos e tipografia clara |
| Editorial | recortes, documentos, parallax | evidência e dados visíveis |
| Mystery/History | acervo, texturas, mapas | atmosfera sem prejudicar clareza |
| Finance/Business | gráficos, manchetes autorizadas | dados e datas verificáveis |
| Science/Technology | diagramas, comparações | representação fiel e fontes |
Quick e Professional são perfis do mesmo core: limites de pesquisa, orçamento, qualidade, tipos de assets e ritmo; nunca dispensar originalidade/licença ou gate factual. Primeiro dois estilos, Documentary e Whiteboard; restantes após piloto.
MotionComponent (proposta): template_id/version, parameter_schema, required_capabilities, duration_ticks, source_refs, license, output_type. Biblioteca inicial: título, lower third, mapa, gráfico, timeline, documento/manchete, personagem, diagrama; FFmpeg/SVG primeiro, Remotion como adapter de asset opcional. Verificar legibilidade, contraste, safe areas, integridade factual, export real e sem efeitos simulados.
