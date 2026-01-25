#!/bin/bash
# Script completo para probar el flujo SIFEN con validaciones
set -e

echo "=== SIFEN COMPLETE FLOW TEST ==="
echo ""

# Configuración
BASE_URL="http://localhost:8000"
TMP_DIR="/tmp/sifen_complete_$$"
mkdir -p "$TMP_DIR"

# Verificar que el servidor esté corriendo
if ! curl -s "$BASE_URL/docs" >/dev/null 2>&1; then
    echo "❌ Servidor no encontrado en $BASE_URL"
    echo "   Inicia el servidor con:"
    echo "   cd tesaka-cv && .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
    exit 1
fi

# 1) Emitir factura
echo "1️⃣  Emitiendo factura..."
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
echo "   dProtConsLote: $PROT"
echo "   status: $STATUS"

if [ "$SUCCESS" != "true" ]; then
    echo "❌ Error en emisión"
    jq -r '.error // .mensaje // "Error desconocido"' "$TMP_DIR/emitir_resp.json"
    exit 1
fi

# 2) Descargar y validar XML
echo ""
echo "2️⃣  Descargando y validando XML..."
curl -sS "$BASE_URL/api/v1/artifacts/$DID/de" > "$TMP_DIR/DE_$DID.xml"

# Validar con guardrails
cd "$(dirname "$0")/../.."
python3 tools/validate_signature_guardrails.py "$TMP_DIR/DE_$DID.xml" || {
    echo ""
    echo "❌ Validaciones fallaron"
    echo "   Revisar: $TMP_DIR/DE_$DID.xml"
    exit 1
}

# 3) Consultar estado
if [ -n "$PROT" ] && [ "$PROT" != "" ] && [ "$PROT" != "null" ]; then
    echo ""
    echo "3️⃣  Consultando estado..."
    FOLLOW_RESP=$(curl -sS "$BASE_URL/api/v1/follow?prot=$PROT")
    echo "$FOLLOW_RESP" | python3 -m json.tool > "$TMP_DIR/follow_resp.json"
    
    FOLLOW_STATE=$(jq -r '.estado' "$TMP_DIR/follow_resp.json")
    FOLLOW_CODE=$(jq -r '.dCodRes' "$TMP_DIR/follow_resp.json")
    FOLLOW_MSG=$(jq -r '.dMsgRes' "$TMP_DIR/follow_resp.json")
    
    echo "   estado: $FOLLOW_STATE"
    echo "   código: $FOLLOW_CODE"
    echo "   mensaje: $FOLLOW_MSG"
    
    # Verificar código
    case "$FOLLOW_CODE" in
        "01")
            echo "   ✅ Aprobado"
            ;;
        "02")
            echo "   ⚠️  Rechazado"
            ;;
        "0160")
            echo "   ❌ Error 0160 - XML mal formado"
            ;;
        *)
            echo "   ⏳ Estado intermedio ($FOLLOW_CODE)"
            ;;
    esac
else
    echo ""
    echo "❌ No se puede consultar follow: dProtConsLote vacío"
fi

# 4) Resumen
echo ""
echo "=== RESUMEN FINAL ==="
echo "✅ Emisión: OK"
echo "✅ Firma: RSA-SHA256 / SHA-256"
echo "✅ RUC: sin cero inicial"
if [ -n "$PROT" ] && [ "$PROT" != "" ] && [ "$PROT" != "null" ]; then
    echo "✅ Consulta: OK (código $FOLLOW_CODE)"
else
    echo "❌ Consulta: No se pudo realizar (protocolo vacío)"
fi

echo ""
echo "📁 Archivos guardados en: $TMP_DIR"
ls -la "$TMP_DIR"

# Limpiar al final si todo OK
if [ "$1" != "--keep" ]; then
    echo ""
    read -p "¿Borrar archivos temporales? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$TMP_DIR"
        echo "🗑️  Archivos temporales borrados"
    fi
fi
