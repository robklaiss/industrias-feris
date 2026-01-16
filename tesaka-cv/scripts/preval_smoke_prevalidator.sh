#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Load SIFEN environment (cert paths, password, PYTHONPATH, etc.)
if [[ -f "$ROOT/scripts/sifen_env.sh" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT/scripts/sifen_env.sh"
fi

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

IN_XML="${1:-}"
if [[ -z "$IN_XML" ]]; then
  TIMBRADO="${SIFEN_TIMBRADO:-12345678}"
  DE_XML="/tmp/preval_smoke_de.xml"
  SIRECEPDE_XML="/tmp/preval_smoke_sirecepde.xml"

  rm -f "$DE_XML" "$SIRECEPDE_XML" "/tmp/preval_smoke.signed.xml"

  echo "[+] Generating fresh DE/siRecepDE (timbrado=$TIMBRADO)"
  "$PY" -m tools.build_de --timbrado "$TIMBRADO" --output "$DE_XML"
  # IMPORTANT: do NOT sign here (tools.build_sirecepde uses signxml). We sign later with xmlsec.
  SIFEN_SIGN_P12_PATH= SIFEN_SIGN_P12_PASSWORD= "$PY" -m tools.build_sirecepde --de "$DE_XML" --output "$SIRECEPDE_XML" --did 1

  IN_XML="$SIRECEPDE_XML"
fi

if [[ ! -f "$IN_XML" ]]; then
  echo "Input not found: $IN_XML" >&2
  exit 2
fi

OUT_SIGNED="/tmp/preval_smoke.signed.xml"

set -x
"$PY" -m tools.debug_sign_de --xml "$IN_XML" --output "$OUT_SIGNED" --p12 "$SIFEN_P12_PATH" --password "$SIFEN_SIGN_P12_PASSWORD"
"$PY" -m tools.verify_sig_location "$OUT_SIGNED"

"$PY" -m tools.export_prevalidator_upload "$OUT_SIGNED" --out "$HOME/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml"
"$PY" -m tools.verify_sig_location "$HOME/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml"

grep -q "<dDesPaisRe>" "$HOME/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml" || echo "WARN: no se encontró <dDesPaisRe> en output"
if grep -q "<dDesPaisRec>" "$HOME/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml"; then
  echo "WARN: se encontró <dDesPaisRec> (tag incorrecto) en output"
fi

"$PY" -m tools.verify_xmlsec "$HOME/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml" || true
set +x

# Show final rDE attributes for verification
UPLOAD_FILE="$HOME/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml"
echo ""
echo "=== VERIFICACIÓN FINAL rDE ==="
echo "rDE@Id:"
sed -n 's/.*<rDE[^>]*Id="\([^"]*\)".*/\1/p' "$UPLOAD_FILE" | head -n1
echo "schemaLocation:"
sed -n 's/.*xsi:schemaLocation="\([^"]*\)".*/\1/p' "$UPLOAD_FILE" | head -n1
echo ""
echo "OK -> Archivo a subir: $UPLOAD_FILE"
