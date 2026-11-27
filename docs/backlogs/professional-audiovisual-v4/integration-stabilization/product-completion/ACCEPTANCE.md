# Acceptance — critérios de produto e release

Herdar ../QUALITY-GATES.md e ../QUALITY-RUBRIC.md integralmente. >=9,0 por dimensão aplicável e média ponderada sem arredondar; reviewer separado; zero P0/P1 obrigatório aberto. Não usar notas como substituto de execução. Os critérios técnicos não asseguram retenção ou monetização.

| Gate | Prova mínima |
|---|---|
| Integridade | troca base preserva overlays/SFX/ordem/revisão; stale edit 409; erro trim/DB deixa estado anterior; concorrência 2 writers um vencedor; reload e undo/redo |
| Áudio | upload real com licença; timeline editável com 3+ trilhas além de voz quando aplicável; mix-only preview e MP4; áudio sem clipping, alvo projeto, dBTP medido e ducking observável |
| Direção/voz | brief e identidade congelados; shot intent editável por cena; pronúncia/pausas observadas; capability indisponível explícita; alterações seletivas |
| Visual | edição real no browser; posição/alpha/z-index/trim persistidos; PiP vídeo; crossfade/slide/wipe por UI com frames/pixels e duração/sync; templates/motion/pós-processamento observáveis, não apenas filtro string |
| Preview/render | low-res respeita aspect/timeline; cache separado por preset e mesmo plano; preview não substitui final; export final 1080p conforme formato; custos/limites |
| Acervo | tags/pesquisa persistente, escopo canal/projeto, dedup e licença, origem; sem acesso cruzado |
| QA | testes de defeitos reais, findings rastreados, ausência de semântico real = NOT_VERIFIED; re-render seletivo, caps/retry, sem chamada paga; não aprovar automaticamente |
| E2E | fluxo browser desktop/mobile em stack descartável (criar→editar→importar→trilhas→camadas→preview→render→reabrir→regenerar→exportar), casos negativos; Node e Playwright realmente executados |
| Pilotos | 60–90s e 300–480s via Studio; roteiro/seed/versões/revisão/hash; comparar base e REC com mesma mídia/narração/duração quando possível; se rebaseline, não atribuir ganho causal indevido; perfil econômico e equilibrado local se viável; custo API 0, kill switch BLOCKED |
| Regressão | suíte canônica, Node, browser E2E e módulos Playwright no SHA limpo final; XML/log/exit codes/skips separados; nenhum resultado parcial substitui full |
| Humano | operador assiste baseline original e ambos novos pilotos; 6 dimensões >=9 cada (voz, composição, ritmo, relevância, áudio, legenda), notas e problemas por timestamp; sem simulação; aceita ou rejeita opcionais; autorização separada de merge |

Não obrigar atingir melhoria percentual artificial nos benchmarks; reportar regressões reais e justificar/solucionar. Métrica CPU/RSS com método e limites, sincronização medida não inferida, custos reais de API separados de assinatura. Artefatos em diretório exclusivo e manifesto com SHA de código/MP4, ffprobe/ebur128, imagens de referência e logs sanitizados. Se gate falhar, status BLOCKED e correction loop limitado; não baixar limiar. 
