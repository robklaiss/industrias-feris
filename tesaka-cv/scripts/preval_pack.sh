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

"${REPO_ROOT}/.venv/bin/python" -m tools.preval_pack "$INPUT"

ls -lah /tmp/preval_UPLOAD_*.xml || true
ls -lah /tmp/preval_embedded_cert.* || true
[[ -f /tmp/preval_embedded_cert_report.txt ]] && tail -n 40 /tmp/preval_embedded_cert_report.txt || true
[[ -f /tmp/preval_xmlsec_verify.txt ]] && tail -n 40 /tmp/preval_xmlsec_verify.txt || true

echo "SUBÍ ESTOS ARCHIVOS:"
echo " - /tmp/preval_UPLOAD_DE.xml"
echo " - /tmp/preval_UPLOAD_DE_ds.xml"
echo " - /tmp/preval_UPLOAD_rDE.xml"
echo " - /tmp/preval_UPLOAD_rDE_ds.xml"
