#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/ART_DIR" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TESAKA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
cd "${TESAKA_ROOT}"

PYTHON_BIN="${TESAKA_ROOT}/../.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "❌ No se encontró intérprete en ${PYTHON_BIN}" >&2
  exit 1
fi

ART_DIR="$(${PYTHON_BIN} -c "import pathlib, sys; print(pathlib.Path(sys.argv[1]).expanduser().resolve())" "$1")"

if [[ ! -d "${ART_DIR}" ]]; then
  echo "❌ Directorio inválido: ${ART_DIR}" >&2
  exit 1
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${ART_DIR}/agent_extract_0160_${TIMESTAMP}.log"

set +e
{
  echo "[runner] ${TIMESTAMP}"
  echo "[runner] Artifacts dir: ${ART_DIR}"
  echo "[runner] Ejecutando agent_extract_0160_artifacts.py"
  "${PYTHON_BIN}" tools/agent_extract_0160_artifacts.py "${ART_DIR}"
} >"${LOG_FILE}" 2>&1
status=$?
set -e

>&2 echo "📄 Log guardado en: ${LOG_FILE}"
tail -n 80 "${LOG_FILE}" || true

exit ${status}
