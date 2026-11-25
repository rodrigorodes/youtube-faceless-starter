# Semantic Media — V4-05/06/09/10/11
Status: proposta. Evoluir portas existentes, não criar registry concorrente.
## Fluxo
CreativeBrief → SceneIntent → ShotIntent (intervalo, entidades, ação, época, lugar, intenção, restrições) → queries multilíngues opcionais → busca autorizada → filtro → ranking → seleção humana/automática condicionada → AssetRef → RenderPlan. Timestamps finais derivados do áudio real; nunca confiar na duração estimada do LLM. Um shot pode ter vários candidatos e um escolhido; troca de candidato não altera roteiro.
## Contratos conceituais
ShotIntent: scene_id, shot_id, start_tick, duration_ticks, visual_intent, entities, era, location, media_types, search_queries, style_snapshot_id.
RankedCandidate: existing MediaCandidate ref, provider_asset_id, source_url, license_evidence_ref, attribution, dimensions, duration_ticks, optional in/out ticks, technical_quality, semantic_evidence, duplicate_group, ranking_version, warnings.
ShotSelection: selected_asset_ref, alternatives, reason, confidence, human_override, revision.
## Algoritmo
Filtros duros: licença compatível, formato, duração, resolução, origem confiável, orçamento e segurança de URL. Desconhecido bloqueia publicação e sinaliza preview. Dedup hash e perceptual hash quando viável; evitar repetição entre shots e canais sem criar regra artificial. Busca paginada e concorrência limitada; somente APIs autorizadas. Primeiro metadados; opcional embeddings multimodais e frames amostrados para rerank top-K. Comparar correspondência factual (época, local, pessoas), estética, enquadramento e diversidade; não apresentar score como verdade. Fallback stock → acervo → mídia manual → geração autorizada e aprovada; representação histórica gerada deve ser distinguível de arquivo real. Nunca baixar terceiros do YouTube sem autorização da plataforma e titulares.
## Aceite
- [ ] Fixture 20s com quatro shots, alternativas até 3 quando disponíveis, licença e motivo; troca individual preserva áudio e demais assets.
- [ ] Casos negativos: época errada, baixa resolução, licença desconhecida, duplicidade, ausência de candidato, timeout, quota, orçamento.
- [ ] Benchmark relevância humana cega (alvo inicial 90% dos shots aceitos, calibrar), custo, latência, repetição; resultados reais e versão do ranking.
- [ ] Preview permite aparar trecho e trocar candidato sem nova chamada LLM; re-render dependências, sem prometer invalidar apenas um segmento se transição cruzar bordas.
