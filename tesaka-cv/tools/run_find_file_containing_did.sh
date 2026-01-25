#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <dId> <external_artifacts_dir>" >&2
  exit 1
fi

DID="$1"
EXTERNAL_DIR_RAW="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TESAKA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
PROJECT_ROOT="$(cd "${TESAKA_ROOT}/.." && pwd -P)"
PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "❌ No se encontró intérprete en ${PYTHON_BIN}" >&2
  exit 1
fi

EXTERNAL_DIR="$(${PYTHON_BIN} - <<'PY'
import pathlib, sys
print(pathlib.Path(sys.argv[1]).expanduser().resolve())
PY
"${EXTERNAL_DIR_RAW}")"

mkdir -p "${EXTERNAL_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${EXTERNAL_DIR}/find_file_containing_did_${TIMESTAMP}.log"

ROOTS=(
  "/Users/robinklaiss/Desktop/SIFEN_ARTIFACTS_TEST_20260123"
  "${TESAKA_ROOT}/artifacts"
  "${TESAKA_ROOT}/tesaka-final/artifacts"
  "${PROJECT_ROOT}/artifacts"
  "${EXTERNAL_DIR}"
)

set +e
{
  echo "[runner] ${TIMESTAMP}"
  echo "[runner] Buscando dId=${DID}"
  echo "[runner] Roots adicionales: ${ROOTS[*]}"
  "${PYTHON_BIN}" "${TESAKA_ROOT}/tools/find_file_containing_did.py" "${DID}" "${ROOTS[@]}"
} >"${LOG_FILE}" 2>&1
status=$?
set -e

best_candidate="$(grep -m1 '^BEST_CANDIDATE=' "${LOG_FILE}" | head -n1 || true)"
if [[ -n "${best_candidate}" ]]; then
  source_path="${best_candidate#BEST_CANDIDATE=}"
  dest_path="${EXTERNAL_DIR}/DE_TAL_CUAL_TRANSMITIDO_${DID}.xml"
  if [[ ! -e "${dest_path}" ]]; then
    if [[ -f "${source_path}" ]]; then
      cp -p "${source_path}" "${dest_path}"
      {
        echo "[runner] Copiado CANDIDATO_XML_TRANSMITIDO a ${dest_path}"
      } >>"${LOG_FILE}"
    else
      {
        echo "[runner] Aviso: BEST_CANDIDATE=${source_path} no existe al momento de copiar"
      } >>"${LOG_FILE}"
    fi
  else
    {
      echo "[runner] Archivo destino ya existe, se omite copia: ${dest_path}"
    } >>"${LOG_FILE}"
  fi
fi

tail -n 80 "${LOG_FILE}"

if [[ ${status} -eq 0 ]]; then
  exit 0
elif [[ ${status} -eq 2 || ${status} -eq 3 ]]; then
  exit 2
else
  exit 1
fi
