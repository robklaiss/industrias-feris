#!/bin/bash
# Script de prueba para el endpoint POST /send-de

# Configuración
API_URL="http://127.0.0.1:8009"
ENV=${1:-"test"}

echo "🧪 Probando endpoint POST /send-de en $API_URL"
echo "   Environment: $ENV"
echo ""

# Payload de prueba
PAYLOAD='{
  "env": "'$ENV'",
  "payload": {
    "tipo_documento": "01",
    "numero_documento": "001-001-0000001",
    "fecha_emision": "2026-01-23",
    "cliente": {
      "ruc": "80012345",
      "dv": "7",
      "nombre": "Cliente de Prueba"
    },
    "items": [
      {
        "descripcion": "Producto de prueba",
        "cantidad": 1,
        "precio": 100000
      }
    ]
  }
}'

# Ejecutar curl con headers adecuados
echo "📤 Enviando request..."
echo ""

curl -s -X POST "$API_URL/send-de" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d "$PAYLOAD" | jq '.' 2>/dev/null || {
    echo "❌ Error: jq no disponible. Mostrando respuesta raw:"
    curl -s -X POST "$API_URL/send-de" \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d "$PAYLOAD"
  }

echo ""
echo ""
echo "✅ Prueba completada. Verificar que:"
echo "   - Content-Type sea application/json"
echo "   - La respuesta contenga meta.* con los campos esperados"
echo "   - CORS headers estén presentes (si se prueba desde browser)"
