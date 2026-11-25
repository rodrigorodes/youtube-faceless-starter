# 02 — Canais, configuração e conexões

**Prefixo dos cenários:** `CFG`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

A interface seleciona um projeto como canal ativo, enquanto produção preserva o dono do vídeo e congela configuração criativa por run. Conexões OAuth são entidades distintas do perfil editorial. Equipe possui vínculos organizacionais, mas o principal HTTP continua o operador configurado.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `CFG.R01` | Canal reúne projeto, perfil, revisão, budget e configuração; criação transacional aceita replay da chave com mesmo payload e recusa divergência. Chave ausente é aceita pela API atual. | `renderer/app/studio/application/channel_creation.py:1-9`, `tests/test_channel_preferences_api.py:28-90` | [CFG.C01](#cfgc01), [CFG.C02](#cfgc02), [CFG.C03](#cfgc03) |
| `CFG.R02` | project_id propaga contexto de navegação; vídeo mantém seu projeto proprietário. Canal não é tenant nem fronteira de autenticação. | `renderer/app/studio/api/active_channel.py:1-11`, `renderer/app/studio/api/active_channel.py:50-69`, `renderer/app/studio/api/routes.py:1111` | [CFG.C04](#cfgc04), [CFG.C08](#cfgc08) |
| `CFG.R03` | Estilo do vídeo precede canal e default; patches seguem vídeo > canal > estilo > motor. Snapshot criativo é canônico e não carrega segredos, saldo ou autorização; retomada não resolve configuração novamente. | `renderer/app/studio/domain/effective_config.py:570-655`, `renderer/app/studio/domain/effective_config.py:336-365`, `renderer/app/studio/application/production.py:795-825`, `renderer/app/studio/application/production.py:906` | [CFG.C05](#cfgc05) |
| `CFG.R04` | Preferências incluem modo e formato padrão; limites soft não podem exceder hard. Budget mede canal e global separadamente e nenhum canal afrouxa o teto global. | `renderer/app/studio/application/channel_creation.py:91-153`, `renderer/app/studio/application/channel_budget.py:38-67`, `tests/test_channel_preferences_api.py:151-171` | [CFG.C01](#cfgc01), [CFG.C03](#cfgc03), [CFG.C06](#cfgc06) |
| `CFG.R05` | Conexões separam conta Google, identidade YouTube, grant e vínculo ao perfil; estado exibido deriva do cofre. Revogação de autorização deve afetar somente o vínculo escolhido. | `renderer/app/studio/application/connections.py:197-224`, `renderer/app/studio/application/connections.py:227-276`, `tests/test_connections_service.py:342-362` | [CFG.C07](#cfgc07) |
| `CFG.R06` | Equipe resolve ator pelo STUDIO_BROWSER_USER e vínculo organizacional, aplicando RBAC; o seletor de canal não cria identidade individual. O guard geral também aceita worker. | `renderer/app/studio/api/routes.py:1956-2029`, `renderer/app/studio/api/routes.py:160-184` | [CFG.C08](#cfgc08) |

## Resumo dos cenários

Total: 8 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [CFG.C01](#cfgc01) | Criar canal com preferências e limites | feliz | CFG.R01, CFG.R04 | `A_PROJETAR` |
| [CFG.C02](#cfgc02) | Criação concorrente e replay divergente | concorrencia | CFG.R01 | `A_PROJETAR` |
| [CFG.C03](#cfgc03) | Soft acima do hard e chave ausente | borda | CFG.R01, CFG.R04 | `A_PROJETAR` |
| [CFG.C04](#cfgc04) | Navegar entre dois canais sem transferir vídeo | regressao | CFG.R02 | `A_PROJETAR` |
| [CFG.C05](#cfgc05) | Precedência de estilo e snapshot imutável | regressao | CFG.R03 | `A_PROJETAR` |
| [CFG.C06](#cfgc06) | Gasto de A não é gasto de B | borda | CFG.R04 | `A_PROJETAR` |
| [CFG.C07](#cfgc07) | Vincular, desconectar e revogar autorização isolada | feliz | CFG.R05 | `A_PROJETAR` |
| [CFG.C08](#cfgc08) | Equipe respeita papel do operador e não o canal selecionado | erro | CFG.R02, CFG.R06 | `A_PROJETAR` |

## Cenários

### CFG.C01 — Criar canal com preferências e limites

- **Tipo:** feliz
- **Regras:** CFG.R01, CFG.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Persistir canal completo e preferências sem configuração parcial.
- **Pré-condições:** Postgres descartável comprovado; cliente autenticado sintético; nenhuma chamada de provedor.
- **Passos:**
  1. POST /studio/channels/transactional com name=Canal História, default_mode=diretor, default_format=long, hard_monthly_usd=30, soft_monthly_usd=15 e Idempotency-Key=cfg-criar-1.
  2. Ler perfil e budget; reiniciar somente o cliente e consultar novamente.
- **Esperado:** 201 com projeto/perfil/budget vinculados, modo diretor, formato long, hard 30 e soft 15 persistidos; revisão inicial existente.
- **Limitações:** Testes de API não substituem validação visual do formulário.
- **Automação:** camada `local-integrado`; referência `tests/test_channel_preferences_api.py:28-44; extensão proposta para revisão e releitura`

### CFG.C02 — Criação concorrente e replay divergente

- **Tipo:** concorrencia
- **Regras:** CFG.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Evitar duplicação por duplo envio e detectar chave reutilizada incorretamente.
- **Pré-condições:** Banco descartável; duas conexões independentes e barreira de início.
- **Passos:**
  1. Enviar simultaneamente duas criações name=Canal Replay com Idempotency-Key=cfg-replay-1.
  2. Reenviar a mesma chave alterando name para Outro Canal; contar projetos/perfis/revisões.
- **Esperado:** Envios equivalentes retornam os mesmos IDs sem duplicação; payload divergente retorna 409 e preserva o primeiro canal.
- **Limitações:** Cliente compartilhado não comprova corrida de conexões; usar conexões reais isoladas.
- **Automação:** camada `local-integrado`; referência `tests/test_channel_preferences_api.py:47-77,208; proposta de contagem transacional`

### CFG.C03 — Soft acima do hard e chave ausente

- **Tipo:** borda
- **Regras:** CFG.R01, CFG.R04
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Fixar limites de validação e comportamento real da chave opcional.
- **Pré-condições:** Cliente autenticado com banco descartável.
- **Passos:**
  1. Criar com hard_monthly_usd=30 e soft_monthly_usd=31; repetir com soft=30.
  2. Fazer uma criação válida sem Idempotency-Key; não repetir como se houvesse garantia de replay.
- **Esperado:** Soft maior é recusado sem canal parcial; igualdade é aceita. Criação sem chave retorna 201 conforme contrato atual, sem presumir deduplicação entre pedidos.
- **Limitações:** Ausência de chave é comportamento existente, não recomendação para clientes.
- **Automação:** camada `local-integrado`; referência `tests/test_channel_preferences_api.py:86-90,151-171`

### CFG.C04 — Navegar entre dois canais sem transferir vídeo

- **Tipo:** regressao
- **Regras:** CFG.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Separar contexto visual de propriedade e autorização.
- **Pré-condições:** Canal A=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; B=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb; vídeo V pertence a A.
- **Passos:**
  1. Abrir tendências com project_id=B e seguir para configurações.
  2. Abrir URL do vídeo V a partir do mesmo navegador e examinar links externos e downloads.
- **Esperado:** Links de páginas mantêm B; URL e dados do vídeo continuam derivados de A. Links externos/downloads não recebem project_id. Mesmo operador pode acessar A e B; não alegar isolamento tenant.
- **Limitações:** Verificação do HTML puro não comprova navegação browser completa.
- **Automação:** camada `browser`; referência `tests/test_active_channel.py como base; automação browser proposta`

### CFG.C05 — Precedência de estilo e snapshot imutável

- **Tipo:** regressao
- **Regras:** CFG.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Impedir alterações silenciosas na retomada de um run.
- **Pré-condições:** Estilo válido com music.bpm=100, override de canal=110 e de vídeo=120; repositório de runs descartável.
- **Passos:**
  1. Resolver configuração e iniciar run R; conferir bpm=120 e provenance=video.
  2. Alterar override do canal para 130 e retomar R; criar um novo run sem override do vídeo.
  3. Tentar inserir api_key em documento criativo.
- **Esperado:** R mantém hash e bpm 120; novo run usa 130 com origem channel. Documento com api_key é recusado; nenhum segredo ou saldo integra snapshot.
- **Limitações:** Snapshot criativo não congela autorização, preço ou disponibilidade; testes de domínio não provam transação SQL.
- **Automação:** camada `local-integrado`; referência `tests/test_effective_config.py; automação proposta para retomada baseada em renderer/app/studio/application/production.py:795-825,906`

### CFG.C06 — Gasto de A não é gasto de B

- **Tipo:** borda
- **Regras:** CFG.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Manter escopos de budget sem relaxar teto global.
- **Pré-condições:** Usage fake: A gastou 90 USD, B gastou 5; soft de B=20; teto global configurado=15.
- **Passos:**
  1. Projetar próxima etapa de vídeo de B; consultar resumo de B e global.
  2. Repetir para run sem video_id e tentar configurar soft maior que hard.
- **Esperado:** Projeção de B usa gasto 5 e teto min(20,15)=15; run sem vídeo usa gasto global. Soft inválido é recusado; A não aparece como consumo individual de B.
- **Limitações:** Este cenário verifica projeção, não reserva concorrente nem cobrança real.
- **Automação:** camada `unit`; referência `renderer/app/studio/application/channel_budget.py:57-67; automação proposta com bases tests/test_channel_budget.py e tests/test_channel_budget_service.py`

### CFG.C07 — Vincular, desconectar e revogar autorização isolada

- **Tipo:** feliz
- **Regras:** CFG.R05
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Preservar separação entre perfil editorial e identidades OAuth.
- **Pré-condições:** Repositórios fake com duas autorizações e dois canais YouTube; cofre em memória com tokens sintéticos.
- **Passos:**
  1. Vincular perfil A ao canal YouTube autorizado 1; listar conexões.
  2. Desvincular perfil A e revogar somente autorização 1; reler autorização 2 e remover suas credenciais fake para avaliar status.
- **Esperado:** Vínculo aparece corretamente; desfazê-lo não exclui perfil. Revogação 1 não revoga 2; sem credencial, status de 2 não permanece conectado por mero campo digitado; respostas não incluem tokens.
- **Limitações:** Não comprova efeitos de revogação no Google; usar somente fake.
- **Automação:** camada `mock`; referência `tests/test_connections_service.py:307-340,342-362,374-397`

### CFG.C08 — Equipe respeita papel do operador e não o canal selecionado

- **Tipo:** erro
- **Regras:** CFG.R02, CFG.R06
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Verificar RBAC e tornar explícita a identidade atribuída ao worker.
- **Pré-condições:** Organização fake com operador viewer; depois owner; resolver de ator com spy; serviço de convite fake.
- **Passos:**
  1. POST /studio/panel/equipe/members como Basic com Origin válido tentando convidar teste@example.test.
  2. Repetir como owner e depois Bearer sem Origin; alternar project_id da interface.
- **Esperado:** Viewer é recusado pelo RBAC; owner pode convidar. Resolver recebe o STUDIO_BROWSER_USER configurado também quando o guard aceita Bearer; troca de canal não cria usuário/tenant. Respostas de chave contêm só metadados.
- **Limitações:** Atribuição do worker ao operador é comportamento a caracterizar, não garantia de menor privilégio; sem multi-login real.
- **Automação:** camada `mock`; referência `Automação proposta sobre renderer/app/studio/api/routes.py:1966-2029`

## Resumo do capítulo

8 cenários GC, todos A_PROJETAR e não executados. Abrange criação, preferências, idempotência concorrente, navegação, snapshot, orçamento, conexões e equipe. Banco e navegador exigem ambientes descartáveis.
