# Regras de arquitetura e implementação

1. **Um único Render Plan canônico.** Não criar `RenderPlanV2` paralelo nem `RenderSpec` novo como fonte de verdade. Evoluir com compatibilidade e versionamento explícito quando quebrar contrato.
2. **Domínio e compilador puros.** Sem subprocess, FFmpeg, Pillow, SDK, HTTP, banco ou acesso a arquivos em `domain/` e na lógica pura do compilador. I/O em adapters.
3. **Um único executor FFmpeg.** Expandir `PlanFfmpegRenderer`; não criar motor concorrente.
4. **Timeline em ticks inteiros.** Respeitar timebase, duração, limites de cena, ordenação e z-order estáveis. Definir regras de overlay sem alterar semântica das tracks antigas.
5. **Base visual contínua.** Toda cena deve ter cobertura base sem lacunas; overlays podem ter intervalos parciais. Rejeitar overlay fora da cena, duração inválida, referências ausentes e conflitos de ordenação.
6. **Compatibilidade por padrão.** Planos antigos devem compilar e renderizar com comportamento equivalente; toda mudança de contrato tem testes de round-trip e migração documentada.
7. **Extensão via portas/adapters.** Providers de stock, IA e upload não entram no domínio; retornar candidatos normalizados com licença, provenance, hash, custo estimado e estado de disponibilidade.
8. **BYOK e custo controlado.** Sem chamada paga implícita; orçamento, aprovação quando necessário, cache e chave idempotente por operação.
9. **Estilo é configuração, não lógica hardcoded.** Reutilizar `visual_style.py`, snapshots, patches e precedência da V3.1; presets devem ter fallback conhecido.
10. **QA não inventa evidência.** Métrica técnica por FFprobe/FFmpeg; avaliação semântica só com provider real. Sem provider => `not_verified`, nunca score fabricado.
11. **Regeneração seletiva versionada.** Alterar uma cena não invalida outras sem dependência; atualizar hash do plano/render, QA e aprovação do novo artefato.
12. **Aprovação humana preservada.** Nenhum caminho de publicação bypassa o gate de QA/aprovação existente.
13. **Mudança pequena e testável.** Uma fase por vez, diffs mínimos, feature flag para comportamento novo, testes unitários + integração com FFmpeg + golden sample.
14. **Não colidir com Faceless Studio V3.1.** Revisar `docs/backlogs/faceless-studio-v31/` antes de tocar estilos, Settings, channel identity ou configuração efetiva.
15. **Segurança e direitos.** Não copiar vídeos de terceiros sem licença/permissão; registrar origem e uso permitido de cada mídia.

## Contratos mínimos sugeridos (design, não implementação existente)
- `Layer`: `id`, `kind` (base/overlay/text), `start_tick`, `end_tick`, `z_index`, `asset_ref?`, `effect_refs?`.
- `MediaCandidate`: `asset_ref`, `source_provider`, `license`, `content_sha256?`, `estimated_cost`, `relevance?`, `provenance`.
- `VisualEvaluation`: `render_version`, `scene_id`, `checks`, `coverage`, `findings`, `provider?`, `evidence_refs`.

**Importante:** antes de adicionar esses tipos, mapear `Track`, `Shot`, `AssetReference`, `QaReport` e `StylePatch` existentes; preferir estendê-los a duplicá-los.

## Adendo VE-07 — UX e operações editáveis
16. Workspace é uma interface sobre os serviços existentes; nenhum segundo pipeline/coordenador.
17. Edições devem ser versionadas, idempotentes e auditáveis; rejeitar atualização concorrente obsoleta.
18. Alterar roteiro, áudio, mídia ou estilo invalida dependências e aprovação de artefato anterior.
19. Distinguir duração estimada da duração de áudio medida; não prometer alinhamento por palavra sem evidência.
20. QA e progresso são server-authoritative; `not_verified` não é `pass`.
21. BYOK, licença, orçamento, OAuth/canal e confirmação de publicação são gates de backend, não apenas UX.
22. UI simples com edição por cena; timeline visual read-only no MVP, sem editor NLE.
