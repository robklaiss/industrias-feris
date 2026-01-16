#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Load SIFEN environment (cert paths, password, PYTHONPATH, etc.)
source "$ROOT/scripts/sifen_env.sh"

echo "[+] Working dir: $PWD"

PY="$PWD/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "[-] ERROR: venv python not found: $PY"
  exit 1
fi

IN="${1:-}"
if [ -z "$IN" ] || [ ! -f "$IN" ]; then
  echo "Usage: $0 <path-to-sirecepde.xml>"
  exit 2
fi

# P12 path
if [ -z "${SIFEN_P12_PATH:-}" ]; then
  echo "[-] SIFEN_P12_PATH not set. Example:"
  echo 'export SIFEN_P12_PATH="/Users/you/.sifen/certs/F1T_65478.p12"'
  exit 3
fi
if [ ! -f "$SIFEN_P12_PATH" ]; then
  echo "[-] ERROR: SIFEN_P12_PATH does not exist: $SIFEN_P12_PATH"
  exit 3
fi

# Password (persist in THIS process, and pass explicitly)
if [ -z "${SIFEN_SIGN_P12_PASSWORD:-}" ]; then
  read -s -p "Enter P12 password: " SIFEN_SIGN_P12_PASSWORD
  echo
  export SIFEN_SIGN_P12_PASSWORD
fi

# Output naming: avoid signed.signed.xml
OUT="$IN"
if [[ "$OUT" == *.signed.xml ]]; then
  OUT="${OUT%.signed.xml}.resigned.xml"
else
  OUT="${OUT%.xml}.signed.xml"
fi

echo "[+] INPUT=$IN"
echo "[+] OUT=$OUT"
echo "[+] Using P12=$(basename "$SIFEN_P12_PATH")"
echo "[+] Password len=${#SIFEN_SIGN_P12_PASSWORD}"

# Sign
"$PY" -m tools.debug_sign_de \
  --xml "$IN" \
  --output "$OUT" \
  --p12 "$SIFEN_P12_PATH" \
  --password "$SIFEN_SIGN_P12_PASSWORD"

# Verify location
"$PY" -m tools.verify_sig_location "$OUT"
