#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-}"
shift || true

if [[ -z "${PROFILE}" || ( "${PROFILE}" != "prod" && "${PROFILE}" != "test" ) ]]; then
  echo "Uso: tools/sifen_run.sh {prod|test} <comando> [args...]"
  echo "Comandos: autofix | send | follow"
  exit 2
fi

ENV_FILE="config/sifen_${PROFILE}.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "No existe ${ENV_FILE}"
  exit 2
fi

# Cargar perfil
set -a
source "${ENV_FILE}"
set +a

PY=".venv/bin/python"

CMD="${1:-}"
shift || true

case "${CMD}" in
  autofix)
    # args esperados: --xml ... [--artifacts-dir ...] ...
    exec "${PY}" tools/autofix_0160_gTotSub.py --env "${SIFEN_ENV}" "$@"
    ;;
  send)
    exec "${PY}" tools/send_sirecepde.py --env "${SIFEN_ENV}" "$@"
    ;;
  follow)
    exec "${PY}" tools/follow_lote.py --env "${SIFEN_ENV}" "$@"
    ;;
  *)
    echo "Comando desconocido: ${CMD}"
    echo "Comandos: autofix | send | follow"
    exit 2
    ;;
esac
