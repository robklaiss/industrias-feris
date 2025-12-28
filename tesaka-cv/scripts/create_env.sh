#!/bin/bash
# Script para crear archivo .env con configuración SIFEN
# Uso: ./scripts/create_env.sh

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

echo "============================================"
echo "Crear archivo .env para configuración SIFEN"
echo "============================================"
echo ""

# Verificar si .env ya existe
if [ -f "$ENV_FILE" ]; then
    echo "⚠️  El archivo .env ya existe."
    read -p "¿Deseas sobrescribirlo? (s/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        echo "❌ Operación cancelada."
        exit 1
    fi
fi

# Crear .env con valores de ejemplo
cat > "$ENV_FILE" << 'EOF'
# ============================================
# CONFIGURACIÓN SIFEN - Ambiente de Pruebas
# ============================================
#
# IMPORTANTE: Estos son valores de EJEMPLO para desarrollo básico.
# Para usar el ambiente de pruebas real, debes obtener valores oficiales de la SET.
#
# Ver: tesaka-cv/docs/DATOS_PRUEBA_SIFEN.md para más información
# Portal: https://ekuatia.set.gov.py

# ============================================
# AMBIENTE SIFEN
# ============================================
SIFEN_ENV=test

# ============================================
# DATOS DE PRUEBA (Ambiente Test)
# ============================================
# ⚠️ NOTA: Estos son valores de EJEMPLO para desarrollo básico.
# Para ambiente de pruebas real, contactar a la SET: consultas@set.gov.py
#
# RUC de prueba (formato: 7-9 dígitos)
SIFEN_TEST_RUC=80012345

# Número de timbrado de prueba (8 dígitos)
SIFEN_TEST_TIMBRADO=12345678

# CSC (Código de Seguridad del Contribuyente) de prueba
# Dejar vacío si no se tiene - el sistema usará valores por defecto
SIFEN_TEST_CSC=

# Razón social de prueba (opcional)
SIFEN_TEST_RAZON_SOCIAL=Contribuyente de Prueba S.A.

# ============================================
# CONFIGURACIÓN DE SERVICIOS
# ============================================
# Timeout para requests HTTP/SOAP (segundos)
SIFEN_REQUEST_TIMEOUT=30

# ============================================
# AUTENTICACIÓN (Opcional - para envío real)
# ============================================
# Solo necesario si se va a enviar documentos reales al ambiente de pruebas
SIFEN_USE_MTLS=false

# Certificado digital (.p12 o .pfx) - Solo si SIFEN_USE_MTLS=true
# SIFEN_CERT_PATH=/ruta/al/certificado.p12
# SIFEN_CERT_PASSWORD=password_del_certificado
# SIFEN_CA_BUNDLE_PATH=/ruta/al/ca-bundle.pem
EOF

echo "✅ Archivo .env creado en: $ENV_FILE"
echo ""
echo "📝 Próximos pasos:"
echo "   1. Revisar el archivo: $ENV_FILE"
echo "   2. Si tienes valores oficiales de la SET, editar y reemplazar los valores de ejemplo"
echo "   3. Ver documentación: tesaka-cv/docs/DATOS_PRUEBA_SIFEN.md"
echo ""

