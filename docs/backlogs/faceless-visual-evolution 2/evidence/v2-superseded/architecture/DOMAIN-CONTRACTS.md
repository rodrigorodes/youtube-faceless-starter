# Modelo, contratos e fronteiras

Status: design conceitual. Adaptar aos tipos reais; não criar tabela/DTO duplicado por semelhança de nome.

## Mapa de identidade
| Conceito | Base existente | Regra proposta |
|---|---|---|
| Conta | organizations | Fronteira de propriedade e autorização |
| Usuário | users + memberships | Participação e papel owner/editor/reviewer/viewer |
| Canal editorial | projects + channel_profiles (1:1) | Usar project_id e profile_id explicitamente na borda |
| Destino YouTube | youtube_channels + grants + authorizations | Independente de usuário do produto |
| Vídeo | videos.project_id | Um canal editorial por vídeo no MVP |
| Cena | scenes + RenderPlan | ID estável; índice não é identidade |
| Execução | production_runs + stage_executions | Processo sobre snapshot de entrada |
| Versão editorial | scripts/revisões existentes + extensão a mapear | Não confundir com run_id ou render_id |
| Artefato | render_jobs/plan_artifacts/assets | Referência imutável ao conteúdo gerado |
| Publicação | publications/publication_intents | Não criar segundo registro da mesma publicação |

Membership atual é por organização. O MVP pode dar acesso a todos os canais da conta conforme papel. Acesso restrito por canal é extensão posterior explícita. `workspaces` não vira nova camada obrigatória de produto.

## Precedência e snapshots
Reusar effective_config: padrões do sistema/conta → perfil do canal → overrides do vídeo → overrides de cena suportados. Esta cadeia é alvo; mapear precedência real V3.1 antes de alterá-la. Snapshot guarda referências de versão e configuração resolvida, nunca segredos. Mudança de canal não re-resolve run existente. Retry/resume usam entradas congeladas; regenerate inicia nova execução. Edição durante run cria revisão posterior; resultado antigo só pode ser associado à sua revisão, nunca promover a revisão nova como pronta.

## Contratos conceituais
```text
VideoWorkspaceView {
 video_id, project_id, channel_profile_id, revision, permissions,
 content_state, production_state, review_state, publication_state,
 selected_scene_id?, scenes[], current_render?, last_valid_render?,
 effective_config_summary, budget_summary, pending_actions[], capabilities
}
EditScene {video_id, scene_id, expected_revision, operation, payload, idempotency_key}
EditResult {revision, affected_scene_ids[], stale_artifacts[], next_actions[]}
PlanGeneration {video_id, expected_revision, scope, requested_capabilities, max_cost}
GenerationQuote {quote_id, revision, expires_at, estimated_cost?, cost_status,
 affected_scene_ids[], selected_provider_summary, changes_requiring_consent[]}
ConfirmGeneration {video_id, expected_revision, quote_id, approved_limit, idempotency_key}
ApproveRender {video_id, expected_revision, render_id, checksum}
ConfirmPublication {video_id, expected_revision, render_id, checksum,
 youtube_channel_id, metadata_snapshot, intent_id, idempotency_key}
RestoreRevision {video_id, source_revision, expected_revision, idempotency_key}
```
Actor/conta são derivados da sessão. Resposta deve informar permissão, mas servidor valida cada comando de novo. Nomes de endpoints são deliberadamente omitidos: inventariar os atuais antes de adicionar rotas. IDs de quote/intenção não substituem verificação de escopo e expiração.

## Concorrência e idempotência
- expected_revision divergente: conflito, nenhuma alteração parcial.
- Idempotency key vinculada ao actor/conta/recurso/tipo e hash do payload; mesmo payload repete resultado, payload diferente é conflito.
- Mutação e invalidação na mesma transação; execução via outbox/coordenação existente.
- Finalização verifica revisão/snapshot de origem. Duas abas não sobrescrevem silenciosamente.
- Reserva financeira antes de chamada paga; concorrência não pode exceder limite. Estado UNCERTAIN não dispara nova cobrança sem reconciliação.
- Snapshot aprovado precisa corresponder ao render/checksum/QA atual. Checar no comando e no worker antes do efeito externo.
- Worker de publicação fixa intenção imutável. Edição posterior não modifica upload em andamento; se ainda não iniciou, marcar intenção obsoleta. Registrar exatamente o que foi enviado.

## Portas e adapters
UI → API autenticada → aplicação/coordenador → domínio/ports. Adapters implementam voz, mídia, render, persistência e publicação. Composition root registra implementações. UI consulta catálogo de capacidades normalizado; não conhece SDK. Credenciais resolvidas no adapter por secret reference e escopo da conta. Provider pode fornecer uma ou mais capacidades; suporte a palavra, idioma, formato, custo e licença deve ser explícito.

## Matriz inicial de papéis (proposta)
| Ação | Owner | Editor | Reviewer | Viewer |
|---|---|---|---|---|
| Ler vídeos permitidos | Sim | Sim | Sim | Sim |
| Editar e gerar dentro do limite | Sim | Sim | Não | Não |
| Aprovar versão | Sim | Não | Sim | Não |
| Confirmar publicação | Sim | Não | Não | Não |
| Gerir membros/chaves/limites | Sim | Não | Não | Não |

Mapear regras já existentes antes de aplicar; mudança de comportamento exige testes e migração explícita. Publicador dedicado pode ser evolução; não inferir de “editor”.

## Isolamento antes de clientes independentes
Auditar queries por ownership, downloads, preview, cache, resultados de jobs, bibliotecas, logs e credenciais. Recursos privados devem ser escopados por conta; hash igual não autoriza leitura cruzada. Cache global apenas para conteúdo explicitamente público e com direitos compatíveis. Testar organizações A/B em leituras, mutações, polling, publicação, referências indiretas e URLs. Remover membership deve revogar novas operações e impedir worker pendente de agir sem autorização válida. Não habilitar oferta SaaS enquanto esses gates não passarem.
