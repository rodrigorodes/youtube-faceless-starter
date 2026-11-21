#!/usr/bin/env bash
set -euo pipefail
curl -fsS -X POST 'http://localhost:8000/videos' -H 'Content-Type: application/json' -d '{"topic":"Como a inteligência artificial funciona?","format":"short","duration_seconds":20,"style":"documentary"}'
echo
