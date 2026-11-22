#!/usr/bin/env bash
# Runner para a suíte de testes E2E de UX, Jornadas e Comportamento com Playwright.
#
# Uso:
#   bash scripts/run-e2e-tests.sh                   # Execução headless padrão
#   bash scripts/run-e2e-tests.sh --headed          # Abre navegador ao vivo para inspeção visual
#   bash scripts/run-e2e-tests.sh tests/e2e_ux/test_e2e_journey_creation.py
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASE_URL="${STUDIO_BASE_URL:-http://localhost:8000}"

echo "==> Verificando disponibilidade do Faceless Studio em $BASE_URL/health..."
if ! curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
  echo "ERRO: O servidor do Faceless Studio não está respondendo em $BASE_URL/health."
  echo "Certifique-se de que o container do renderer está ativo (ex.: docker compose up -d renderer)."
  exit 1
fi
echo "==> Servidor operacional."

HEADED_ARG=""
EXTRA_ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--headed" ]]; then
    HEADED_ARG="--headed"
  else
    EXTRA_ARGS+=("$arg")
  fi
done

TARGET="tests/e2e_ux"
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  TARGET="${EXTRA_ARGS[*]}"
fi

echo "==> Executando suíte E2E ($TARGET)..."
python3 -m pytest $TARGET $HEADED_ARG -v
