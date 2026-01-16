#!/bin/bash
# Script para ejecutar smoketest con certificado real
# Configurar estas variables antes de ejecutar:

# IMPORTANTE: Configurar estas variables con tus valores reales
export SIFEN_CERT_PATH="/Users/robinklaiss/.sifen/certs/TU_CERT_REAL.p12"
export SIFEN_CERT_PASS="tu_password_real"
export SIFEN_CSC="12345678"  # Código de Seguridad del Contribuyente

# Verificar que las variables estén configuradas
if [ -z "$SIFEN_CERT_PATH" ] || [ "$SIFEN_CERT_PATH" = "/Users/robinklaiss/.sifen/certs/TU_CERT_REAL.p12" ]; then
    echo "❌ ERROR: Debes configurar SIFEN_CERT_PATH con tu certificado real"
    echo "   Edita este script y cambia TU_CERT_REAL.p12 por tu certificado"
    exit 1
fi

if [ -z "$SIFEN_CERT_PASS" ] || [ "$SIFEN_CERT_PASS" = "tu_password_real" ]; then
    echo "❌ ERROR: Debes configurar SIFEN_CERT_PASS con tu contraseña real"
    echo "   Edita este script y cambia tu_password_real por tu contraseña"
    exit 1
fi

if [ ! -f "$SIFEN_CERT_PATH" ]; then
    echo "❌ ERROR: Certificado no existe: $SIFEN_CERT_PATH"
    exit 1
fi

echo "✅ Configuración:"
echo "   SIFEN_CERT_PATH: $SIFEN_CERT_PATH"
echo "   SIFEN_CERT_PASS: ********"
echo "   SIFEN_CSC: $SIFEN_CSC"
echo ""

# Ejecutar smoketest
.venv/bin/python tools/smoketest.py --input tools/de_input.json --artifacts-dir /tmp/sifen_smoketest_artifacts
