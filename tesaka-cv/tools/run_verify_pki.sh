#!/usr/bin/env bash
set -euo pipefail

# Wrapper para sifen_verify_pki_bundle.py
# Resuelve repo root y ejecuta con defaults razonables

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Cambiar al directorio del repo
cd "$REPO_ROOT"

# Defaults
XML_DEFAULT="/tmp/sifen_preval/smoke_python_de_preval_signed.xml"
P12_DEFAULT="$HOME/.sifen/certs/F1T_65478.p12"
CA_DEFAULT="$HOME/.sifen/certs/ca-documenta.crt"
OUTDIR_DEFAULT="/tmp/sifen_verify_run"

# Ejecutar el script Python con .venv/bin/python, pasando todos los args
.venv/bin/python tools/sifen_verify_pki_bundle.py "$@"

EXIT_CODE=$?

echo ""
echo "Para ver logs detallados:"
echo "  cat /tmp/sifen_verify_run/fingerprints.txt"
echo "  cat /tmp/sifen_verify_run/openssl_verify.txt"
echo "  cat /tmp/sifen_verify_run/crypto_verify.txt"
echo "  cat /tmp/sifen_verify_run/summary.json"

exit $EXIT_CODE
