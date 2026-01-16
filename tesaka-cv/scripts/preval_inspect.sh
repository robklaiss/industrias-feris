#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_XML="${HOME}/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml"

# Source env if available
if [[ -f "${SCRIPT_DIR}/sifen_env.sh" ]]; then
  # shellcheck disable=SC1090
  source "${SCRIPT_DIR}/sifen_env.sh"
fi

PYTHON_BIN="python3"
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
fi

XML_PATH="${DEFAULT_XML}"
EXTRA_ARGS=()
if [[ $# -gt 0 ]]; then
  if [[ "$1" != --* ]]; then
    XML_PATH="$1"
    shift
  fi
fi

if [[ $# -gt 0 ]]; then
  EXTRA_ARGS=("$@")
fi

set -x
"${PYTHON_BIN}" -m tools.inspect_prevalidator_xml "${XML_PATH}" "${EXTRA_ARGS[@]}"
set +x

if printf '%s\0' "${EXTRA_ARGS[@]}" | grep -q -- '--write-der'; then
  echo "DER generado (si hubo certificado) en /tmp/preval_embedded.der"
fi
