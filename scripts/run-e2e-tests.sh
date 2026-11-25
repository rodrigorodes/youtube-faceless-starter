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

BASE_URL="${STUDIO_BASE_URL:-http://localhost:8100}"

# Guarda de destino (FS-02.03 / LAC-03): impede execução acidental contra a stack DEV (porta 8000)
TARGET_PORT="$(echo "$BASE_URL" | sed -e 's,^.*:,,' -e 's,/.*$,,')"
if [ "$TARGET_PORT" = "8000" ] && [ "${STUDIO_E2E_ALLOW_DEV:-0}" != "1" ]; then
  echo "ERRO DE DESTINO: STUDIO_BASE_URL aponta para a porta 8000 (stack de desenvolvimento em uso)." >&2
  echo "Para proteger seus dados, testes E2E devem apontar para a stack isolada (ex: porta 8100)." >&2
  echo "Se você tem certeza de que deseja rodar contra a stack DEV, defina STUDIO_E2E_ALLOW_DEV=1." >&2
  exit 1
fi

echo "==> Verificando disponibilidade do Faceless Studio em $BASE_URL/health..."
if ! curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
  echo "ERRO: O servidor do Faceless Studio não está respondendo em $BASE_URL/health."
  echo "Certifique-se de que a stack isolada está ativa (ex.: scripts/run-e2e-full.sh ou docker compose -f docker-compose.e2e.yml up -d)."
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
