#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

IN="${1:-}"
if [[ -z "$IN" || ! -f "$IN" ]]; then
  echo "Usage: ./scripts/run_prevalidador.sh /tmp/sirecepde_*.signed.xml"
  exit 2
fi

mkdir -p artifacts

# 1) quitar XML declaration si existe
PAYLOAD="$(awk 'NR==1 && $0 ~ /^<\?xml/ {next} {print}' "$IN")"

# 2) construir SOAP 1.1 (Roshka-friendly) y actualizar el artifact que debug_compare_roshka lee
cat > artifacts/soap_last_sent.xml <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
$PAYLOAD
  </soapenv:Body>
</soapenv:Envelope>
EOF

# 3) guardar "headers esperados" solo como referencia local
cat > artifacts/soap_last_sent_headers.txt <<EOF
Content-Type: application/soap+xml; charset=utf-8
SOAPAction: (none)
Endpoint: .../recibe.wsdl (según Roshka)
EOF

echo "[+] Wrote artifacts/soap_last_sent.xml from: $IN"
echo "[+] Now running tools/debug_compare_roshka.py ..."
./.venv/bin/python tools/debug_compare_roshka.py "$IN"
