#!/usr/bin/env bash
# E2E de ponta a ponta, SEM custo e SEM tocar na stack de uso: sobe docker-compose.e2e.yml (projeto Docker
# `faceless-e2e`, porta 8100, Postgres e storage em tmpfs), roda a jornada em Playwright e derruba tudo.
#
# Uso:
#   bash scripts/run-e2e-full.sh                 # jornada completa (headless)
#   bash scripts/run-e2e-full.sh --headed        # navegador visível
#   KEEP=1 bash scripts/run-e2e-full.sh          # mantém a stack no ar depois (inspeção); derrube com `down -v`
#   bash scripts/run-e2e-full.sh -k piloto       # filtra testes
#
# Provedores: texto demo, imagem placeholder, voz Piper local, render ffmpeg local. O YouTube fica fora do
# escopo: a jornada termina em "aprovado, pendente de publicar". Para o E2E contra a stack de uso (telas, sem
# produção paga) existe `scripts/run-e2e-tests.sh`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -p faceless-e2e -f docker-compose.e2e.yml)

cleanup() {
  if [[ "${KEEP:-0}" != "1" ]]; then
    "${COMPOSE[@]}" down -v >/dev/null 2>&1 || true
  else
    echo "==> KEEP=1: stack mantida em http://127.0.0.1:8100 (derrube com: ${COMPOSE[*]} down -v)"
  fi
}
trap cleanup EXIT

echo "==> Recriando a stack isolada (banco e storage zerados)..."
"${COMPOSE[@]}" down -v >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d --build --wait

echo "==> Executando a jornada completa..."
STUDIO_E2E_ISOLATED=1 STUDIO_E2E_BASE_URL="http://127.0.0.1:8100" \
  python3 -m pytest tests/e2e_full -v -p no:cacheprovider "$@"
