#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <dId> <copy_to_dir>" >&2
  exit 1
fi

DID="$1"
COPY_DIR_RAW="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TESAKA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
PYTHON_BIN="${TESAKA_ROOT}/../.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "❌ No se encontró intérprete en ${PYTHON_BIN}" >&2
  exit 1
fi

COPY_DIR="$(${PYTHON_BIN} -c "import pathlib, sys; print(pathlib.Path(sys.argv[1]).expanduser().resolve())" "${COPY_DIR_RAW}")"

if [[ ! -d "${COPY_DIR}" ]]; then
  echo "❌ Directorio inválido: ${COPY_DIR}" >&2
  exit 1
fi

cd "${TESAKA_ROOT}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${COPY_DIR}/agent_find_sent_lote_${TIMESTAMP}.log"

set +e
{
  echo "[runner] ${TIMESTAMP}"
  echo "[runner] Artifacts dir: ${COPY_DIR}"
  echo "[runner] Buscando dId=${DID}"
  "${PYTHON_BIN}" tools/find_sent_lote_by_did.py "${DID}" --copy-to "${COPY_DIR}"
} >"${LOG_FILE}" 2>&1
status=$?
set -e

>&2 echo "📄 Log guardado en: ${LOG_FILE}"

tail -n 30 "${LOG_FILE}" || true

exit ${status}
