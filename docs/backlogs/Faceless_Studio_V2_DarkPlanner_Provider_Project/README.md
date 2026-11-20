# Faceless Studio V2 — Integração DarkPlanner como provider plugável

**Status:** proposta de implementação; nenhum código do starter foi modificado. **Escopo:** integração de geração de narração, preservando domínio e casos de uso independentes do fornecedor.

## Objetivo
Conseguir selecionar `voice: darkplanner:<voice-id>` no projeto/canal, gerar áudio por cena, produzir WAV local compatível com o renderer e trocar por `piper:...` sem editar regras do negócio ou `RunRender`.

## Diagnóstico confirmado no starter fornecido
- `renderer/app/studio/application/ports.py` já define `Voice.speak(text, out_path) -> seconds`.
- `renderer/app/studio/adapters/voice_piper.py` implementa a porta e valida silêncio.
- `renderer/app/studio/application/config.py` já resolve `voice` por projeto e registra fabricantes pelo nome.
- `renderer/app/studio/composition.py` registra `register("voice", "piper", PiperVoice)`.
- `renderer/app/studio/application/render.py` invoca `voice.speak` sequencialmente por cena, gera cues e monta `RenderSpec`.
- `renderer/app/studio/adapters/qa_ffmpeg.py` já avalia áudio no vídeo renderizado.

**Não confirmado:** contrato real da API DarkPlanner, SLA, TTS por API, resposta síncrona/assíncrona, SRT, webhooks, permissões de redistribuição e limites de rate. Não inventar endpoints nem propriedades do serviço. Os exemplos da documentação são contratos *internos sugeridos*.

## Documentos
1. [Plano de entrega](PLANO_DE_EXECUCAO.md)
2. [Backlog detalhado](backlog/CARDS.md) e [CSV de issues](backlog/issues.csv)
3. [Arquitetura e pontos de extensão](arquitetura/DESENHO.md)
4. [Contratos internos](contratos/CONTRATOS.md)
5. [Estratégia de testes](testes/PLANO_DE_TESTES.md)
6. [Operação, segurança e rollout](operacao/RUNBOOK.md)
7. [ADR: adapter anti-corrupção](adr/ADR-001-AUDIO-PROVIDER.md)
8. [Checklist discovery API](operacao/API_DISCOVERY.md)

## Ordem de execução
DPA-01 → DPA-02 → DPA-03 → DPA-04 → DPA-05 → DPA-06 → DPA-07 → DPA-08 → DPA-09 → DPA-10 → DPA-11 → DPA-12. `DPA-01` é gate de viabilidade para o adapter real. O restante do core pode ser desenvolvido usando um fake provider.

## Não fazer
Não criar `DarkPlannerService` dentro do core; não chamar API de terceiros de dentro do domínio; não guardar tokens em `Project.config`, logs, uploads ou URLs; não habilitar fallback pago automático; não declarar integração implementada sem teste E2E.
