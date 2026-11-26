# Achados iniciais da revisão estática

Referência fixa: [develop 0257c04](https://github.com/rodrigorodes/youtube-faceless-starter/commit/0257c045dbff8ef3f78b4f8ffba76b20db226433). Comparação com main: 13 commits, 77 arquivos, +7564/-304. Revalidar no HEAD antes de qualquer alteração. Prioridades são propostas de triagem, não conclusão de auditoria completa.

| ID | Fase | Prioridade | Evidência no código | Ação/gate |
|---|---|---|---|---|
| A01 | 02 | P0 | adapters/voice_kokoro.py: _synthesize_native chama _synthesize_deterministic_pcm, tom 220 Hz; composition/providers.py marca validated=True | Desabilitar oferta validada até fala real inteligível; erro semântico, fallback explícito autorizado Piper; fixture PT-BR real |
| A02 | 02/01 | P1 | adapters/voice_elevenlabs.py: speak lança NotImplementedError com chave; wiring registra classe sem injeção de credencial | Manter indisponível/experimental; API opcional; mocks de contrato e autorização, não executar rede |
| A03 | 04 | P0 | application/render_compiler.py MAX_OVERLAYS_PER_SCENE=1; _validate_overlays só image/graphic; domain/render_plan_builder.py aceita várias tracks | Contratos e compilação consistentes; render de múltiplas camadas e vídeo real |
| A04 | 04/05 | P0 | adapters/render_plan_compiler.py _transition_filter (confirmar nome): crossfade rejeitado; _overlay_filter centraliza sem aplicar novas transformações; LayerExecution não as transporta | Provar pixels/tempo/transição no MP4, não apenas schema |
| A05 | 13 | P0 | tests/test_v4_professional_pilot.py fornece manualmente 75s, 22.5s, 30s, LUFS, drift e US$0.25; application/professional_pilot.py valida parâmetros | Rotular dados sintéticos, retirar alegação de benchmark observado; comparação pareada real |
| A06 | 03 | P1 | domain/audio_dsp.py calcula true_peak_dbtp por pico de amostras; audio_multitrack.py separado do renderer | Integrar áudio ao plano/compilador existente; medir dBTP real via FFmpeg ebur128; não alegar true peak por sample peak |
| A07 | 05/06/07 | P1 | motion_effects, creative_director, captions_exporters e novos helpers precisam de rastreabilidade de consumidores | Demonstrar aplicação de motion, brief editável, exportação e sync reais; limites explícitos |
| A08 | 08/09 | P1 | application/render_engine.py e funções de regeneração em domain/quality.py; wiring não conecta novos serviços | Reusar cache e QA existentes; provar geração seletiva, cancelamento e progresso com I/O real |
| A09 | 10 | P1 | application/studio_workbench.py e domain/studio_workbench.py; diff não altera rotas/storyboard | Integrar comandos de edição existentes; persistência, CAS, reload, undo/redo no browser |
| A10 | 11 | P1 | application/asset_registry.py usa dicionários locais por id/hash | Reusar AssetRepository/Storage/Postgres; dedup por escopo e proveniência, concorrência e restart |
| A11 | 12 | P0 | application/resilience.py: InMemoryOperationStore, timeout por mock_duration_seconds; integração não demonstrada | Não duplicar ProductionCoordinator; garantir persistência de reserva/operação e CAS, timeout medido, restart, reconciliação antes de retry |
| A12 | 01/04/10/11 | P1 | application/media.py só ALLOWED_MIME de imagens, _materialize usa AssetKind.image; GAI-EXECUTION-PLAN pendente | GAI-01/02 importação genérica real de PNG/MP4 com segurança; nenhum SDK Google no core |
| A13 | todas | P0 gate | relatórios por fase declaram GO, testes focados; ausência de regressão canônica no HEAD final confirmada na revisão parcial | Regressão final no checkout identificável; browser pendente e avaliação humana V4-00/13 não presumida |

## Limites
A01–A05, A06 (pico), A10–A12 têm evidências estáticas concretas. A07–A09 e integração geral requerem busca de referências e tracing; ausência de wiring novo não demonstra por si só ausência de consumo indireto. Auditor INT-01 deve localizar símbolos reais e reproduzir falhas; não tomar números de testes/relatórios como medições independentes. Não afirmar violação de segurança ou custo ocorrido sem evidência.
