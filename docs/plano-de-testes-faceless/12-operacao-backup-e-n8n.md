# 12 — Operação, backup e n8n

**Prefixo dos cenários:** `OPS`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

Renderer recupera trabalho no ciclo de vida; PostgreSQL mantém migrações versionadas. Backup cobre dump do banco, não os arquivos de mídia/cofre. n8n orquestra publicação, coleta analytics e ingestão de tendências; os três JSON são distribuídos inativos. Este plano usa dublês e instâncias descartáveis, sem iniciar serviços nesta revisão.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `OPS.R01` | Startup solicita migração, recupera runs em voo e inicia recuperação periódica quando intervalo > 0; shutdown cancela o laço. Health informa banco indisponível sem necessariamente retornar erro HTTP. | `renderer/app/main.py:15-54` | [OPS.C01](#opsc01) |
| `OPS.R02` | Migrações numeradas são ordenadas; cada arquivo e registro de versão compartilham transação com advisory lock e verificação de versão dentro dela. | `renderer/app/studio/adapters/postgres/db.py:15-30` | [OPS.C02](#opsc02) |
| `OPS.R03` | Backup recusa dump vazio e escreve gzip com checksum; nome tem precisão de segundos. Restore exige --yes e arquivo verificado; usa docker compose no ROOT e não fornece transação única de restauração. | `scripts/backup.py:16-45`, `scripts/backup.py:48-76` | [OPS.C03](#opsc03), [OPS.C04](#opsc04) |
| `OPS.R04` | Testes de banco precisam de prova descartável antes de escrita; fixture conn remove schema studio. Conexão é validada fisicamente e rejeita redirecionamentos de DSN. | `tests/conftest.py:10-46`, `tests/conftest.py:78-107` | [OPS.C02](#opsc02), [OPS.C04](#opsc04), [OPS.C05](#opsc05) |
| `OPS.R05` | Workflow 03 entrega execução ao Core com lease=5400 e max_attempts=3, tem webhook e chega inativo; não deve carregar credenciais YouTube. JSON não provisiona autenticação funcional do worker nem agenda explícita de dois minutos. | `workflows/03-publish-approved.json:4-77`, `workflows/03-publish-approved.json:328`, `tests/test_workflow_publish.py:51-98` | [OPS.C06](#opsc06) |
| `OPS.R06` | Workflow 04 chega inativo, usa mappings vazio até configuração e credenciais separadas; normaliza por nome de coluna e não inventa datas ausentes. | `workflows/04-analytics-daily.json:13-35`, `workflows/04-analytics-daily.json:105-136`, `workflows/04-analytics-daily.json:187` | [OPS.C07](#opsc07) |
| `OPS.R07` | Workflow 05 chega inativo, com projectId vazio e queries vazio; busca não contém parâmetro q. Format Trends usa query recebida ou fallback ADE Lineup 2026 e métrica search_relevance=1, não total de views. | `workflows/05-trends-daily.json:23-45`, `workflows/05-trends-daily.json:70`, `workflows/05-trends-daily.json:154` | [OPS.C08](#opsc08) |

## Resumo dos cenários

Total: 8 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [OPS.C01](#opsc01) | Startup degradado e recuperação sem sobreposição | erro | OPS.R01 | `A_PROJETAR` |
| [OPS.C02](#opsc02) | Migração concorrente e rollback por arquivo | concorrencia | OPS.R02, OPS.R04 | `A_PROJETAR` |
| [OPS.C03](#opsc03) | Backup íntegro, vazio e colisão de nome | concorrencia | OPS.R03 | `A_PROJETAR` |
| [OPS.C04](#opsc04) | Restore recusado e recuperação em clone isolado | borda | OPS.R03, OPS.R04 | `A_PROJETAR` |
| [OPS.C05](#opsc05) | Barrar banco sem prova antes do DROP SCHEMA | erro | OPS.R04 | `A_PROJETAR` |
| [OPS.C06](#opsc06) | Workflow 03 entrega ao Core e trata resultados sem publicar de verdade | feliz | OPS.R05 | `A_PROJETAR` |
| [OPS.C07](#opsc07) | Workflow 04 preserva lacunas e rejeita relatório inválido | borda | OPS.R06 | `A_PROJETAR` |
| [OPS.C08](#opsc08) | Workflow 05 associa termo de busca à tendência | regressao | OPS.R07 | `A_PROJETAR` |

## Cenários

### OPS.C01 — Startup degradado e recuperação sem sobreposição

- **Tipo:** erro
- **Regras:** OPS.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Manter diagnóstico e recuperação periódica quando o banco falha.
- **Pré-condições:** Studio fake injetado antes da importação; recuperação que falha uma vez e depois conclui; sem serviços.
- **Passos:**
  1. Entrar no lifespan com recover_in_flight lançando erro; consultar /health com ping falso.
  2. Simular duas rodadas de recover_orphans mais lentas que intervalo; encerrar lifespan; repetir com intervalo=0.
- **Esperado:** Falha de recuperação não derruba subida; studio_db=unavailable; chamadas periódicas não se sobrepõem no mesmo laço; shutdown é chamado; intervalo zero não agenda varredura.
- **Limitações:** Não comprova recuperação entre processos ou execução real de run.
- **Automação:** camada `mock`; referência `tests/test_main_boot.py:92-147`

### OPS.C02 — Migração concorrente e rollback por arquivo

- **Tipo:** concorrencia
- **Regras:** OPS.R02, OPS.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Aplicar cada versão uma vez e não registrar migração falha.
- **Pré-condições:** Postgres descartável comprovado; diretório temporário com 0001_criar.sql e 0002_falhar.sql sintéticos; duas conexões.
- **Passos:**
  1. Executar migrate simultaneamente nas duas conexões para 0001_criar.sql que cria tabela marcador.
  2. Em uma execução seguinte, incluir 0002_falhar.sql que cria tabela transitória e lança erro SQL; inspecionar catálogo e versões.
- **Esperado:** Versão 0001 aparece uma vez; segunda execução não a reaplica. Falha 0002 reverte sua tabela e sua versão; 0001 permanece aplicada.
- **Limitações:** Não executar migrations no banco configurado do usuário; lock pode aguardar, não há fail-fast neste código.
- **Automação:** camada `local-integrado`; referência `Automação proposta sobre renderer/app/studio/adapters/postgres/db.py:15-30; base tests/test_db.py`

### OPS.C03 — Backup íntegro, vazio e colisão de nome

- **Tipo:** concorrencia
- **Regras:** OPS.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Verificar integridade e caracterizar risco de duas gravações no mesmo segundo.
- **Pré-condições:** Somente write_backup em diretório temporário; dumps sintéticos SELECT 1 e SELECT 2; instante fixo.
- **Passos:**
  1. Gravar b'SELECT 1;' e verificar gzip/checksum; tentar dump vazio e adulterar arquivo.
  2. Gravar dois dumps no mesmo diretório com now=2026-11-19T10:00:00, primeiro sequencialmente e depois com barreira concorrente.
- **Esperado:** Roundtrip recupera bytes; vazio é recusado; corrupção falha na verificação. Código atual gera o mesmo caminho nas duas gravações, com sobrescrita sequencial; registrar se concorrência deixa checksum incompatível, sem presumir integridade atômica do par.
- **Limitações:** Nome colidente é confirmado por leitura; efeito da corrida é hipótese não reproduzida. Não ler backups existentes.
- **Automação:** camada `unit`; referência `tests/test_backup.py:14-37; extensão concorrente proposta`

### OPS.C04 — Restore recusado e recuperação em clone isolado

- **Tipo:** borda
- **Regras:** OPS.R03, OPS.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar restauração acidental na stack atual e validar retorno de falha.
- **Pré-condições:** Primeira etapa com _compose_exec fake e arquivo SQL sintético temporário; etapa integrada somente em cópia descartável com ROOT/Compose isolados e banco confirmado vazio.
- **Passos:**
  1. Chamar main restore sem --yes e depois com arquivo corrompido; contar chamadas ao subprocesso.
  2. Com backup sintético íntegro, simular retorno psql=1 e verificar mensagem; no clone, restaurar tabela marcador com uma linha e conferir SELECT.
- **Esperado:** Sem confirmação/corrompido não chama psql. Retorno 1 não anuncia sucesso. No clone bem-sucedido, linha é restaurada; falha SQL não autoriza inferir rollback integral, pois não há single-transaction.
- **Limitações:** O script real usa cwd=ROOT e docker compose; executar direto no checkout atingiria a stack atual. Checksum válido não prova completude do backup, e dump não inclui mídia/cofre.
- **Automação:** camada `local-integrado`; referência `tests/test_backup.py:40-51 cobrem recusas; restore isolado e falha psql são automações propostas`

### OPS.C05 — Barrar banco sem prova antes do DROP SCHEMA

- **Tipo:** erro
- **Regras:** OPS.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Validar segurança da própria execução dos testes.
- **Pré-condições:** Connection fake com log de SQL; provas sintéticas temporárias; sem DSN do usuário.
- **Passos:**
  1. Fornecer prova ausente, divergente e DSN com múltiplos hosts ou hostaddr.
  2. Repetir com prova válida de 64 hex igual à devolvida pelo fake; examinar ordem de verificação, rollback e liberação.
- **Esperado:** Entradas inseguras geram erro/fechamento sem DDL destrutivo. Conexão válida verifica prova antes de disponibilizar escrita e ajusta autocommit somente depois do rollback.
- **Limitações:** Não autoriza rodar a suíte completa; fixture conn contém DROP SCHEMA CASCADE.
- **Automação:** camada `mock`; referência `tests/conftest.py:25-46,96-107; base tests/test_disposable_db_guard.py`

### OPS.C06 — Workflow 03 entrega ao Core e trata resultados sem publicar de verdade

- **Tipo:** feliz
- **Regras:** OPS.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Validar orquestração, bloqueio e configuração necessária antes da ativação.
- **Pré-condições:** JSON lido offline; runtime de nós com HTTP fake ou n8n descartável sem saída externa; nenhuma credencial real.
- **Passos:**
  1. Confirmar active=false e alimentar Config com lease_seconds=20,max_attempts=99.
  2. Simular Core retornando UPLOADED, IDLE, RECONCILE e erro desconhecido; simular falha de thumbnail.
  3. Inspecionar Schedule Trigger e HTTP Execute/thumbnail para agenda e credencial worker.
- **Esperado:** Config produz 5400/3; switch direciona upload/ocioso/reconciliação e fallback bloqueado; thumbnail não reclassifica upload como novo envio. Identificar pendências do JSON: agenda vazia e autenticação genérica sem associação worker completa; não declarar importação pronta.
- **Limitações:** Nome Every 2 minutes não prova agenda. Webhook não tem autenticação explícita no JSON; não testar em n8n compartilhado nem fazer upload.
- **Automação:** camada `mock`; referência `tests/test_workflow_publish.py:39-118; proposta para validação de agenda/credenciais`

### OPS.C07 — Workflow 04 preserva lacunas e rejeita relatório inválido

- **Tipo:** borda
- **Regras:** OPS.R06
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Normalizar analytics sem fabricar métricas ausentes.
- **Pré-condições:** Nó de código offline; video_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; youtube_id=oNQ2KN37sfQ; janela 2026-11-01 a 2026-11-14.
- **Passos:**
  1. Entregar headers views,day,likes e linha [7,2026-11-03,2].
  2. Entregar rows vazio e depois linha de 2026-10-31; confirmar mappings vazio e active=false na distribuição.
- **Esperado:** Primeiro caso produz views=7, likes=2 somente para 03/11; vazio produz zero linhas; fora da janela gera erro. Nenhuma chamada externa com configuração ainda vazia; credenciais readonly e studio_worker são referências separadas.
- **Limitações:** Runner de código não comprova execução n8n nem acesso Google; views desconhecidas não viram zero.
- **Automação:** camada `mock`; referência `tests/test_workflow_analytics.py:17-58`

### OPS.C08 — Workflow 05 associa termo de busca à tendência

- **Tipo:** regressao
- **Regras:** OPS.R07
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Expor diferença entre configuração de termos e requisição HTTP real.
- **Pré-condições:** Cópia em memória do JSON; projectId sintético; queries=[Energia solar]; fake de resposta YouTube sem campo query.
- **Passos:**
  1. Inspecionar parâmetros do nó Search YouTube e executar Format Trends com um resultado de vídeo abcdefghijk.
  2. Repetir com projectId vazio e com items vazio; conferir até cinco evidências e metric_value.
- **Esperado:** Caracterização atual: requisição não contém q e Format Trends usa ADE Lineup 2026 quando query não vem na resposta; metric_value=1 representa search_relevance, não views. Projeto vazio/sem itens não produz ingestão. Critério funcional pendente: termo configurado deve chegar à busca e ao tópico, sem fallback indevido.
- **Limitações:** Falha funcional deduzida do JSON, não reproduzida live. Teste existente injeta query na resposta fake e não cobre montagem da busca.
- **Automação:** camada `mock`; referência `tests/test_workflow_trends.py:17-25,40-73; ampliação proposta para requisição completa`

## Resumo do capítulo

8 cenários GC, todos A_PROJETAR e não executados. Inclui startup, migração concorrente, backup/restore, segurança da suíte e os três workflows. Restore real só em clone descartável explicitamente isolado; o script atual aponta para a stack do ROOT.
