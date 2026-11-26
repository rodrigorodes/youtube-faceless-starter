#!/usr/bin/env bash
# Runner dedicado de REC-04.02 (Documentário real 5–8 min / >=25 cenas via Studio, pareado com V4-00).
#
# Executa tests/test_rec_04_documentary.py dentro do container oficial (FFmpeg 7.1.5,
# Piper pt_BR-faber-medium, Postgres 16 efêmero em tmpfs, checkout montado :ro) e monta
# um diretório exclusivo em storage/output/runs/<run_id>/ para preservar os MP4s,
# legendas, frames-chave de amostra, opções de thumbnail V2-F7 e manifest.json.
#
# Não toca DEV (portas 8000/5678), não commita binários, mantém STUDIO_PUBLICATION_ENABLED=0
# e orçamento externo estritamente $0.00.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASE_IMAGE="${FACELESS_TEST_IMAGE:-faceless-renderer:test}"
PYTEST_IMAGE="${FACELESS_PYTEST_IMAGE:-faceless-renderer-pytest:test}"
PG_IMAGE="postgres:16-alpine"
PID="$$"
SHORT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
RUN_ID="${REC04_DOC_RUN_ID:-rec04_doc_$(date -u +%Y%m%d_%H%M%S)_${SHORT_SHA}}"
OUT_DIR="${ROOT}/storage/output/runs/${RUN_ID}"
NETWORK="faceless-rec04-doc-net-${PID}"
PG_NAME="faceless-rec04-doc-pg-${PID}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/faceless-rec04-doc.XXXXXX")"

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

echo "== imagem (REC-04.02)"
docker build -q -t "$BASE_IMAGE" renderer >/dev/null
docker build -q -t "$PYTEST_IMAGE" -f - renderer >/dev/null <<EOF
FROM ${BASE_IMAGE}
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
echo "HEAD=${SHORT_SHA} RUN_ID=${RUN_ID}"
echo "hash renderer/app: checkout=${HOST_TREE} imagem=${IMAGE_TREE}"
echo "migrações: checkout=${HOST_MIG} imagem=${IMAGE_MIG}"
if [ "$HOST_TREE" != "$IMAGE_TREE" ] || [ "$HOST_MIG" != "$IMAGE_MIG" ]; then
  echo "ERRO: a imagem não corresponde ao checkout" >&2
  exit 3
fi

echo "== PostgreSQL descartável (tmpfs, rede privada, zero portas no host)"
PROOF="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
PG_PASSWORD="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
mkdir -p "$TMP/proof" "$OUT_DIR"
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
sleep 2
docker exec "$PG_NAME" pg_isready -U postgres >/dev/null

echo "== executando documentário 5-8min REC-04.02 (saída em ${OUT_DIR})"
set +e
docker run --rm --network "$NETWORK" \
  -e STUDIO_TEST_DSN="postgresql://postgres:${PG_PASSWORD}@${PG_NAME}:5432/postgres" \
  -e STUDIO_BUDGET_DISPOSABLE_DSN="postgresql://postgres:${PG_PASSWORD}@${PG_NAME}:5432/postgres" \
  -e STUDIO_BUDGET_TEST_PROOF_FILE=/proof/proof \
  -e STUDIO_PUBLICATION_ENABLED=0 \
  -e STUDIO_BUDGET_GUARD=1 \
  -e MAX_COST_USD_PER_VIDEO=0 \
  -e MAX_COST_USD_PER_MONTH=0 \
  -e REC04_DOC_OUT_DIR=/rec04-doc-out \
  -e REC04_DOC_RUN_ID="$RUN_ID" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/w/renderer \
  -v "$ROOT:/w:ro" \
  -v "$OUT_DIR:/rec04-doc-out:rw" \
  -v "$TMP/proof:/proof:ro" \
  -w /w \
  --entrypoint python "$PYTEST_IMAGE" -m pytest -p no:cacheprovider tests/test_rec_04_documentary.py -ra -v
STATUS=$?
set -e

echo "== REC-04.02 finalizado com código ${STATUS}"
if [ "$STATUS" -eq 0 ] && [ -f "${OUT_DIR}/rec04_02_documentary.mp4" ]; then
  echo "MP4 preservado:      ${OUT_DIR}/rec04_02_documentary.mp4"
  echo "Manifesto gerado:    ${OUT_DIR}/manifest.json"
  echo "Frames de amostra:   ${OUT_DIR}/frames/"
  echo "Para assistir (Mac): open \"${OUT_DIR}/rec04_02_documentary.mp4\""
fi
exit "$STATUS"
