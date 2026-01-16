#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/signed.xml" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=/dev/null
source "${REPO_ROOT}/scripts/sifen_env.sh"

INPUT="$1"
if [[ ! -f "$INPUT" ]]; then
  echo "Input XML not found: $INPUT" >&2
  exit 2
fi

OUT="/tmp/preval_rDE_std.xml"
DESKTOP_FIX="${HOME}/Desktop/SIFEN_PREVALIDADOR_UPLOAD_FIX.xml"

"${REPO_ROOT}/.venv/bin/python" -m tools.export_for_prevalidator "$INPUT"

"${REPO_ROOT}/.venv/bin/python" -m tools.verify_sig_location "$OUT"

"${REPO_ROOT}/.venv/bin/python" -m tools.fix_prevalidator_xml "$OUT" "$DESKTOP_FIX"

echo "OK -> SUBÍ ESTE ARCHIVO AL PREVALIDADOR: ${DESKTOP_FIX}"
