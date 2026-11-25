# 01 — Acesso e segurança

**Prefixo dos cenários:** `AUT`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

O roteador aplica guard de host/origem e autenticação Basic ou Bearer antes dos casos de uso. Não há sessão individual por canal. OAuth guarda tokens no cofre e devolve metadados; testes devem usar somente identidades e segredos sintéticos.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `AUT.R01` | Studio exige usuário, senha e token distintos e não vazios; usuário não contém dois-pontos. Configuração inválida retorna 503; credencial ausente/incorreta retorna 401. | `renderer/app/studio/api/routes.py:160-184` | [AUT.C01](#autc01), [AUT.C02](#autc02), [AUT.C04](#autc04) |
| `AUT.R02` | Host deve estar permitido. Basic em mutação exige Origin da mesma origem; Bearer rejeita qualquer cabeçalho Origin. O worker não representa um tenant nem um papel de menor privilégio. | `renderer/app/studio/api/routes.py:117-131`, `renderer/app/studio/api/routes.py:176-184`, `renderer/app/studio/api/routes.py:1111` | [AUT.C01](#autc01), [AUT.C03](#autc03), [AUT.C04](#autc04) |
| `AUT.R03` | Consentimento verifica state, validade e PKCE antes da troca; respostas públicas não incluem tokens. O state é removido após a conclusão, sem consumo atômico visível no caso de uso. | `renderer/app/studio/application/youtube_oauth.py:153-196`, `renderer/app/studio/application/connections.py:171-224` | [AUT.C07](#autc07), [AUT.C08](#autc08) |
| `AUT.R04` | Cofre de arquivos valida escopo/chave, grava via replace com diretório 0700 e arquivo 0600; lock é por instância. Listagem externa deve conter nomes/metadados, nunca valores. | `renderer/app/studio/adapters/secret_store.py:24-108` | [AUT.C06](#autc06), [AUT.C08](#autc08) |
| `AUT.R05` | Rotas legadas /videos retornam 410; /health é independente da autenticação Studio e informa studio_db. | `renderer/app/main.py:52-60` | [AUT.C05](#autc05) |

## Resumo dos cenários

Total: 8 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [AUT.C01](#autc01) | Basic e worker válidos permanecem independentes | feliz | AUT.R01, AUT.R02 | `A_PROJETAR` |
| [AUT.C02](#autc02) | Configuração incompleta falha fechada | erro | AUT.R01 | `A_PROJETAR` |
| [AUT.C03](#autc03) | CSRF de mutação e separação browser/worker | borda | AUT.R02 | `A_PROJETAR` |
| [AUT.C04](#autc04) | Host malicioso e Basic malformado | erro | AUT.R01, AUT.R02 | `A_PROJETAR` |
| [AUT.C05](#autc05) | Saúde pública e remoção do legado | regressao | AUT.R05 | `A_PROJETAR` |
| [AUT.C06](#autc06) | Cofre sintético valida caminho e protege valores | feliz | AUT.R04 | `A_PROJETAR` |
| [AUT.C07](#autc07) | Callback inválido não troca código nem revela token | erro | AUT.R03 | `A_PROJETAR` |
| [AUT.C08](#autc08) | Dois callbacks para o mesmo state | concorrencia | AUT.R03, AUT.R04 | `A_PROJETAR` |

## Cenários

### AUT.C01 — Basic e worker válidos permanecem independentes

- **Tipo:** feliz
- **Regras:** AUT.R01, AUT.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Distinguir autenticação aceita de indisponibilidade do serviço.
- **Pré-condições:** Aplicação de teste com make_router(lambda: None, lambda: False), host localhost:8000 e credenciais sintéticas do conftest.
- **Passos:**
  1. GET /studio/videos/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa com Basic test-user:test-browser-password e depois Bearer test-worker-token, sem Origin.
  2. Trocar senha pelo token e token pela senha.
- **Esperado:** As duas credenciais válidas chegam ao serviço e retornam 503 neste dublê; trocadas retornam 401 com desafio Basic.
- **Limitações:** 503 neste arranjo não significa autenticação recusada; não testa banco.
- **Automação:** camada `mock`; referência `tests/test_studio_auth.py:32-37`

### AUT.C02 — Configuração incompleta falha fechada

- **Tipo:** erro
- **Regras:** AUT.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Impedir acesso quando o operador não provisionou autenticação válida.
- **Pré-condições:** Ambiente isolado via monkeypatch; nenhuma leitura de .env.
- **Passos:**
  1. Remover individualmente STUDIO_BROWSER_USER, STUDIO_BROWSER_PASSWORD e STUDIO_WORKER_TOKEN.
  2. Repetir com senha igual ao token e com usuário teste:operador; fazer GET Studio.
- **Esperado:** 503 de configuração em todas as variantes; caso de uso não é chamado.
- **Limitações:** Não valida entrega de variáveis pelo ambiente real.
- **Automação:** camada `mock`; referência `tests/test_studio_auth.py:40-48; proposta adicional para usuário contendo dois-pontos`

### AUT.C03 — CSRF de mutação e separação browser/worker

- **Tipo:** borda
- **Regras:** AUT.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Verificar a obrigatoriedade e igualdade exata de origem.
- **Pré-condições:** Cliente localhost:8000 com serviço indisponível simulado.
- **Passos:**
  1. POST /studio/videos/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/approve usando Basic sem Origin, com http://localhost:8000 e com http://localhost:8001.
  2. Repetir com Bearer sem Origin, com Origin correto e com Origin vazio.
- **Esperado:** Basic sem origem ou com outra porta retorna 403; mesma origem alcança 503 do dublê. Bearer sem cabeçalho alcança o serviço; presença do cabeçalho, inclusive vazio, retorna 403.
- **Limitações:** Não exercita comportamento de proxy; Origin vazio exige teste adicional.
- **Automação:** camada `mock`; referência `tests/test_studio_auth.py:51-56; proposta para porta diferente e Origin vazio`

### AUT.C04 — Host malicioso e Basic malformado

- **Tipo:** erro
- **Regras:** AUT.R01, AUT.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Recusar rebinding e entrada inválida sem erro interno.
- **Pré-condições:** Allowlist contém localhost e não attacker.example.
- **Passos:**
  1. Enviar credencial válida com Host attacker.example:8000 e Origin correspondente.
  2. Enviar Authorization Basic !!! para Host localhost:8000.
- **Esperado:** Host não permitido retorna 403; Basic malformado retorna 401, sem 500 nem eco de credencial.
- **Limitações:** Não é teste de DNS/rede real.
- **Automação:** camada `mock`; referência `tests/test_studio_auth.py:59-62; proposta para Base64 inválido`

### AUT.C05 — Saúde pública e remoção do legado

- **Tipo:** regressao
- **Regras:** AUT.R05
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Evitar interpretar rotas independentes como bypass de Studio.
- **Pré-condições:** Studio substituído por dublê com ping falso antes de importar main.
- **Passos:**
  1. Sem Authorization, consultar /health e GET/POST /videos e /videos/qualquer.
  2. Comparar com GET /studio/videos/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.
- **Esperado:** /health contém studio_db=unavailable; legado retorna 410; Studio sem autenticação retorna 401.
- **Limitações:** Saúde responde status=ok mesmo sem banco; não equivale a readiness integral.
- **Automação:** camada `mock`; referência `tests/test_main_boot.py:20-35; tests/test_studio_auth.py:28-29`

### AUT.C06 — Cofre sintético valida caminho e protege valores

- **Tipo:** feliz
- **Regras:** AUT.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Verificar armazenamento e rejeição de traversal sem tocar segredos reais.
- **Pré-condições:** Diretório temporário novo, FileSecretStore exclusivo; dados artificiais.
- **Passos:**
  1. Gravar chave access_token com valor ficticio-123 no escopo youtube:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; consultar names e get.
  2. Tentar escopo ../fora e chave inválida contendo barra; inspecionar permissões e arquivos temporários.
- **Esperado:** names contém só access_token, get recupera o valor sintético, modos são 0700/0600 em POSIX; traversal gera SecretStoreError e não cria arquivo externo.
- **Limitações:** Não comprova criptografia em repouso; não usar raiz credentials existente.
- **Automação:** camada `unit`; referência `Automação proposta sobre renderer/app/studio/adapters/secret_store.py:24-108`

### AUT.C07 — Callback inválido não troca código nem revela token

- **Tipo:** erro
- **Regras:** AUT.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Garantir falha antes do OAuth para state inválido e resposta pública mínima no sucesso.
- **Pré-condições:** Relógio congelado; cofre em memória; cliente OAuth fake com contador.
- **Passos:**
  1. Iniciar consentimento de conta; enviar state diferente e depois state válido no instante exato da expiração.
  2. Reiniciar e concluir com code=code-fake, identidade teste@example.test e tokens fictícios.
- **Esperado:** Inválidos geram erro de state e zero chamadas exchange_code; sucesso devolve conta/canal/grant, sem access_token, refresh_token ou verifier.
- **Limitações:** Não confirma consent screen nem revogação Google; nunca usar provedor configurado.
- **Automação:** camada `mock`; referência `tests/test_connections_service.py:238-258,272-284`

### AUT.C08 — Dois callbacks para o mesmo state

- **Tipo:** concorrencia
- **Regras:** AUT.R03, AUT.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Investigar replay concorrente sem transformar hipótese em garantia existente.
- **Pré-condições:** OAuth fake; barreira após leitura do state; dois executores; cofre temporário ou em memória.
- **Passos:**
  1. Iniciar um consentimento; disparar duas conclusões com o mesmo code-fake e state antes de qualquer exclusão.
  2. Contar trocas OAuth, grants criados e respostas; repetir sequencialmente após sucesso.
- **Esperado:** Critério de segurança proposto: no máximo uma conclusão efetiva e rejeição do replay; registrar divergência se ambos atravessarem a validação. Replay sequencial após limpeza deve falhar antes da troca.
- **Limitações:** Consumo atômico não foi identificado; concorrência não reproduzida. Lock por método do cofre não cobre toda a operação OAuth.
- **Automação:** camada `mock`; referência `Automação proposta; renderer/app/studio/application/connections.py:174-219`

## Resumo do capítulo

8 cenários GC, todos A_PROJETAR e não executados. Cobertura: acesso feliz, configuração inválida, CSRF, rebinding, cofre e callback concorrente. Mock não comprova proteção de proxy/TLS nem integração Google.
