#!/usr/bin/env bash
# scripts/sign_sirecepde.sh
set -euo pipefail

cd "$(dirname "$0")/.."
echo "[+] Working dir: $(pwd)"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <path-to-sirecepde.xml>"
  exit 1
fi

INPUT_XML="$1"
if [[ ! -f "$INPUT_XML" ]]; then
  echo "[-] File not found: $INPUT_XML"
  exit 1
fi

if [[ -z "${SIFEN_P12_PATH:-}" ]]; then
  echo "[-] SIFEN_P12_PATH not set. Example:"
  echo "export SIFEN_P12_PATH=\"/Users/you/.sifen/certs/F1T_65478.p12\""
  exit 1
fi
if [[ ! -f "$SIFEN_P12_PATH" ]]; then
  echo "[-] Certificate not found: $SIFEN_P12_PATH"
  exit 1
fi

if [[ -z "${SIFEN_SIGN_P12_PASSWORD:-}" ]]; then
  echo -n "Enter P12 password: "
  read -s SIFEN_SIGN_P12_PASSWORD
  export SIFEN_SIGN_P12_PASSWORD
  echo
fi

OUT_XML="${INPUT_XML%.xml}.signed.xml"
echo "[+] Signing: $INPUT_XML -> $OUT_XML"

.venv/bin/python -m tools.debug_sign_de "$INPUT_XML" "$OUT_XML"

echo "[+] Verifying signature location..."
.venv/bin/python -m tools.verify_sig_location "$OUT_XML"
