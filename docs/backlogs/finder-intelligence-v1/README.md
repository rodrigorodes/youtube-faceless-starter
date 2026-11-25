# Finder Intelligence V1
Iniciativa irmã de ../professional-audiovisual-v4/V4.1-CONSOLIDATION.md. Status: planejamento, não implementação. Objetivo: reduzir garimpo e identificar oportunidades originais com evidência e incerteza, sem garantir viralização. Mesmo repo/monólito, portas e registry compartilhados, domínio independente do render.
## AS-IS observado em f4a9244
youtube_trends.py busca vídeos recentes com parâmetros PT/BR; trend_priority.py usa views/idade, concorrência fixa 50/80, aderência 95/70 conforme categoria, overlap de tokens e risco por palavras; panel_trends.py, trend_repo.py, workflows/05-trends-daily.json e saved trends existentes. Reconciliar com HEAD antes de alterar. AutoResearch/SourceSnapshot e V2-F3 são compartilhados, não duplicar.
## Entrada operacional
Relatos fornecidos pelo usuário (não verificados): garimpo de inglês para espanhol, scanner até 8 idiomas, pastas e recomendações, canais novos/rápidos, ações sobre vídeo, urgência de produção, ferramentas concorrentes. Não copiar conteúdo nem tratar heurísticas comerciais como fatos do algoritmo.
## Leitura
[Plano e backlog](PLAN.md) · [Compliance](DATA-COMPLIANCE.md) · [Especificação](INTELLIGENCE-SPEC.md) · [Contrato Studio](STUDIO-INTEGRATION.md) · [Prompt](MASTER-PROMPT.md). Fases FI-00–11 propostas; FI-00 bloqueia coleta/métricas reais. POC com fixtures antes de aprovação. Chrome extension P2 após API. Gestão multicanal e SaaS não são pré-requisitos do piloto.
