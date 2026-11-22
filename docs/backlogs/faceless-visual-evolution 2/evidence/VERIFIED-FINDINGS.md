# Achados verificados (não corrigidos nesta rodada)

Registrados com evidência. Nenhum foi "consertado" por fora do escopo; cada um tem impacto e
referência. Ordem de risco aproximada.

| # | Achado | Evidência | Impacto | Correção sugerida |
|---|---|---|---|---|
| 1 | `/publications/claim` fica **fora** do gate de identidade (`verify_publication_gate`) | rota em `api/routes.py`; workflow n8n `workflows/03-publish-approved.json` está inativo | um claim de publicação não passa pela verificação de identidade do canal; risco de publicar em canal errado se o workflow for reativado | mover a verificação para o caso de uso `claim` (fail-closed) e cobrir com teste de rota |
| 2 | Seleção de provider **congelada** no snapshot do run (S8) | `domain/effective_config.py` + `application/production.py`; `evidence/ve-s8-closure.md` | **resolvido**: criação grava `provider_policy.selection`; retry lê o snapshot e levanta em vez de trocar em silêncio; run legado cai no roteamento vivo | — |
| 3 | Recusa de orçamento não é acionável | `api/routes.py:923` responde `403 "budget denied for paid operation <key>"` | operador não sabe qual teto estourou nem o valor | devolver teto, valor e escopo (projeto/canal) na mensagem |
| 4 | Compose não encaminha `STUDIO_PROVIDER_PRODUCTION` / `STUDIO_SECRETS_ROOT` | `docker-compose.yml` (W0B.1 só encaminhou `STUDIO_BUDGET_GUARD`/`STUDIO_PRODUCTION_MODE`) | produção por provider e cofre de segredos não chegam ao container | encaminhar as duas variáveis com default seguro |
| 5 | `application/config.py` ainda cita `ffmpeg` nos `_DEFAULTS` | `renderer/app/studio/application/config.py` | resíduo de S2: nome de fornecedor na camada de aplicação | mover o default para composição (ou aceitar como dado de configuração, documentando) |
| 6 | `render_compiler.py` emite argumentos de linha de comando com `ffmpeg` | `application/render_compiler.py` | S3 conhecido: compilador de render plan fala com o binário | aceitável por ora; isolar em adaptador quando S3 entrar |
| 7 | `MediaSearch` não tem adaptador de segunda fonte (Pixabay) | `adapters/media_pexels.py` é o único | se o Pexels cair ou não tiver o termo, não há fallback | segundo adaptador da mesma porta, sem tocar o domínio |
| 8 | QA semântico não tem verificador | `domain/quality.py` marca `MULTIMODAL_EVALUATION` como `not_verified`; a aba Qualidade é honesta | não há selo falso; falta a porta do avaliador multimodal | declarar `SemanticChecker` e implementar por provedor de visão |
| 9 | `panel_styles.py` `active_section` já alinhado a `biblioteca` | `api/panel_styles.py:519` | — (resolvido na W1) | — |
| 10 | Testes de segredos não resolvem `.git` de worktree dentro do container | `tests/test_secrets_hygiene.py` | falso negativo em validação por worktree | montar o gitdir ou pular com motivo explícito no worktree |
| 11 | `test_port_contracts` falha na suíte completa por **vazamento de `_REGISTRY`** entre testes | `register(...)` em nível de módulo em `tests/test_editorial_api.py` (4) e `tests/test_render_api.py` (2); o arquivo isolado dá 8 passed | 2 falhas falsas na suíte completa; o S8 confirmou as mesmas no HEAD `a2e6a39` sem as mudanças | fixture de isolamento que salva/restaura `_REGISTRY` por teste, ou registrar fakes dentro do teste |

## Ambiente de teste (não é código)

- Rodadas concorrentes de container derrubam o Postgres descartável e matam `ffmpeg` por OOM
  (`psycopg.OperationalError: Name or service not known` / `Connection refused`; `ffmpeg` com
  `returncode -9`). Rodada completa com outras frentes ativas é **inválida**; refazer sozinha.
- `scripts/test-container.sh` honra `FACELESS_TEST_IMAGE`/`FACELESS_PYTEST_IMAGE`; cada frente
  usa uma tag própria para não colidir.
