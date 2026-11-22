# Estratégia de validação e release

| Gate | Evidência mínima |
|---|---|
| G0 baseline | HEAD, ambiente, comandos, resultados, ADRs aceitos |
| G1 segurança | Grant correto/expirado/revogado, destino cruzado bloqueado, concorrência de reservas em PostgreSQL descartável, paridade UI/guard |
| G2 UX | Dois canais, estilo persistido, deep links, aliases, fontes, tema e teclado em navegador |
| G3 snapshot | Alteração durante TTS, retry/resume, novo run e legado; nenhum segredo serializado |
| G4 editorial | Captura de prompts de short/long para canais distintos; fontes insuficientes rejeitadas |
| G5 estilos | Isolamento de patches, reset, troca de base, arquivamento e conflito de versão |
| G6 routing | Perfil/provider real, audit trail, falha e fallback autorizado; custo respeitado |
| G7 release | Suites aplicáveis, browser, pipeline controlado, workflow sandbox, rollback demonstrado |

## Baseline sugerido (executar no ambiente do repo)

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider \
  tests/test_channel_budget.py tests/test_provider_catalog.py \
  tests/test_saas_domain.py tests/test_workflow_publish.py \
  tests/test_workflow_analytics.py tests/test_workflow_trends.py -q
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider \
  tests/test_home_v3.py tests/test_new_video_v3.py tests/test_videos_v3.py \
  tests/test_trends_v3.py tests/test_analytics_v3.py tests/test_ux_contract.py -q
```

Confirmar pré-requisitos em README/requirements e `tests/conftest.py`. Banco somente descartável com guard comprovado; jamais apontar testes que recriam schema para ambiente operacional. Providers fake para testes automatizados. Não considerar skipped como passed. Publicação real deve ser separada, autorizada explicitamente, privada, em canal de teste e com limites. Se não disponível, declarar gate correspondente não validado; decisão de aceite deve registrar restrição. Chamada paga exige autorização e teto. Não executar workflow importado sem revisar efeitos.

## PostgreSQL descartável (receita validada na F00)

O guard do `tests/conftest.py` exige: host único e explícito na DSN, e um arquivo de prova de
64 hex legível **pelo servidor** em `/budget-test-proof/proof`. Receita usada em 21/11/2026
(sem volume; dados em tmpfs; porta local isolada):

```sh
T=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/f00-disposable
mkdir -p "$T/proof"
python3 -c "import secrets;open('$T/proof/proof','w').write(secrets.token_hex(32))"
docker run -d --name faceless-f00-pg -p 127.0.0.1:55433:5432 -e POSTGRES_PASSWORD=test \
  -v "$T/proof":/budget-test-proof:ro --tmpfs /var/lib/postgresql/data postgres:16-alpine

cd <repo>
PYTHONPATH=renderer PYTHONDONTWRITEBYTECODE=1 \
  STUDIO_TEST_DSN="postgresql://postgres:test@127.0.0.1:55433/postgres" \
  STUDIO_BUDGET_DISPOSABLE_DSN="postgresql://postgres:test@127.0.0.1:55433/postgres" \
  STUDIO_BUDGET_TEST_PROOF_FILE="$T/proof/proof" \
  python3 -m pytest -p no:cacheprovider tests -q
```

Encerrar depois com `docker rm -f faceless-f00-pg`. Nunca apontar essas variáveis para o
banco do produto: a suíte remove o schema `studio` do destino.

## Evidência por execução

- Fase/tarefa, commit, ambiente (sem segredos), comando e resultado (pass/fail/skip), duração.
- Artefato/log sanitizado, teste que comprova aceite, gap correspondente, limitações.
- Revisor, data e decisão. Falha bloqueante: interromper dependentes, não mascarar erro com mocks ou relaxar asserts.

## Rollback

Preferir migrações aditivas e releases compatíveis. Backup/restauração testados antes de migração. Nunca apagar ledger, grants, revisões ou snapshots para reverter. Desabilitar publicação/produção paga em contingência; não reativar caminho inseguro. Não fazer reset/force push/revert de trabalho alheio. Rollback de código e dados planejado e aprovado antes de release.
