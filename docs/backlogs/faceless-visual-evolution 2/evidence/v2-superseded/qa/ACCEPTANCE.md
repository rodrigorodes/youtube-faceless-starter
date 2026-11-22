# Cenários de aceite e validação

Cenários abaixo são exigências para o produto futuro, não testes já aprovados. Para evidências desta entrega veja `../evidence/DELIVERY-VALIDATION.md`.

| ID | Dado / ação | Resultado esperado |
|---|---|---|
| A01 | Conta nova cria canal e vídeo | Sem wizard de equipe; rascunho com defaults |
| A02 | Canais A/B têm vídeos | Listagens e navegação preservam canal; sem mistura |
| A03 | Novo vídeo com roteiro colado | Texto preservado; geração não substitui sem decisão |
| A04 | Muda voz/estilo do canal depois de criar vídeo | Snapshot do vídeo e run não muda |
| A05 | Overrides em vídeo | Canal permanece intacto |
| A06 | Muda texto da cena 3 | Voz/timing/visual dependente ficam stale; IDs restantes mantidos |
| A07 | Troca mídia da cena 3 | Narração preservada, visual/final atualizados conforme cache |
| A08 | Adiciona/reordena/remove cena | Timeline válida, confirmação de remoção e revisão nova |
| A09 | Salva e fecha navegador | Rascunho salvo; job servidor recuperável pelo mesmo vídeo |
| A10 | Duas abas editam mesma revisão | Segunda mutação rejeitada; texto local recuperável |
| A11 | Job antigo termina após nova edição | Artefato vinculado à revisão antiga, nova continua pendente |
| A12 | Restore de versão anterior | Nova revisão; auditoria e aprovação pendentes |
| A13 | Falha de provider | Não perde rascunho; retry não duplica efeito financeiro |
| A14 | Custo desconhecido/limite insuficiente | Não inicia chamada sem política autorizada/reserva |
| A15 | Provider não suporta palavra | UI não oferece alinhamento por palavra |
| A16 | Fallback troca voz ou custo | Decisão explícita; nenhuma mudança silenciosa |
| A17 | QA técnico falha/semântico ausente | Técnico bloqueia; semântico not_verified explícito |
| A18 | Aprova v1, edita v2, tenta publicar v1 pelo caminho atual | Bloqueio servidor; histórico v1 preservado |
| A19 | Troca destino/metadados após confirmar intenção | Intenção obsoleta; confirmação nova |
| A20 | Dois cliques ou timeout de envio | Mesmo resultado idempotente/reconciliação, sem upload duplicado |
| A21 | Vídeo aprovado sem upload | Nunca aparece como publicado |
| A22 | Publicado recebe edição | Publicação histórica preservada; alterações locais explícitas |
| A23 | Usuário B adivinha IDs da conta A | Ler/editar/gerar/preview/download/poll/publicar negados |
| A24 | Viewer/editor tenta comando fora do papel | Bloqueio de backend, inclusive chamada direta |
| A25 | Membership revogado com job pendente | Nova operação e efeito externo revalidados |
| A26 | Assets privados com hash igual entre contas | Cache não concede acesso cruzado |
| A27 | 390/768/1280 px e teclado | Sem overflow da página, foco visível, labels e erros claros |
| A28 | Plano sem overlay e plano multilayer | FFprobe e quadros mostram paridade/janelas corretas |

## Níveis de teste
Domínio: revisão, invalidação, identidade, capacidades, estados e política. Contrato/API: autorização, CAS, idempotência, payloads e erros. Postgres: transações, concorrência, reservas, backfill e escopo. Renderer: golden funcional, cache hit/miss, duração/streams/quadros. E2E: criar, corrigir cena, retomar falha, revisar/publicar com adapter fake. Validação real de YouTube/provider depende de autorização e ambiente, sem chamadas implícitas.

## Métricas propostas
Tempo humano até rascunho (meta ≤60s), ações para trocar mídia (meta ≤3 após abrir vídeo), retomada (≤2 ações desde Início), taxa de conclusão, abandono por etapa, falhas recuperadas, custo previsto/real e taxa de reutilização. Não registrar roteiro ou segredos em telemetria por padrão. Meta não equivale a medição.
