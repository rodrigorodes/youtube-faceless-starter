# Revisão de arquitetura — Faceless Studio

**Data:** 24/11/2026 · **Baseline:** `main`, `2beb90e` · **Método:** leitura de código,
configuração e testes offline; documentação editada localmente. Execução direta
Superpowers; runtime LangGraph não utilizado.

## Resumo

O projeto já é um **monólito modular funcionalmente amplo**, com domínio, portas,
adapters SQL/mídia, produção persistente, aprovação e publicação nativa. Preservar
essa base é mais proporcional que reescrever frontend/backend ou adotar broker e
microserviços preventivamente.

Prioridades: controles de configuração realmente aplicados, lease/recuperação de
produção, readiness e gates contínuos. A instalação atual serve a um operador
local; tabelas SaaS e seleção de canal não constituem isolamento multi-tenant.

**P0:** nenhum achado demonstrado que exija interrupção imediata no escopo local.
Isso não é certificação de segurança. **P1:** R01–R03.
**P2:** R04–R09. **P3:** R10.

### O que já é uma boa base

- Separação de imports com testes: `tests/test_architecture.py:36–56`.
- Transições de produção CAS, fencing e evento na mesma transação:
  `renderer/app/studio/adapters/postgres/production_repo.py:387–423`.
- Configuração congelada e seleção de providers por run:
  `renderer/app/studio/composition/wiring.py:670–680`.
- Gate de publicação antes do upload, identidade do destino e kill switch no
  executor: `renderer/app/studio/application/publication_execution.py:205–273`.
- Sessão resumable/reconciliação explícita e ausência de retry cego:
  `renderer/app/studio/application/publication_execution.py:1–17`.
- Guard de testes de banco com prova do servidor descartável:
  `tests/conftest.py:25–46,78–107`.

## Critério de classificação

- **Fato:** observado em código/arquivo ou check local; não implica incidente em produção.
- **Hipótese/risco:** consequência condicionada a carga, falha ou modo de uso ainda
  não reproduzido nesta revisão.
- **P0:** perda/exposição crítica demonstrada; **P1:** controle ou progresso
  operacional comprometido; **P2:** confiabilidade/evolução antes de ampliar uso;
  **P3:** manutenção e clareza.
- Esforço estimado: **S** até 1 dia, **M** 2–5 dias, **L** acima disso, incluindo
  testes focados. São ordens de grandeza, não compromisso de entrega.

## Achados priorizados

### R01 — P1 — Flags de contingência não chegam ao renderer via Compose

**Status (2026-11-24): parcialmente endereçado** — `STUDIO_PUBLICATION_ENABLED` agora é encaminhada pelo Compose (default `1`), commit `0c280f3`; as demais flags seguem sem encaminhamento. Evidência original abaixo preservada (descreve o estado antes das correções).

**Fato.** `Settings.from_env()` lê `STUDIO_PUBLICATION_ENABLED`,
`STUDIO_RENDER_PLAN_ENABLED`, `STUDIO_AUTO_RESEARCH`, `STUDIO_TREND_SOURCES` e
`STUDIO_TOKEN_ENV_PATH`; nenhuma é encaminhada no Compose principal. Em especial,
`STUDIO_PUBLICATION_ENABLED=0` colocado somente no `.env` não alcança o executor.

**Evidência:** `renderer/app/studio/composition/settings.py:81–90`;
`docker-compose.yml:44–88`;
`renderer/app/studio/application/publication_execution.py:269–273`;
`tests/test_compose_env.py:40–64` cobre apenas parte das variáveis.

**Impacto:** operador pode acreditar que desativou upload/render/pesquisa sem
efetivamente fazê-lo. Não foi verificada a configuração privada nem efetuado upload.

**Recomendação:** encaminhar explicitamente controles suportados, testar efeito
final com Settings + Compose + dublê do uploader, e manter uma matriz de origem e
defaults. Priorizar publicação antes de adicionar novas flags. Evitar importar
todo `.env` indiscriminadamente no container.

**Esforço/dependências:** S; composição e testes offline. Critério: variável de
contingência chega como falso e uploader não é chamado.

### R02 — P1 — Lease de etapa expira sem heartbeat do worker

**Status (2026-11-24): endereçado** pelo plano `2026-11-24-publication-lease-recovery.md`: heartbeat/auto-cerco do lease, `LOST` sem escrita e reconciliação do `publish` (commits `1c4367e`, `97d77df`, `a5ef144`, `8673022`, `0bd746e`, `8b863c9`, `56c416d`). Limitação D4: handlers não são interrompíveis. Evidência original abaixo preservada.

**Fato.** Coordenador usa lease padrão de 300 s; composição não o sobrescreve.
O handler executa de forma síncrona entre claim e complete. Existe
`renew_lease()` no repositório/porta, mas a busca no código do Studio encontrou
somente as definições, nenhum consumidor. A conclusão exige lease ainda válido.

**Evidência:** `renderer/app/studio/application/production.py:650–661,892–924`;
`renderer/app/studio/composition/wiring.py:670–672`;
`renderer/app/studio/adapters/postgres/production_repo.py:363–381,697–711`.
O uploader admite timeout de até 30 minutos:
`renderer/app/studio/adapters/youtube_publisher.py:103`.

**Impacto condicionado:** etapa acima de cinco minutos pode produzir efeito ou
arquivo e falhar ao concluir com `LOST`; o worker interrompe o laço. Pode exigir
reconciliação/reexecução; não foi demonstrado upload duplicado nem medido o p95 real.

**Recomendação:** renovar lease durante trabalho longo com dono/token atuais,
parar novas ações quando perder posse e distinguir cancelamento de rollback.
Testar relógio/lease vencido e recuperação após efeito concluído. Só ampliar TTL
não resolve pausas indefinidas nem morte de processo.

**Esforço/dependências:** M; repositório já tem renovação. Exige teste de
concorrência em banco efêmero e política de cancelamento dos adaptadores.

### R03 — P1 — Recuperação automática é uma varredura única no boot

**Status (2026-11-24): endereçado** — varredura periódica `recover_orphans` + `_recovery_loop` (`STUDIO_RECOVERY_INTERVAL_SECONDS`, default 60, `0` desliga), commits `8b863c9`, `56c416d`, `bf55860`, `4b758af` (teste de dois `Production`/mesmo banco). Sem advisory lock. Evidência original abaixo preservada.

**Fato.** Lifespan chama `recover_in_flight()` uma vez. A regra exclui run
`RUNNING` com lease vivo; composição não agenda nova varredura. `_enqueue()`
registra falha de submit e retorna, preservando run mas sem agendamento durável.

**Evidência:** `renderer/app/main.py:15–27`;
`renderer/app/studio/application/production.py:601–637,1133–1171`;
`renderer/app/studio/composition/wiring.py:675–680`.

**Impacto condicionado:** reinício rápido antes de expirar o lease pode deixar
run órfão parado após expiração, até resume manual/outro boot. Falha de banco
durante boot também pode deixar a recuperação não realizada.

**Recomendação:** redrive periódico limitado, consultando PostgreSQL e usando o
claim/fencing existentes; testar restart antes/depois da expiração, indisponibilidade
inicial de banco e falha de submit. Manter aprovação humana fora do redrive.
Não é necessário introduzir broker para corrigir essa lacuna.

**Esforço/dependências:** M; coordenar com R02 e métricas de idade da fila.

### R04 — P2 — Healthcheck não representa prontidão do domínio

**Fato.** `/health` sempre devolve HTTP 200 e `status=ok`; `ffmpeg=true` é constante.
Banco indisponível só altera campo JSON. Compose usa `curl -fsS` sem avaliar corpo.

**Evidência:** `renderer/app/main.py:34–36`; `docker-compose.yml:101–105`.

**Impacto:** container pode aparecer saudável enquanto o domínio falha; diagnóstico
de operador não distingue API viva de migração/banco indisponível.

**Recomendação:** separar liveness de readiness; readiness deve verificar
inicialização/schema e recursos locais essenciais com timeout. Não depender de
serviço IA externo para manter processo vivo. Métricas úteis: duração/idade de
etapas, leases, pendências de publicação e disco.

**Esforço/dependências:** S–M; contrato de operação e ajuste posterior do healthcheck.

### R05 — P2 no uso local; bloqueador antes de SaaS — Canal não é tenant

**Fato.** Autenticação global Basic/Bearer cobre o router; vídeo é buscado por ID
sem escopo de organização. Operações de equipe resolvem papel, mas isso não
aplica RBAC a todo recurso de produção. ADR-003 está marcado **Proposto**.

**Evidência:** `renderer/app/studio/api/routes.py:158–182,1106,1853–1864`;
`renderer/app/studio/adapters/postgres/repo.py:256–261`;
`docs/adr/ADR-003-isolamento-por-organizacao.md:3–21`.

**Impacto condicionado:** múltiplos clientes usando a mesma instalação/credencial
não terão isolamento por organização. Não foi constatado vazamento real.

**Recomendação:** preservar uso single-operator declarado. Antes de onboarding de
terceiros, contexto de tenant derivado de identidade confiável, filtros de
repositório, autorização por recurso e testes negativos com dois tenants.
Seleção de canal no navegador não deve decidir autorização. Reutilizar ADR-003
após fechar decisões, sem implantar um sistema de identidade sem demanda.

**Esforço/dependências:** L para multi-tenant completo; decisão de produto,
identidade, migrações/backfill e auditoria. Documentar limite agora é S.

### R06 — P2 — Artefatos gerados e cobertura de CI deixam drift passar

**Fato.** O DDL consolidado contém 41 migrações até 0046, mas há 44 até 0049.
O diagrama gerado omite retornos `RENDERED/AWAITING_APPROVAL → SCRIPTED`.
Schemas de vídeo/cena não contêm campos hoje declarados (`production_mode`,
`broll_enabled`, `broll_note`). CI encontrada só executa higiene/empacotamento.

**Evidência:** `docs/schema/studio.sql:8`;
`renderer/app/studio/adapters/postgres/migrations/0047_channel_preferences_and_production_mode.sql:4–16`;
`renderer/app/studio/adapters/postgres/migrations/0048_scene_broll.sql:1–3`;
`renderer/app/studio/adapters/postgres/migrations/0049_saved_trends.sql:1–17`;
`renderer/app/studio/domain/contracts.py:76–89,102–114`;
`docs/10-arquitetura.md:24–30`;
`.github/workflows/secret-hygiene.yml:18–21`.

**Impacto:** integração ou revisão que confie no schema/diagrama versionado pode
interpretar contrato incompleto. A existência de `tests/test_architecture.py`
não significa que a CI o execute.

**Recomendação:** regenerar saídas juntas com dependências fixadas, usando banco
descartável para introspecção, e incluir gates de contratos, DDL, arquitetura e
testes de banco na CI. Modelo gerado não deve receber tabelas inventadas à mão.
Defaults de Settings/Compose também merecem teste de paridade com exceções explícitas.

**Esforço/dependências:** M; Python 3.12/Pydantic 2.11.4 e banco descartável.
**Limitação do check local:** Python 3.11.9/Pydantic 2.5.0 também introduz diferenças
de serialização (`0`/`0.0`, `$ref`/`allOf`); não atribuir toda divergência ao código.
Os campos ausentes e migrações faltantes são fatos independentes dessa versão.

### R07 — P2 — Limites de execução e cofre pressupõem processo único

**Fato.** Executor compartilhado por produção/render tem limite de threads, sem
controle explícito de admissão na chamada `submit`. Cofre usa lock de thread por
instância e read-modify-replace em JSON. Limpeza de diretórios de trabalho percorre
todos os vídeos, sem identidade de outro processo no adaptador.

**Evidência:** `renderer/app/studio/composition/wiring.py:312,589,675–676`;
`renderer/app/studio/adapters/secret_store.py:31–37,55–65,80–87`;
`renderer/app/studio/adapters/storage.py:140–146`.

**Impacto condicionado:** carga grande pode acumular espera/memória; escalar
processos pode elevar concorrência além do limite esperado e criar competição
por arquivos/segredos. Não há benchmark de saturação nesta revisão.

**Recomendação:** primeiro medir profundidade/idade e impor limite de admissão;
documentar processo único. Antes de réplicas, definir dono dos arquivos, lock
entre processos/serviço de segredos e recuperação que preserve trabalho vivo.
Worker separado só quando os dados demonstrarem necessidade.

**Esforço/dependências:** M para métricas/backpressure; L para operação multi-instância.
Depende de R02/R03 e modelo de implantação.

### R08 — P2 — Backup SQL não é recuperação integral da plataforma

**Fato.** Script faz `pg_dump`, compactação/checksum e restore SQL. Artefatos e
segredos estão em bind de storage/credentials; n8n tem volume próprio e chave de
criptografia externa ao dump. Cofre escreve JSON sem cifra implementada.

**Evidência:** `scripts/backup.py:18–19,52–75`;
`docker-compose.yml:9–10,27,34–35,91–93`;
`renderer/app/studio/adapters/secret_store.py:55–65`.

**Impacto condicionado:** dump íntegro pode restaurar metadados sem mídia ou
tokens necessários. Backup de storage também contém material sensível.

**Recomendação:** runbook com conjunto de recuperação SQL + mídia + cofre +
configuração/chaves + n8n; janela consistente, retenção, proteção e ensaio em
ambiente isolado. Registrar RPO/RTO medidos e verificar referências SQL→arquivo.
Não executar restore sobre banco de uso para “testar backup”.

**Esforço/dependências:** M; espaço de backup, política do operador e destino
descartável. Nenhum backup privado foi aberto nesta revisão.

### R09 — P2 — Capacidade de conteúdo e monetização precisa de evidência específica

**Fato.** Veo só estima e lança `ModelUnavailable`; checker semântico retorna
`not_verified` e é ligado na composição. QA técnico não verifica entendimento
visual/editorial. A documentação antiga de ambiente apresentava Veo entre
providers “em uso”.

**Evidência:** `renderer/app/studio/adapters/image_veo.py:10–17`;
`renderer/app/studio/adapters/quality_semantic.py:18–36`;
`renderer/app/studio/composition/wiring.py:316–320`.

**Impacto:** expectativas incorretas de geração/qualidade; automatizar seleção
baseada apenas em views não demonstra originalidade, direitos ou retorno.

**Recomendação:** conservar o estado “não verificado” na UX; avaliação editorial
com exemplos aprovados/reprovados, rastreio de fontes/licenças e experimento
pequeno de retenção/CTR com tamanho de amostra explícito. Só integrar avaliador
semântico ou outro provider depois de medir valor/custo. Nenhuma contagem de views
garante monetização.

**Esforço/dependências:** M para avaliação editorial; provider novo é trabalho
separado, depende de acesso/preço/licença. Configuração documental corrigida aqui.

### R10 — P3 — Documentação e módulos centrais concentram conhecimento demais

**Fato.** README tratava persistência/editorial/aprovação como futuro. Guia de
extensão referenciava `composition.py`, que hoje é pacote. Router concentra 2.990
linhas; wiring 793; portas 1.189; produção 1.171 na baseline.

**Evidência:** `renderer/app/studio/api/routes.py:1106–1110`;
`renderer/app/studio/composition/wiring.py:282–312`;
`scripts/export_contracts.py:24–28` ainda gera referência antiga ao arquivo.

**Impacto:** onboarding e revisão mais custosos; nomes/linhas copiados entre guias
ficam obsoletos. Contagem de linhas é sinal de concentração, não defeito isolado.

**Recomendação:** mapa de responsabilidades canônico e links a símbolos/arquivos;
separar routers/contratos por área gradualmente quando tocados, mantendo testes de
rotas e regra de dependências. Não trocar stack/introduzir SPA só por tamanho.

**Esforço/dependências:** S para docs (feito nesta revisão); M por extração futura,
dependendo da área. Referência no documento gerado aguarda ajuste do gerador em tarefa de código.

## Sequência recomendada

| Ordem | Entrega observável | Pré-requisito |
|---|---|---|
| 1 | Contingência bloqueia efeito externo em teste; defaults são rastreáveis | R01 |
| 2 | Etapa longa mantém posse; restart rápido volta a progredir sem duplicar efeito | R02 + R03, banco efêmero |
| 3 | Readiness falha quando domínio está indisponível; métricas de pendências | R04 + início de R07 |
| 4 | Contratos/DDL/modelo gerados atualizados e CI detecta nova divergência | R06 |
| 5 | Restore completo comprovado; limites de admissão medidos | R08 + R07 |
| 6 | Avaliação editorial/experimentos; modularização incremental | R09 + R10 |
| Antes de SaaS | Identidade/tenant testados contra acesso cruzado | R05, decisão de produto |

## Documentação entregue

- [README](../../README.md): componentes reais, instalação com auth e prioridades.
- [Configuração canônica](../04-variaveis-de-ambiente.md): origens, defaults
  Python/Compose, flags omitidas, exemplos sem segredos e local/teste/produção.
- [Arquitetura operacional](../11-arquitetura-operacional.md): diagramas, interfaces,
  responsabilidades, dados, filas, integrações, limites e operação.
- [Guia de extensão](../21-extensao.md): caminhos atuais e receita de extensão.
- [Registro operacional](2026-11-24-progress.md): execução/checks/continuidade.

O documento de arquitetura `10` é saída de gerador. A visão operacional foi
separada para não perder conteúdo na próxima geração; não duplica a máquina de
estados nem o modelo completo. Nenhum contrato, aplicação, migração ou Compose
foi alterado. Drift dos artefatos gerados permanece explicitamente registrado.

## Verificações e limitações

Execução local isolada de DSNs, sem servidor, sem Docker, sem acessar `.env`,
conteúdo de credentials, storage ou backups. O ZIP não rastreado preexistente foi
preservado. Não houve deploy, build, commit ou acesso a ambiente remoto.

```sh
env -u STUDIO_TEST_DSN -u STUDIO_DATABASE_URL \
  PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python3 -m pytest -q -p no:cacheprovider \
  tests/test_contracts_snapshot.py \
  tests/test_schema_docs.py::test_committed_ddl_matches_migrations \
  tests/test_schema_docs.py::test_ddl_contains_every_migration_verbatim \
  tests/test_architecture.py tests/test_compose_env.py
```

Resultado: **16 passaram, 2 falharam**, um warning de escape inválido no parsing
de código UI. Falhas: snapshot de contratos e DDL consolidado (R06).
Arquitetura e encaminhamento parcial do Compose passaram; isso não prova que
todas as flags chegam nem que o isolamento multi-tenant existe.

Checks finais de links, referências, exemplos e whitespace estão registrados no
[progresso](2026-11-24-progress.md). Não foram executados testes de banco,
render/FFmpeg, E2E, OAuth, upload, restore, performance ou renderizador Mermaid.
Não há lint Markdown dedicado identificado no projeto. Leitura de testes não
equivale a evidência de que toda a suíte passa.

Consulta documental Context7 em 24/11/2026 confirmou a distinção entre
[interpolação de `.env`](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
e [ambiente do container](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/).
Nenhuma configuração privada foi enviada à consulta.
