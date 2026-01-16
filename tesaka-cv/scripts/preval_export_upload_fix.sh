#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/signed.xml [output.xml]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="python3"
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
fi

INPUT="$1"
OUTPUT="${2:-${HOME}/Desktop/SIFEN_PREVALIDADOR_UPLOAD_FIX.xml}"

if [[ ! -f "$INPUT" ]]; then
  echo "Input XML not found: $INPUT" >&2
  exit 2
fi

set -x
"${PYTHON_BIN}" -m tools.prevalidator_export_fix "$INPUT" "$OUTPUT"
set +x

INSPECT_PY="${REPO_ROOT}/.venv/bin/python"
if [[ -x "$INSPECT_PY" ]]; then
  if ! "$INSPECT_PY" -m tools.inspect_prevalidator_xml "$OUTPUT" --write-der; then
    echo "WARN: inspect_prevalidator_xml no disponible o falló; continúa de todas formas." >&2
  fi
fi

open -R "$OUTPUT"
