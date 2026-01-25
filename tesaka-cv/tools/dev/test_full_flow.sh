#!/bin/bash
# Script para probar el flujo completo de emisión y seguimiento SIFEN TEST
set -e

echo "=== SIFEN TEST FULL FLOW ==="
echo "1) Emitir factura"
echo "2) Validar XML (firma, RUC, etc.)"
echo "3) Consultar estado (follow)"
echo ""

# Configuración
BASE_URL="http://localhost:8000"
TMP_DIR="/tmp/sifen_test_$$"
mkdir -p "$TMP_DIR"

# Payload de prueba
cat > "$TMP_DIR/emitir_payload.json" << 'EOF'
{
  "ruc": "04554737-8",
  "timbrado": "12560693",
  "establecimiento": "001",
  "punto_expedicion": "001",
  "numero_documento": "0000001",
  "env": "test"
}
EOF

echo "📤 Enviando a /api/v1/emitir..."
RESPONSE=$(curl -sS -X POST "$BASE_URL/api/v1/emitir" \
  -H "Content-Type: application/json" \
  -d @"$TMP_DIR/emitir_payload.json")

# Guardar respuesta
echo "$RESPONSE" | python3 -m json.tool > "$TMP_DIR/emitir_resp.json"

# Extraer datos clave
DID=$(jq -r '.dId' "$TMP_DIR/emitir_resp.json")
PROT=$(jq -r '.dProtConsLote' "$TMP_DIR/emitir_resp.json")
CDC=$(jq -r '.CDC' "$TMP_DIR/emitir_resp.json")
STATUS=$(jq -r '.status' "$TMP_DIR/emitir_resp.json")
SUCCESS=$(jq -r '.success' "$TMP_DIR/emitir_resp.json")

echo ""
echo "📋 Respuesta:"
echo "   dId: $DID"
echo "   CDC: $CDC"
echo "   dProtConsLote: $PROT"
echo "   status: $STATUS"
echo "   success: $SUCCESS"

if [ "$SUCCESS" != "true" ]; then
    echo "❌ Error en emisión"
    cat "$TMP_DIR/emitir_resp.json"
    exit 1
fi

# Descargar XML DE
echo ""
echo "📥 Descargando XML DE..."
curl -sS "$BASE_URL/api/v1/artifacts/$DID/de" > "$TMP_DIR/DE_$DID.xml"

# Validaciones
echo ""
echo "🔍 Validaciones:"

# 1) Verificar que no hay SHA-1
if grep -q -i "rsa-sha1\|xmldsig#sha1" "$TMP_DIR/DE_$DID.xml"; then
    echo "   ❌ SHA-1 encontrado (debe ser SHA-256)"
else
    echo "   ✅ Sin SHA-1 (correcto)"
fi

# 2) Verificar que no hay firma dummy
if grep -q "dGhpcyBpcyBhIHRlc3Q" "$TMP_DIR/DE_$DID.xml"; then
    echo "   ❌ Firma dummy/placeholder encontrada"
else
    echo "   ✅ Sin firma dummy (correcto)"
fi

# 3) Verificar dRucEm sin cero inicial
RUC_EM=$(grep -o '<dRucEm>[^<]*' "$TMP_DIR/DE_$DID.xml" | sed 's/<dRucEm>//')
if [ "${RUC_EM:0:1}" = "0" ]; then
    echo "   ❌ dRucEm tiene cero inicial: $RUC_EM"
else
    echo "   ✅ dRucEm sin cero inicial: $RUC_EM"
fi

# 4) Verificar firma RSA-SHA256
if grep -q "rsa-sha256" "$TMP_DIR/DE_$DID.xml"; then
    echo "   ✅ Firma RSA-SHA256 encontrada"
else
    echo "   ❌ No se encuentra RSA-SHA256"
fi

# 5) Verificar Digest SHA-256
if grep -q "xmlenc#sha256" "$TMP_DIR/DE_$DID.xml"; then
    echo "   ✅ Digest SHA-256 encontrado"
else
    echo "   ❌ No se encuentra Digest SHA-256"
fi

# Consultar estado
if [ -n "$PROT" ] && [ "$PROT" != "" ] && [ "$PROT" != "null" ]; then
    echo ""
    echo "📞 Consultando estado (follow)..."
    FOLLOW_RESP=$(curl -sS "$BASE_URL/api/v1/follow?prot=$PROT")
    echo "$FOLLOW_RESP" | python3 -m json.tool > "$TMP_DIR/follow_resp.json"
    
    FOLLOW_STATE=$(jq -r '.estado' "$TMP_DIR/follow_resp.json")
    FOLLOW_CODE=$(jq -r '.dCodRes' "$TMP_DIR/follow_resp.json")
    FOLLOW_MSG=$(jq -r '.dMsgRes' "$TMP_DIR/follow_resp.json")
    
    echo ""
    echo "📋 Respuesta follow:"
    echo "   estado: $FOLLOW_STATE"
    echo "   código: $FOLLOW_CODE"
    echo "   mensaje: $FOLLOW_MSG"
    
    if [ "$FOLLOW_CODE" = "0160" ]; then
        echo "   ❌ Error 0160 - XML mal formado"
    elif [ "$FOLLOW_CODE" = "01" ]; then
        echo "   ✅ Aprobado"
    elif [ "$FOLLOW_CODE" = "02" ]; then
        echo "   ⚠️  Rechazado"
    else
        echo "   ⏳ Estado intermedio"
    fi
else
    echo ""
    echo "❌ No se puede consultar follow: dProtConsLote vacío"
fi

# Guardar artifacts para análisis
echo ""
echo "💾 Archivos guardados en: $TMP_DIR"
ls -la "$TMP_DIR"

echo ""
echo "=== RESUMEN ==="
if [ "$SUCCESS" = "true" ] && [ -n "$PROT" ] && [ "$PROT" != "" ] && [ "$PROT" != "null" ]; then
    echo "✅ Flujo completo exitoso"
    echo "   - Emisión: OK"
    echo "   - dProtConsLote: $PROT"
    echo "   - Estado: $FOLLOW_STATE"
else
    echo "❌ Problemas detectados"
    echo "   - Revisar archivos en $TMP_DIR"
fi

# Opcional: abrir directorio
if command -v open >/dev/null 2>&1; then
    echo ""
    read -p "¿Abrir directorio $TMP_DIR? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        open "$TMP_DIR"
    fi
fi
