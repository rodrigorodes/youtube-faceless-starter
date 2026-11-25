# Revisão documental — acesso, canais, tendências e operação

Escopo: F01/AUT, F02/CFG, F03/TEN e F12/OPS. Execução direta autorizada; runtime LangGraph não utilizado. Foram lidos código, documentação e testes. Nenhum cenário funcional foi executado; todos permanecem **A_PROJETAR**. Achados abaixo são observações estáticas, não resultados de teste. Não foram acessados `.env`, `credentials/`, `storage/` ou `backups/`.

## Achados confirmados por leitura

| ID | Fato e impacto | Fonte | Cenário |
|---|---|---|---|
| REV-OPS-01 | O workflow 05 declara `queries`, mas o nó HTTP não envia `q`; o formatador usa `searchResult.query` ou `ADE Lineup 2026`. Configurar outro termo não basta para associá-lo à busca/tópico pelo JSON atual. | `workflows/05-trends-daily.json:23-45,70` | OPS.C08 |
| REV-OPS-02 | O teste do formatador injeta `query` no resultado fake e não verifica sua transmissão ao endpoint de busca; logo não cobre REV-OPS-01. | `tests/test_workflow_trends.py:40-66` | OPS.C08 |
| REV-OPS-03 | Workflow 03 tem nó chamado “Every 2 minutes” com `parameters={}`; não há intervalo explícito nesse nó. “Execute (Core)” usa autenticação genérica sem `genericAuthType`/associação de credencial nesse nó. Importação não prova agendamento/autenticação funcionais. | `workflows/03-publish-approved.json:4-14,46-77` | OPS.C06 |
| REV-OPS-04 | O webhook de publicação não declara autenticação no JSON. Isto confirma ausência de configuração no artefato, não exposição pública de uma instalação. | `workflows/03-publish-approved.json:15-31` | OPS.C06 |
| REV-OPS-05 | Backup nomeia por segundo e escreve gzip e checksum separadamente. Duas chamadas com mesmo instante/diretório escolhem o mesmo caminho; a escrita sequencial sobrescreve o anterior. | `scripts/backup.py:22-30` | OPS.C03 |
| REV-OPS-06 | Restore usa `docker compose exec postgres` no ROOT; `--yes` não isola o destino. `psql` usa `ON_ERROR_STOP=1`, mas não `--single-transaction`. Falha não comprova rollback integral. | `scripts/backup.py:16-19,48-49,66-76` | OPS.C04 |
| REV-OPS-07 | Backup é dump PostgreSQL; não inclui mídia/cofre em arquivos nem chave de criptografia externa do n8n. Checksum comprova integridade dos bytes, não recuperação integral do produto. | `scripts/backup.py:18,54-61`; `renderer/app/studio/adapters/secret_store.py:31-37`; `docs/17-studio-auth.md:14-15` | OPS.C04 |
| REV-OPS-08 | Janela de tendências usa `.days > 31`: intervalo de 31 dias e 23 horas não é recusado por essa condição, apesar da mensagem “at most 31 days”. | `renderer/app/studio/domain/trends.py:59-62` | TEN.C03 |
| REV-OPS-09 | Upsert de tendências não atualiza `source_url` nem exige `observed_at` mais recente. Reenvio pode atualizar métricas/evidências mantendo a URL original e não tem proteção de frescor nesse SQL. | `renderer/app/studio/adapters/postgres/trend_repo.py:118-131` | TEN.C04 |
| REV-OPS-10 | `/videos` foi removido com 410; documentação de autenticação ainda descreve endpoints legados independentes/não protegidos sem indicar remoção. Evitar interpretar texto antigo como endpoint produtivo utilizável. | `renderer/app/main.py:57-60`; `docs/17-studio-auth.md:6-7,43-44` | AUT.C05 |
| REV-OPS-11 | Guard Studio aceita Basic e worker; ator de equipe é resolvido de `STUDIO_BROWSER_USER`, não da credencial Bearer nem do canal selecionado. Não há identidade individual criada pelo seletor de canal. | `renderer/app/studio/api/routes.py:160-184,1966-1978`; `renderer/app/studio/api/active_channel.py:7-11` | CFG.C08 |
| REV-OPS-12 | `source_url` exige HTTPS e allowlist; `evidence.url` admite HTTP e não passa pela mesma allowlist. Não confundir validação de metadados com verificação factual ou segurança de fetch. | `renderer/app/studio/domain/trends.py:13-36,47-50` | TEN.C01–C03 |
| REV-OPS-13 | Fixture `conn` executa `DROP SCHEMA ... CASCADE` após verificação de prova descartável; a verificação ocorre por conexão física e restringe redirecionamento do DSN. A existência do guard não autoriza executar um runner arbitrário. | `tests/conftest.py:25-46,96-107` | OPS.C05 |

## Riscos/hipóteses ainda não reproduzidos

- **OAuth concorrente:** dois callbacks podem ler o mesmo state antes de sua exclusão e ambos chegar à troca de código. A aplicação faz leitura/validação e só remove state após os efeitos (`renderer/app/studio/application/connections.py:174-219`; fluxo legado em `renderer/app/studio/application/youtube_oauth.py:156-195`). Não afirmar que dois uploads/grants efetivamente ocorreram: Google pode recusar reutilização de code. **AUT.C08** usa barreira e cliente fake.
- **Cofre com múltiplas instâncias/processos:** lock é criado no objeto; `set` faz read-modify-write (`renderer/app/studio/adapters/secret_store.py:31-34,80-87`). Replace evita arquivo parcial, mas não demonstra exclusão mútua entre instâncias. Possível atualização perdida requer reprodução isolada.
- **Par gzip/checksum concorrente:** a interleaving das duas escritas pode deixar par incompatível; apenas colisão de caminho foi confirmada estaticamente. **OPS.C03** diferencia sobrescrita sequencial de corrida.
- **Falha parcial no consentimento de conta:** metadados de conta/canal/grant/vínculo são gravados antes dos tokens, em chamadas separadas (`renderer/app/studio/application/connections.py:197-215`). Falha no cofre pode deixar metadados sem credencial; status é derivado depois. Não assumir atomicidade entre banco e arquivos nem sucesso completo do consentimento.
- **Privilégio atribuído ao worker em Equipe:** a rota resolve ator pelo operador configurado; impacto depende dos vínculos/papéis reais. **CFG.C08** deve caracterizar a política sem alegar escalada reproduzida.
- **Disponibilidade de startup:** testes com dublê cobrem recuperação que falha, mas não equivalem a migração real contra banco inacessível. O fluxo chama `studio.use_cases` antes do bloco que protege a recuperação (`renderer/app/main.py:28-38`); conferir composição ao ampliar o teste, sem inferir que toda exceção possível de boot é absorvida.

## Testes existentes lidos e limites

| Testes | Cobertura observada no código do teste | Limite |
|---|---|---|
| `tests/test_studio_auth.py:28-62` | Credenciais independentes, configuração ausente, Basic/Origin, worker/Origin e rebinding. | Serviço dublê retorna 503 após autenticação aceita; não testa TLS/proxy. |
| `tests/test_channel_preferences_api.py:28-90` | Criação, replay, conflito e chave opcional. | Não comprova UI; teste concorrente identificado em `:208`, requer banco descartável para execução. |
| `tests/test_ideas.py:74-119` | Ordem estável, entrada limite, saída inválida e custo barrado antes do modelo. | Modelo fake; contabilização do caminho sem PaidOperationGuard não representa toda a política de settlement. |
| `tests/test_trends_domain.py:29-76` | Esquema/host, timezone, futuro, janela inválida e lote inválido. | Não cobre fronteira 31d23h nem upsert concorrente. |
| `tests/test_backup.py:14-51` | Roundtrip sintético, corrupção, ausência de checksum, vazio, refusas de restore e exit codes de verify. | Não executa restore íntegro com sucesso nem corrida de nomes. |
| `tests/test_workflow_trends.py:17-73` | Inativo, referências de credencial e formatação via código de nó. | `query` é injetado na resposta fake; não valida requisição completa. Node ausente implica skip. |
| `tests/test_workflow_analytics.py:17-58` | Referências de credencial, colunas reordenadas, vazio e fora da janela. | Código de nó offline, não importação/execução n8n; Node ausente implica skip. |
| `tests/test_workflow_publish.py:39-118` | Hosts, ausência de OAuth YouTube, Core como único executor, configuração fixa, switch e thumbnail. | Autenticação genérica não comprova seleção funcional de credencial; requisição sem auth testa 401, não sucesso worker. |

Outros testes identificados como base no plano — `test_active_channel.py`, `test_effective_config.py`, `test_channel_budget.py`, `test_channel_budget_service.py`, `test_connections_service.py`, `test_main_boot.py`, `test_trend_repo.py`, `test_db.py`, `test_disposable_db_guard.py` — não são apresentados como executados nem como cobertura integral dos novos cenários.

## Limites e integração

- Entrega restrita a quatro capítulos, quatro dados e dois fragmentos; produto, testes e configuração não foram alterados.
- 32 cenários, 24 regras. Catálogo local: `fragmentos/catalogo-operacao.json`; cada `fonte` é a referência primária e as referências complementares permanecem no capítulo/dados.
- Markdown espelha os mesmos campos e textos do JSON válido nos `.yaml`. Ausentes campos de execução (`obtido`, `evidencia`, `data`).
- Não foi usado Git, serviço, provedor ou workflow. Checagens documentais de sintaxe, IDs e correspondência não substituem execução funcional.
- Lacunas de runner comunicadas pelo agente principal (Playwright não declarado, Compose de testes sem prova, exportação JUnit read-only e nome fixo de stack E2E) ficam na integração dele; não foram reproduzidas nem duplicadas como descobertas desta revisão.
- Sem inventário de segredos reais, restore da instalação atual, importação em n8n compartilhado ou validação Google live. Cenários integrados são propostas para clones descartáveis.
