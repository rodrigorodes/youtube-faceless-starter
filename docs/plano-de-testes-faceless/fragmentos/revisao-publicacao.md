# Revisão documental — publicação, analytics, painel e jornadas

Escopo: F08–F11, execução direta autorizada, sem runtime de workflow. Leitura estática do código, documentação e testes existentes; nenhum teste do produto, serviço, navegador ou publicação foi executado. Alterações preexistentes do produto preservadas. Não foram lidos `.env`, credenciais, storage ou backups.

## Achados confirmados por leitura

1. **Gate compartilhado de publicação.** `renderer/app/studio/application/publication_gate.py:37-60` compara intenção, destino/metadados e revisão renderizada/QA. `renderer/app/studio/application/publication_execution.py:209-213` o aplica antes do upload. A documentação antiga em `docs/15-publicacao.md:79-83` ainda diz que claim legado não exige intenção/gate; o código de `renderer/app/studio/application/publishing.py:130-132` já chama o gate quando os repositórios são fornecidos. Existe divergência documental; o plano não repete a afirmação antiga como garantia atual.
2. **Exceção legada no gate de canal.** `renderer/app/studio/application/publication_execution.py:250-251` permite execução sem verificar autorização quando faltam repositórios de canal/autorizações. O próprio módulo descreve a construção do servidor como diferente em `:236-248`; `tests/test_publication_execution.py:471` preserva o caso legado. Teste montado sem esses repositórios não prova o bloqueio do servidor.
3. **Ambiguidade não é falha segura para retry.** Exceção de uploader vira reconciliação em `renderer/app/studio/application/publication_execution.py:298-304`; falha ao gravar ID confirmado também em `:317-322`. `renderer/app/studio/adapters/postgres/publish_repo.py:316-330` faz rearm com condições no próprio UPDATE, incluindo ausência de sessão/ID/offset/UNKNOWN e lease vencido.
4. **Tratamento de erro de analytics tem fronteira explícita.** O try de `renderer/app/studio/application/analytics_collection.py:185-192` cobre a chamada da porta; `_known_metric` é chamada depois, em `:194-196`, e pode lançar `AnalyticsUnavailable` (`:128-136`). Está confirmado que o serviço não converte ali essa exceção em `CollectionOutcome`; não foi comprovado nesta leitura se o HTTP a traduz adequadamente.
5. **Atribuição ausente é explícita, com texto potencialmente histórico.** `renderer/app/studio/application/analytics_collection.py:106-113` associa ausência de ID remoto a texto “F8 não implementado” e sempre adiciona motivos de brief/packaging ausentes. Isso é comportamento confirmado desse helper, não prova de que tais recursos inexistam em todo o produto.
6. **Teste de navegação contém caminhos condicionais.** `tests/e2e_ux/test_e2e_dom_behavior.py:48-62` só testa o atalho de tendência se existir card visível; `tests/e2e_ux/test_e2e_shell_navigation.py:61-66` só verifica tema se o botão estiver visível. Ausência do elemento pode deixar a interação sem ser exercitada, mesmo com o teste concluído.
7. **Proteção E2E é parcial, não validação universal de isolamento.** `tests/e2e_full/conftest.py:45-50` confere flag e porta 8000; não verifica ali host local nem destino do banco. `:7-8` delimita demo/placeholder/Piper/FFmpeg e ausência de publicação real. Confirmar URL, banco e volumes descartáveis continua sendo pré-condição do ensaio futuro.
8. **Tempos de teste não são SLA.** `tests/e2e_full/test_journey_piloto.py:19` define timeout de 150 s. `tests/test_pilot_video_e2e.py:51-64` gera áudio tonal simulado, e `:139-142` gera imagens de cor sólida. O piloto longo de 180 s é útil tecnicamente, mas não prova locução natural ou qualidade visual editorial.
9. **Feedback tem distinção de resultado.** `renderer/app/studio/api/publicacao_js.py:73-86` só marca `ok: true` em UPLOADED; `renderer/app/studio/api/erro_js.py:60-83` traduz lista 422 e códigos conhecidos. Presença desses helpers não comprova integração correta em todas as telas.

## Riscos e hipóteses a verificar, sem declarar bugs reproduzidos

- **Reconciliação após mudança de canal:** `ReconcilePublication.execute` obtém token e chama reconcile (`renderer/app/studio/application/publication_execution.py:372-382`) sem repetir o gate completo do upload. Investigar mudança de destino entre upload e reconciliação; não concluir envio ao canal errado sem analisar adaptador/sessão. Relacionado a PUB-10.
- **Resposta inválida na coleta:** verificar se a fronteira descrita no achado 4 resulta em resposta HTTP adequada ou 500. ANA-06 define o comportamento desejado e não afirma correção existente.
- **Repetição concorrente de coleta/rearm e edição em duas abas:** idempotência sequencial e tradução de “stale” não demonstram atomicidade de toda a jornada. ANA-03, PUB-11 e UX-08 propõem ampliar cobertura.
- **Acessibilidade e layout:** ARIA, ausência de overflow nas páginas atuais e Escape no diálogo não demonstram foco, leitores de tela, contraste ou todas as áreas em zoom. UX-06/07 propõem ensaio completo das ações essenciais.
- **Carga:** propostas de 2 s para leitura, 900 s para long e 25% para regressão são limites exploratórios, não capacidade observada; calibrar com hardware, versões, amostra e carga registrados. E2E-07/08 não prometem percentis de render com três amostras.

## Testes existentes localizados

| Área | Referências | Alcance / limite |
|---|---|---|
| Aprovação e preview | `tests/test_publish_api.py:51-98,196-292` | Revisão, QA, CSP, reabertura; API local não prova uso real do player. |
| Intenção e privacidade | `tests/test_publication_policy.py:55-99,130-199`; `tests/test_publication_api.py:94-124` | Contratos offline; não valida YouTube live. |
| Upload/reconciliação | `tests/test_publication_execution.py:266-716` | Fakes de upload, gates, retry e wiring; não prova quota/rede remota. |
| Claim/lease | `tests/test_publication_resilience_repo.py:106-244`; `tests/test_publication_rearm.py:34-46` | Inclui concorrência de retry e CAS; rearm concorrente é ampliação proposta. |
| Analytics | `tests/test_analytics_collection.py:111-205,271-282`; `tests/test_analytics_repo.py:104-208`; `tests/test_analytics_dashboard.py:179-372` | Prontidão, persistência e agregação; circuito publicação→coleta é ampliação. |
| Alertas | `tests/test_alerts_p06.py:17-111` | Estado passivo e metadados; não health check ativo. |
| UI | `tests/e2e_ux/test_e2e_shell_navigation.py:22-66`; `tests/e2e_ux/test_e2e_responsive.py:16-94`; `tests/e2e_ux/test_e2e_dom_behavior.py:11-62` | Browser previsto; caminhos condicionais e acessibilidade parcial. |
| Jornadas | `tests/e2e_full/test_journey_inicio.py:26-57`; `tests/e2e_full/test_journey_piloto.py:88-158`; `tests/e2e_full/test_journey_diretor.py:29-92` | Stack isolada e parada antes da publicação. |
| Coordenação/piloto longo | `tests/test_production_coordinator.py:133-331,521-580`; `tests/test_pilot_video_e2e.py:68`; `tests/test_longform_480s.py:1-24` | Estado e artefatos; roteiro 480 s offline não equivale a render E2E 480 s. |

## Entrega e limites

- Quatro capítulos e quatro arquivos de dados: PUB 12, ANA 8, UX 8, E2E 8 = **36 cenários**, todos `A_PROJETAR`.
- **22 regras**: PUB 6, ANA 6, UX 5, E2E 5; catálogo local em `catalogo-publicacao.json`, funcionalidades F08–F11.
- Markdown contém o mesmo registro JSON dos dados YAML (JSON é subconjunto de YAML), preservando todos os campos sem divergência de conteúdo.
- Publicação real só poderá ser ensaio futuro em conta de teste autorizada; plano prioriza mock/local isolado.
- Nenhuma conclusão de teste aprovado, desempenho medido ou comportamento reproduzido deriva deste documento.
