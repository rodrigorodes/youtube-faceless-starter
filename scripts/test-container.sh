#!/usr/bin/env bash
# Comando único de teste: a suíte roda DENTRO da imagem do renderer (ffmpeg, fontes e Python
# iguais aos de produção), contra um PostgreSQL descartável. O host (macOS/Windows) não é um
# ambiente de teste válido: lá faltam ffmpeg e a fonte DejaVu, e as versões de pacote divergem.
#
# Uso:
#   scripts/test-container.sh                       # suíte completa
#   scripts/test-container.sh tests/test_render_*.py -q
#   PYTEST_ADDOPTS="-x" scripts/test-container.sh tests/test_architecture.py
#
# O que faz:
#   1. constrói a imagem do renderer (cache do Docker) e uma camada fina com pytest;
#   2. confere que o código dentro da imagem é idêntico ao do checkout (hash de renderer/app)
#      e que as migrações da imagem e do checkout coincidem; imprime HEAD e se há alterações;
#   3. sobe um Postgres efêmero (tmpfs, rede própria, sem porta publicada) com a PROVA de
#      descartabilidade que tests/conftest.py exige antes de qualquer escrita;
#   4. roda o pytest com o checkout montado SOMENTE LEITURA e devolve o código de saída dele;
#   5. remove contêiner, rede e arquivos temporários ao sair, com sucesso ou não.
#
# Não toca o banco do n8n/Studio nem o `storage/` do projeto.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASE_IMAGE="${FACELESS_TEST_IMAGE:-faceless-renderer:test}"
PYTEST_IMAGE="${FACELESS_PYTEST_IMAGE:-faceless-renderer-pytest:test}"
PG_IMAGE="postgres:16-alpine"
RUN_ID="$$"
NETWORK="faceless-test-net-${RUN_ID}"
PG_NAME="faceless-test-pg-${RUN_ID}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/faceless-test.XXXXXX")"

cleanup() {
  docker rm -f "$PG_NAME" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT

command -v docker >/dev/null || { echo "docker não encontrado" >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo "docker não está em execução" >&2; exit 2; }

PYTEST_VERSION="$(sed -n 's/^pytest==\(.*\)$/\1/p' requirements-dev.txt)"
[ -n "$PYTEST_VERSION" ] || { echo "pytest não está fixado em requirements-dev.txt" >&2; exit 2; }

echo "== imagem"
docker build -q -t "$BASE_IMAGE" renderer >/dev/null
docker build -q -t "$PYTEST_IMAGE" -f - renderer >/dev/null <<EOF
FROM ${BASE_IMAGE}
# git: tests/test_secrets_hygiene.py exercita o scanner e o empacotador, que leem o índice do git.
# Só na camada de teste: a imagem de produção não precisa dele.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \\
 && git config --system --add safe.directory '*' \\
 && pip install --no-cache-dir pytest==${PYTEST_VERSION}
EOF

echo "== alinhamento (checkout x imagem)"
HOST_TREE="$(cd renderer && find app \( -name '*.py' -o -name '*.sql' \) -not -path '*/__pycache__/*' | LC_ALL=C sort \
  | xargs shasum -a 256 | shasum -a 256 | cut -c1-16)"
IMAGE_TREE="$(docker run --rm --entrypoint sh "$BASE_IMAGE" -c \
  'cd /app && find app \( -name "*.py" -o -name "*.sql" \) -not -path "*/__pycache__/*" | LC_ALL=C sort | xargs sha256sum | sha256sum | cut -c1-16')"
HOST_MIG="$(ls renderer/app/studio/adapters/postgres/migrations/*.sql | wc -l | tr -d ' ')"
IMAGE_MIG="$(docker run --rm --entrypoint sh "$BASE_IMAGE" -c 'ls /app/app/studio/adapters/postgres/migrations/*.sql | wc -l' | tr -d ' ')"
DIRTY="não"; [ -n "$(git status --porcelain -- renderer tests)" ] && DIRTY="sim"
echo "HEAD=$(git rev-parse --short HEAD) alterações_em_renderer/tests=${DIRTY}"
echo "hash renderer/app: checkout=${HOST_TREE} imagem=${IMAGE_TREE}"
echo "migrações: checkout=${HOST_MIG} imagem=${IMAGE_MIG}"
if [ "$HOST_TREE" != "$IMAGE_TREE" ] || [ "$HOST_MIG" != "$IMAGE_MIG" ]; then
  echo "ERRO: a imagem não corresponde ao checkout" >&2
  exit 3
fi

echo "== PostgreSQL descartável"
PROOF="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
PG_PASSWORD="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
mkdir -p "$TMP/proof"
printf '%s' "$PROOF" > "$TMP/proof/proof"
chmod 755 "$TMP/proof"; chmod 644 "$TMP/proof/proof"
docker network create "$NETWORK" >/dev/null
docker run -d --name "$PG_NAME" --network "$NETWORK" \
  -e POSTGRES_PASSWORD="$PG_PASSWORD" \
  --tmpfs /var/lib/postgresql/data \
  -v "$TMP/proof/proof:/budget-test-proof/proof:ro" \
  "$PG_IMAGE" >/dev/null
for _ in $(seq 1 60); do
  docker exec "$PG_NAME" pg_isready -U postgres >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$PG_NAME" pg_isready -U postgres >/dev/null 2>&1 || { echo "Postgres de teste não subiu" >&2; exit 4; }
# o init do postgres reinicia o servidor uma vez; espera a segunda disponibilidade
sleep 2
docker exec "$PG_NAME" pg_isready -U postgres >/dev/null

# Os dois DSNs apontam para o MESMO Postgres efêmero acima: a suíte usa STUDIO_TEST_DSN (fixture
# `dsn`/`conn` do conftest) e STUDIO_BUDGET_DISPOSABLE_DSN (orçamento, produção, SaaS...). Sem o
# segundo, ~140 testes de banco são pulados em silêncio. Ambos exigem a prova de descartabilidade.
echo "== pytest ($*)"
ARGS=("$@")
[ ${#ARGS[@]} -eq 0 ] && ARGS=(tests --ignore=tests/e2e_full --ignore=tests/e2e_ux -q)

REPORTS_DIR="${ROOT}/storage/test-reports"
mkdir -p "$REPORTS_DIR"

set +e
docker run --rm --network "$NETWORK" \
  -e STUDIO_TEST_DSN="postgresql://postgres:${PG_PASSWORD}@${PG_NAME}:5432/postgres" \
  -e STUDIO_BUDGET_DISPOSABLE_DSN="postgresql://postgres:${PG_PASSWORD}@${PG_NAME}:5432/postgres" \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/proof/proof \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/w/renderer \
  ${PYTEST_ADDOPTS:+-e PYTEST_ADDOPTS="$PYTEST_ADDOPTS"} \
  -v "$ROOT:/w:ro" \
  -v "$REPORTS_DIR:/w/storage/test-reports:rw" \
  -v "$REPORTS_DIR:/test-reports:rw" \
  -v "$TMP/proof:/proof:ro" \
  -w /w \
  --entrypoint python "$PYTEST_IMAGE" -m pytest -p no:cacheprovider "${ARGS[@]}"
STATUS=$?
set -e
echo "== pytest saiu com código ${STATUS}"
exit "$STATUS"
