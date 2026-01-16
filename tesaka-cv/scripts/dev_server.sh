#!/usr/bin/env bash
# scripts/dev_server.sh
set -euo pipefail

cd "$(dirname "$0")/.."
echo "[+] Working dir: $(pwd)"

export PYTHONPATH="${PWD}"
export SIFEN_ARTIFACTS_DIR="${PWD}/artifacts"

if [[ -f .env ]]; then
  echo "[+] Loading .env"
  set -a
  source .env
  set +a
fi

echo "[+] Killing any process on :8001"
(lsof -ti :8001 | xargs -r kill -9) 2>/dev/null || true

echo "[+] Starting dev server (uvicorn)..."
exec .venv/bin/python -m web.main
