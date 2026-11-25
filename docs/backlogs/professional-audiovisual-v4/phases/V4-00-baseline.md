# V4-00 — Baseline & Stability
Status: CONCLUÍDO TECNICAMENTE / AGUARDANDO REVISÃO HUMANA AUDIOVISUAL. Dependências: Nenhuma.
Relatório de Entrega: [V4-00-BASELINE-REPORT.md](V4-00-BASELINE-REPORT.md)

## Atividades
- [x] V4-00.01 — Mapear módulos e responsabilidades. Identificado monólito modular de 5 módulos em FS-08.01 e V4-00-BASELINE-REPORT.
- [x] V4-00.02 — Validar dependências. Verificados Python 3.12.16, Postgres 16-alpine, FFmpeg 7.1.5 libass e Piper-TTS 1.8.0.
- [x] V4-00.03 — Executar regressão. Executada a regressão canônica RUN-13 no container oficial, complementada por 193 novos testes de métricas, ticks/legendas, integração do coordenador: handlers simulados e jornada real do Studio: Short (100% verdes).
- [x] V4-00.04 — Renderizar piloto de referência. Renderizada fixture técnica (63,52s) e benchmark audiovisual longo: 345,60 segundos (18 cenas documentais, dentro do intervalo exigido de 300–480s).
- [x] V4-00.05 — Medir CPU RAM tempo custo. Métricas extraídas em storage/output/v4_baseline_metrics.json (custo $0.00, CPU total 1.394s incluindo subprocessos filhos, memória desacoplada pai 1,35 GB / filhos 1,63 GB, saídas históricas com IDs estritamente exclusivos).
- [ ] V4-00.06 — Avaliar vídeo e áudio humanamente. Avaliação humana: pendente: Vídeos e frames disponibilizados em storage/output para homologação e revisão do operador.
- [x] V4-00.07 — Mapear capabilities FFmpeg. Mapeados filtros scale, zoompan, libass, afade, amix, loudnorm e limites de reencode.
- [x] V4-00.08 — Identificar limites de contratos. Gaps identificados para V4-01 (ProviderRegistry, multitrack, vídeo externo).
- [x] V4-00.09 — Validar checkpoints e recuperação. Validado fencing CAS, LeaseHeartbeat e recuperação de órfãos sem duplicidade.
- [x] V4-00.10 — Documentar AS-IS. Relatório AS-IS consolidado com matriz de transição e proposta de evolução.

## Aceite
Relatório reproduzível com comandos, métricas, hashes e falhas; nenhuma regressão crítica.

## Execução
Leia MASTER-PROMPT e CURRENT-VS-TARGET. Localize símbolos e testes reais antes de alterar. Documente contratos afetados, riscos e orçamento. Execute tarefas em pequenos commits, com testes de regressão e integração específicos. Use fixtures locais; serviços pagos apenas com aprovação. Atualize UX incrementalmente quando houver mudança visível.

## Rollback e gate
Preserve comportamento anterior por compatibilidade ou flag; documente reversão de dados e cache quando aplicável. Pare se o gate falhar. Entregue comandos, resultados, diff, pendências e decisão GO/NO-GO. Não inicie outra fase sem autorização.

## Prompt
Implemente exclusivamente V4-00 conforme este documento e o MASTER-PROMPT; reconcilie com HEAD, proponha plano antes de editar e comprove o aceite. Não declare sucesso sem evidência.

## Integração com Foundation & Stability
Reusar evidências FS-01/02/04/07 e FS-05/06 quando aplicáveis, conforme [plano](../../foundation-stability/PLAN.md). Conferir SHA, configuração e validade; não repetir campanha sem motivo. Nenhum CI/CD exigido; gate local e baseline real não dispensados.
