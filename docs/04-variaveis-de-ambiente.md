# Variáveis de ambiente e configuração

Revisado em **24/11/2026**, contra o checkout `2beb90e`. Fonte da configuração:
[Compose](../docker-compose.yml), [Settings](../renderer/app/studio/composition/settings.py),
[providers por projeto](../renderer/app/studio/application/config.py) e
[bridge](../scripts/opencode-bridge.py).

O `.env` privado na raiz fornece valores para **interpolação do Compose**; ele não é
automaticamente injetado inteiro no renderer. Só as chaves encaminhadas em
`services.renderer.environment` chegam ao container. O processo Python lê seu
ambiente; o bridge tem carregador próprio. Não imprima `docker compose config`,
`env` ou arquivos de credenciais em relatórios: podem revelar valores secretos.

`.env.example` é um ponto de partida, não um inventário completo. As tabelas abaixo
distinguem defaults do código e do Compose. [Auditoria e pendências](reviews/2026-11-24-architecture-review.md).

| Variável | Obrigatória | Padrão | Para quê |
|----------|-------------|--------|----------|
| `POSTGRES_USER` | não | `n8n` | Usuário compartilhado por n8n e Studio no Compose |
| `POSTGRES_DB` | não | `n8n` | Nome do banco |
| `POSTGRES_PASSWORD` | **sim** | — | Senha do banco. O `docker compose` aborta se faltar. |
| `N8N_ENCRYPTION_KEY` | **sim** | — | Chave que cifra as credenciais salvas no n8n. O `docker compose` aborta se faltar. |
| `TZ` | não | `America/Sao_Paulo` | Fuso do n8n (também usado como `GENERIC_TIMEZONE`) |
| `OPENCODE_BRIDGE_TOKEN` | não (obrigatória com o provider `opencode`) | vazio | Token (16+ caracteres) compartilhado entre renderer e bridge. Veja [07](07-openai-luna-oauth.md). |
| `OPENCODE_MODEL` | não | `openai/gpt-6-luna` | Modelo de texto do bridge: `provider/model[#variante]` |
| `OPENCODE_IMAGE_MODEL` | não | `openrouter/recraft/recraft-v4.1-flash-v2:free` | Modelo de imagem do provider `opencode`; o bridge recusa os que não terminam em `:free` |
| `OPENCODE_ALLOW_PAID_IMAGES` | não | (vazio) | `1` libera modelos de imagem pagos no bridge |
| `STUDIO_TEXT`, `STUDIO_IMAGE`, `STUDIO_VOICE`, `STUDIO_RENDERER` | não | `opencode:openai/gpt-6-luna`, `opencode:openrouter/recraft/recraft-v4.1-flash-v2:free`, `piper:pt_BR-faber-medium`, `ffmpeg:rich` | Código em `application/config.py`; Compose encaminha vazio e o código resolve. `Project.config` sobrescreve. Texto: `opencode`/`demo`; imagem: `opencode`/`placeholder`/`stock`; `veo` existe no registro mas **não gera** (lança `ModelUnavailable`). Voz `piper` resolve `/opt/voices/<modelo>.onnx`; render `ffmpeg`. |
| `PIPER_VOICE` | não | `/opt/voices/pt_BR-faber-medium.onnx` | Caminho explícito do arquivo de voz do Piper; **sobrepõe** o modelo do spec. Para outra voz: monte o `.onnx` (+ `.onnx.json`) em `/opt/voices` e aponte `PIPER_VOICE`, ou use `STUDIO_VOICE=piper:<nome>` para uma voz já instalada. Vozes pt_BR do repositório do Piper: `faber`, `cadu`, `jeff` (`medium`) e `edresson` (`low`) |
| `STUDIO_DATABASE_URL` | sim para domínio | Python: ausente; Compose: montada com `POSTGRES_*` | Banco do schema `studio`, compartilhado com n8n no Compose. Definir esta chave no `.env` **não substitui** a URL montada. Sem conexão/configuração, o domínio fica indisponível. |
| `STUDIO_BROWSER_USER`, `STUDIO_BROWSER_PASSWORD`, `STUDIO_WORKER_TOKEN` | sim para Studio | vazios | Credenciais distintas e persistentes; configuração e limites em [17](17-studio-auth.md). Sem elas `/studio` responde 503. |
| `STUDIO_ALLOWED_HOSTS` | não | `localhost,127.0.0.1,renderer` | Hosts aceitos pela API `/studio`, separados por vírgula. Configuração protege contra DNS rebinding, mas **não substitui autenticação**; não exponha a API à rede. |
| `MAX_COST_USD_PER_VIDEO`, `MAX_COST_USD_PER_MONTH` | não; teto positivo para gasto pago | `0`, `15` | Tetos em USD. O guard de operações pagas faz reservas quando habilitado; os limites por canal participam da resolução na composição. Valores inválidos/negativos/não finitos voltam ao default. Estimativa não é fatura nem garantia de preço externo. |
| `PEXELS_API_KEY` | não | (vazio) | Chave do Pexels para `STUDIO_IMAGE=stock:pexels` |
| `STUDIO_PAID_IMAGE_USD`, `STUDIO_VEO_USD_PER_SECOND` | não | `0.05`, `0.40` | Estimativas de custo por imagem não `:free` e por segundo de Veo (o `CostGuard` usa antes de gerar) |
| `RENDER_CONCURRENCY` | não | `1` | Limite de threads do executor **compartilhado por render avulso e produção**. Código limita a 1–4; não limita tamanho da fila nem concorrência global entre processos. |
| `STUDIO_SOURCE_ALLOWLIST` | não | `amsterdam-dance-event.nl` | Domínios (vírgula) de onde o estúdio busca fontes; subdomínios incluídos |
| `STUDIO_ALLOW_NAMES` | não | `amsterda` | Nomes próprios aceitos mesmo ausentes da fonte (exônimos em português) |
| `OPENCODE_BRIDGE_PORT` | não | `8787` | Porta do bridge no host |
| `OPENCODE_BRIDGE_URL` | não | `http://host.docker.internal:8787` | Como o container alcança o bridge |

Valores fixos no `docker-compose.yml` (não vêm do `.env`): `MAX_DURATION_SECONDS=60` (**não é lido** pelo código atual), `OUTPUT_DIR=/data/output`, `JOB_DIR=/data/jobs`, `WEBHOOK_URL=http://localhost:5678/`, `N8N_HOST=localhost`, `N8N_PROTOCOL=http`.

`OUTPUT_DIR`/`JOB_DIR` também não têm leitores no Python atual; o Studio usa
`STUDIO_STORAGE_ROOT`. Duração é política de domínio (`domain/render.py`), não
`MAX_DURATION_SECONDS`.

## Controles de execução, segurança e integração

Origem **S** = `composition/settings.py:38–90`; **C** = `docker-compose.yml:44–88`;
**R** = `api/routes.py:115–182`; **B** = `scripts/opencode-bridge.py`.
Nas tabelas anteriores: banco/n8n vêm de C, autenticação de R, providers de
`application/config.py:10–36`, voz de `app/rich.py`, parâmetros OpenCode do host de B;
os demais parâmetros Studio vêm de S/C.

| Variável / finalidade | Obrigatoriedade | Default Python → Compose | Origem / observação |
|---|---|---|---|
| `STUDIO_BUDGET_GUARD` — reservas preventivas | Não; habilitar para orçamento pago | `false` → `1` | S/C. Fora do Compose não presumir guard ligado. |
| `STUDIO_PRODUCTION_MODE` — pausas do coordenador | Não | `INTERACTIVE` → `BUDGET_GUARDED` | S/C. Inválido volta a `INTERACTIVE`. Aprovação final humana permanece; não confundir com modo do vídeo `piloto`/`diretor`. |
| `STUDIO_PROVIDER_PRODUCTION` — excluir demo/placeholder do roteamento produtivo | Não | `false` → vazio (`false`) | S/C. É flag independente do modo guardado; não ativa guard nem OAuth. |
| `STUDIO_STORAGE_ROOT` — artefatos | Diretório gravável para mídia | `/data` → fixo `/data` | S/C. Bind `./storage:/data`; chave no `.env` não muda esse valor fixo. |
| `STUDIO_SECRETS_ROOT` — cofre | Não | `<storage_root>/secrets` → vazio, mesmo fallback | S/C. JSON em disco, permissões 0700/0600, sem criptografia implementada no adaptador. |
| `STUDIO_GOOGLE_CLIENT_SECRET_FILE` — app OAuth web | Para consentimento/refresh/upload | Ausente → vazio | S/C. Caminho **no container**, por exemplo `/app/credentials/google-client.json`; arquivo deve ser provisionado, não commitado. |
| `STUDIO_GOOGLE_OAUTH_REDIRECT_URI` — callback | Para OAuth, deve coincidir com cadastro do app | `http://localhost:8000/studio/oauth/callback` → igual | S/C. Não é o redirect de um cliente OAuth desktop. |
| `YOUTUBE_API_KEY` — pesquisa de tendências | Para refresh de tendências | Vazio → vazio | `application/categories.py:118–130`/C; fallback de chave no arquivo legado. API key não autoriza upload ou analytics privados. |
| `STUDIO_PUBLICATION_ENABLED` — desligar executor de upload | Não | `true` → `1` | S/C. Agora **encaminhada** pelo Compose (`${STUDIO_PUBLICATION_ENABLED:-1}`); `0` bloqueia `RunPublication` (`BLOCKED`) sem tocar uploader ou token. Vazio equivale a falso no código, por isso o Compose usa `:-1`. Aplique com `docker compose up -d renderer`. |
| `STUDIO_RECOVERY_INTERVAL_SECONDS` — varredura periódica de runs órfãos | Não | `60` → `60` | S/C. `0` desliga o laço (kill switch: volta a recuperar só no boot); valor em `(0, 5)` vira `5`; vazio/inválido volta a `60`. Grace (30 s) e limite por rodada (50) são constantes iniciais, não configuráveis nem medidas. |

### Lidas pelo código, mas **não encaminhadas no Compose principal**

| Variável / finalidade | Obrigatoriedade | Default Python efetivo no Compose | Origem / efeito |
|---|---|---|---|
| `STUDIO_RENDER_PLAN_ENABLED` — disponibilidade do render | Não | `true` | S. `0` recusa render; não reativa renderer legado. |
| `STUDIO_AUTO_RESEARCH` — pesquisa automática Wikipedia | Não | `true` | S. O Compose E2E encaminha `0`; o principal não encaminha esta variável. |
| `STUDIO_TREND_SOURCES` — hosts admitidos na ingestão | Não | `www.googleapis.com,www.youtube.com` | S. Não é a allowlist de fontes editoriais. |
| `STUDIO_TOKEN_ENV_PATH` — credencial legada | Não para grants atuais | `credentials/token.env` | S. Relativo a `/app` na imagem; arquivo montado read-only. Não substitui destino/autorização por canal. |

As lacunas restantes são pendências de implementação (R01 na revisão; `STUDIO_PUBLICATION_ENABLED` já foi endereçada), não controles
disponíveis só por editar `.env`. Nenhum arquivo de deploy foi alterado nesta revisão.

### Host do bridge e valores sem consumidor

`OPENCODE_MODEL`, `OPENCODE_IMAGE_MODEL`, `OPENCODE_ALLOW_PAID_IMAGES` e
`OPENCODE_BRIDGE_PORT` são parâmetros do **bridge no host**, não do renderer.
O renderer envia o modelo escolhido pelo projeto/roteamento; o default do bridge
não substitui toda escolha explícita. `OPENCODE_ALLOW_PAID_IMAGES` só libera a
barreira do bridge quando igual a `1`; não aprova orçamento no Studio.

`GEMINI_API_KEY` aparece como nome no exemplo, mas não há consumidor no renderer
atual. Não configura Veo, que é um stub. Não há garantia de disponibilidade,
gratuidade permanente ou preço dos modelos listados: são defaults do código.

## Precedência e snapshot

1. Providers: `Project.config` → variável `STUDIO_*` não vazia → default do código.
   O roteador aplica disponibilidade/política econômica e o modo de provider.
2. Estilo: seleção do vídeo → estilo do canal → neutro; patches criativos do vídeo
   prevalecem sobre patches do canal e parâmetros de estilo.
3. A criação do run congela configuração efetiva e seleção de providers. Retomar/retry
   usa o snapshot; regenerar cria outra execução com configuração atual.
4. `PIPER_VOICE` é override físico do arquivo de voz; a seleção lógica de modelo não
   instala arquivos. A imagem inclui apenas a voz faber especificada no Dockerfile.

Flags de S aceitam `1`, `true`, `yes`, `on` (sem distinguir maiúsculas); vazio
explícito é falso. Isso difere de variável ausente para flags cujo default é `1`.

## Local, testes e produção

| Uso | Configuração real | Limites |
|---|---|---|
| Operador local | `docker-compose.yml`: PostgreSQL/n8n/renderer; portas em loopback; bridge separado | Banco/arquivos persistentes; autenticação obrigatória; APIs externas podem custar. |
| Preview | `docker-compose.preview.yml` sobre o principal | Monta código read-only, mas usa **o mesmo storage e banco**. Não é sandbox; boot pode migrar. |
| Testes de banco | `docker-compose.test.yml` + harness de prova de banco descartável | O Compose isolado sozinho não provisiona a prova exigida por `tests/conftest.py`. Ver `scripts/test-container.sh`. Nunca apontar `STUDIO_TEST_DSN` ao banco de uso. |
| E2E isolado | `docker-compose.e2e.yml`, harness `scripts/run-e2e-full.sh` | Porta 8100, banco/storage tmpfs, demo/placeholder, pesquisa automática desligada; não comprova OAuth/upload real. |
| Produção externa/multiusuário | Não há perfil dedicado nos arquivos revisados | Não equiparar `STUDIO_PROVIDER_PRODUCTION=1` a implantação pronta para SaaS. Ver arquitetura operacional e ADR-003. |

Exemplo **sem segredos**, para o Compose local (não configura autenticação nem
garante isolamento de rede):

```dotenv
STUDIO_BUDGET_GUARD=1
STUDIO_PRODUCTION_MODE=INTERACTIVE
MAX_COST_USD_PER_VIDEO=0
MAX_COST_USD_PER_MONTH=15
RENDER_CONCURRENCY=1
```

Não executar o app contra um banco importante só para conferir parâmetros: o boot
aplica migrações. Conferência estática: comparar nomes/defaults em S, C e nos
testes `tests/test_compose_env.py`.

## Regras importantes

1. **Use senhas longas e aleatórias, diferentes entre si.** Prefira hexadecimal para evitar caracteres especiais no compose. Como gerar: veja [macOS](02-configuracao-macos.md#2-gerar-as-senhas) e [Windows](03-configuracao-windows.md#2-gerar-as-senhas).
2. **`POSTGRES_PASSWORD` inicializa a senha na primeira criação do volume `pg_data`.** Trocar depois só no `.env` não altera a senha dentro do banco existente; n8n e Studio podem perder conexão. Rotação exige mudança coordenada no banco e nos consumidores. `docker compose down -v` não é rotação: remove os volumes, inclusive os dados de domínio do Studio.
3. **`N8N_ENCRYPTION_KEY` não pode mudar** depois que existirem credenciais salvas: elas ficam ilegíveis. Guarde a chave (cofre de senhas) junto com o backup do volume `n8n_data`.
4. O **bridge do OpenCode** (provider `opencode`) consome a cota da conta logada e seus termos se aplicam. Veja [07](07-openai-luna-oauth.md).
5. Depois de editar o `.env`, aplique com `docker compose up -d` (recria só o que mudou).
6. **Trocar a voz do Piper invalida a calibração de duração.** `domain/narration_duration.py` mediu os números (`MEASURED_*`) **só** para `piper:pt_BR-faber-medium`; com outra voz o erro da estimativa volta (antes de calibrar era +15,6%). `tests/test_tts_calibration.py` **pula** (compara hash da voz e versão do Piper) quando a voz é outra — a perda do guarda é silenciosa. Recalibre com `scripts/tts_calibration.py` e atualize `scripts/tts_calibration_samples.json`.

## Portas

| Porta | Serviço | Binding |
|-------|---------|---------|
| 5678 | n8n | `127.0.0.1` (só a própria máquina) |
| 8000 | renderer | `127.0.0.1` (só a própria máquina) |

Se alguma porta já estiver em uso, o `up` falha com *port is already allocated*. Altere o lado esquerdo em `docker-compose.yml` (ex.: `"127.0.0.1:8001:8000"`) e ajuste as URLs dos comandos. Se mudar a do n8n, atualize também `WEBHOOK_URL`.

## Versões declaradas

As dependências Python estão em [requirements](../renderer/requirements.txt).
Tags de imagens como `16-alpine` e `3.12-slim` são mutáveis; não há pin por digest
no Compose/Dockerfile revisado.

| Componente | Versão |
|------------|--------|
| n8n | `docker.n8n.io/n8nio/n8n:1.123.5` |
| PostgreSQL | `postgres:16-alpine` |
| Renderer | `python:3.12-slim` + FFmpeg do Debian + fastapi 0.115.12, uvicorn 0.34.2, pillow 11.2.1, httpx 0.28.1, pydantic 2.11.4 |
