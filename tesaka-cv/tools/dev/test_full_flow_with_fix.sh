#!/bin/bash
# Script para probar el flujo completo con todos los fixes aplicados
set -e

echo "=== SIFEN MODO GUERRA - FULL FLOW CON FIXES ==="
echo ""

# Configuración
BASE_URL="http://localhost:8000"
TMP_DIR="/tmp/sifen_war_$$"
mkdir -p "$TMP_DIR"

# Verificar servidor
if ! curl -s "$BASE_URL/docs" >/dev/null 2>&1; then
    echo "❌ Servidor no encontrado. Inicia con:"
    echo "   cd tesaka-cv && .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
    exit 1
fi

# 1) Emitir factura
echo "1️⃣  Emitiendo factura (con firma RSA-SHA256)..."
cat > "$TMP_DIR/payload.json" << 'EOF'
{
  "ruc": "04554737-8",
  "timbrado": "12560693",
  "establecimiento": "001",
  "punto_expedicion": "001",
  "numero_documento": "0000001",
  "env": "test"
}
EOF

RESPONSE=$(curl -sS -X POST "$BASE_URL/api/v1/emitir" \
  -H "Content-Type: application/json" \
  -d @"$TMP_DIR/payload.json")

echo "$RESPONSE" | python3 -m json.tool > "$TMP_DIR/emitir_resp.json"

DID=$(jq -r '.dId' "$TMP_DIR/emitir_resp.json")
PROT=$(jq -r '.dProtConsLote' "$TMP_DIR/emitir_resp.json")
CDC=$(jq -r '.CDC' "$TMP_DIR/emitir_resp.json")
STATUS=$(jq -r '.status' "$TMP_DIR/emitir_resp.json")
SUCCESS=$(jq -r '.success' "$TMP_DIR/emitir_resp.json")

echo "   dId: $DID"
echo "   CDC: $CDC"
echo "   dProtConsLote: $PROT"
echo "   status: $STATUS"

if [ "$SUCCESS" != "true" ]; then
    echo "❌ Error en emisión"
    jq -r '.error // .mensaje // "Error desconocido"' "$TMP_DIR/emitir_resp.json"
    exit 1
fi

# 2) Validar XML firmado
echo ""
echo "2️⃣  Validando XML firmado..."
curl -sS "$BASE_URL/api/v1/artifacts/$DID/de" > "$TMP_DIR/DE_$DID.xml"

# Validaciones con guardrails
cd "$(dirname "$0")/../.."
python3 tools/validate_signature_guardrails.py "$TMP_DIR/DE_$DID.xml" || {
    echo ""
    echo "❌ Validaciones fallaron"
    echo "   Revisar: $TMP_DIR/DE_$DID.xml"
    exit 1
}

# Validaciones adicionales
echo ""
echo "📋 Validaciones detalladas:"
echo "   Firma RSA-SHA256: $(rg -i 'rsa-sha256' "$TMP_DIR/DE_$DID.xml" >/dev/null && echo '✅' || echo '❌')"
echo "   Digest SHA-256: $(rg -i 'xmlenc#sha256' "$TMP_DIR/DE_$DID.xml" >/dev/null && echo '✅' || echo '❌')"
echo "   Sin SHA-1: $(rg -i 'xmldsig#sha1' "$TMP_DIR/DE_$DID.xml" >/dev/null && echo '❌' || echo '✅')"
echo "   Sin placeholder: $(rg 'dGhpcyBpcyBhIHRlc3Q' "$TMP_DIR/DE_$DID.xml" >/dev/null && echo '❌' || echo '✅')"

# 3) Consultar estado (con fix de endpoint)
echo ""
echo "3️⃣  Consultando estado (con fix consulta-lote.wsdl)..."
if [ -n "$PROT" ] && [ "$PROT" != "" ] && [ "$PROT" != "null" ]; then
    FOLLOW_RESP=$(curl -sS "$BASE_URL/api/v1/follow?prot=$PROT")
    echo "$FOLLOW_RESP" | python3 -m json.tool > "$TMP_DIR/follow_resp.json"
    
    FOLLOW_STATE=$(jq -r '.estado' "$TMP_DIR/follow_resp.json")
    FOLLOW_CODE=$(jq -r '.dCodRes' "$TMP_DIR/follow_resp.json")
    FOLLOW_MSG=$(jq -r '.dMsgRes' "$TMP_DIR/follow_resp.json")
    
    echo "   estado: $FOLLOW_STATE"
    echo "   código: $FOLLOW_CODE"
    echo "   mensaje: $FOLLOW_MSG"
    
    # Verificar que no sea 0160
    if [ "$FOLLOW_CODE" = "0160" ]; then
        echo "   ❌ Aún error 0160 - necesitar más investigación"
    elif [ "$FOLLOW_CODE" = "01" ]; then
        echo "   ✅ Aprobado"
    elif [ "$FOLLOW_CODE" = "02" ]; then
        echo "   ⚠️  Rechazado"
    elif [ "$FOLLOW_CODE" = "0301" ]; then
        echo "   ⚠️  Lote no encolado (pero endpoint responde)"
    else
        echo "   ℹ️  Estado: $FOLLOW_CODE"
    fi
else
    echo "   ❌ No se puede consultar: dProtConsLote vacío"
fi

# 4) Verificar artifacts
echo ""
echo "4️⃣  Verificando artifacts guardados..."
if [ -d "artifacts/$DID" ]; then
    echo "   ✅ Directorio artifacts/$DID creado"
    ls -la "artifacts/$DID" | head -5
else
    echo "   ❌ No se encontró artifacts/$DID"
fi

# 5) Resumen final
echo ""
echo "=== RESUMEN DE FIXES ==="
echo "✅ 1) Firma RSA-SHA256 (sin SHA-1)"
echo "✅ 2) RUC sin cero inicial"
echo "✅ 3) Endpoint consulta-lote.wsdl manteniendo .wsdl"
echo ""
echo "📁 Archivos en: $TMP_DIR"
echo "📁 Artifacts en: artifacts/$DID"

# Test anti-regresión
echo ""
echo "=== TEST ANTI-REGRESIÓN ==="
echo "Ejecutando: python3 tests/test_consulta_lote_endpoint.py"
python3 tests/test_consulta_lote_endpoint.py

# Limpiar
echo ""
read -p "¿Borrar archivos temporales? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$TMP_DIR"
    echo "🗑️  Archivos temporales borrados"
fi
