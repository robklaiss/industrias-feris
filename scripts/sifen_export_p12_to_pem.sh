#!/bin/bash
#
# Exporta certificado P12 a archivos PEM temporales para uso con mTLS
#
# Este script pide el password del P12 de forma interactiva y exporta
# el certificado y la clave privada a /tmp/sifen_cert.pem y /tmp/sifen_key.pem
# con permisos 600.
#
# Uso:
#   export SIFEN_P12_PATH=/path/to/cert.p12  # opcional
#   bash scripts/sifen_export_p12_to_pem.sh
#

set -euo pipefail

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Resolver ruta del P12
P12_PATH="${SIFEN_P12_PATH:-${HOME}/.sifen/certs/F1T_65478.p12}"
CERT_PEM="/tmp/sifen_cert.pem"
KEY_PEM="/tmp/sifen_key.pem"

echo -e "${BLUE}🔐 Exportando certificado P12 a PEM${NC}"
echo ""

# Validar que el archivo P12 existe
if [ ! -f "$P12_PATH" ]; then
    echo -e "${RED}❌ Error: Certificado P12 no encontrado: ${P12_PATH}${NC}"
    echo ""
    echo "Solución:"
    echo "  export SIFEN_P12_PATH=/ruta/al/certificado.p12"
    echo "  bash scripts/sifen_export_p12_to_pem.sh"
    exit 1
fi

echo -e "📁 Archivo P12: ${P12_PATH}"
echo -e "📄 Certificado PEM: ${CERT_PEM}"
echo -e "🔑 Clave privada PEM: ${KEY_PEM}"
echo ""

# Verificar que openssl está disponible
if ! command -v openssl >/dev/null 2>&1; then
    echo -e "${RED}❌ Error: openssl no está disponible${NC}"
    echo ""
    echo "Solución: Instala OpenSSL"
    echo "  macOS: brew install openssl"
    exit 1
fi

# Extraer certificado (pedirá password interactivamente)
echo -e "${BLUE}🔍 Extrayendo certificado...${NC}"
echo "   (Se solicitará el password del P12)"
if openssl pkcs12 -in "$P12_PATH" -clcerts -nokeys 2>/dev/null | \
   openssl x509 -out "$CERT_PEM" 2>/dev/null; then
    echo -e "   ${GREEN}✅ Certificado exportado${NC}"
else
    echo -e "${RED}❌ Error: No se pudo extraer el certificado${NC}"
    echo "   Posibles causas:"
    echo "   - Password incorrecto"
    echo "   - Archivo P12 corrupto"
    echo "   - Permisos insuficientes"
    exit 1
fi

# Extraer clave privada (pedirá password interactivamente)
echo -e "${BLUE}🔍 Extrayendo clave privada...${NC}"
echo "   (Se solicitará el password del P12 nuevamente)"
if openssl pkcs12 -in "$P12_PATH" -nocerts -nodes 2>/dev/null | \
   openssl pkey -out "$KEY_PEM" 2>/dev/null; then
    echo -e "   ${GREEN}✅ Clave privada exportada${NC}"
else
    # Limpiar certificado si falla la clave
    rm -f "$CERT_PEM"
    echo -e "${RED}❌ Error: No se pudo extraer la clave privada${NC}"
    echo "   Posibles causas:"
    echo "   - Password incorrecto"
    echo "   - Archivo P12 corrupto"
    echo "   - Permisos insuficientes"
    exit 1
fi

# Establecer permisos 600
chmod 600 "$CERT_PEM"
chmod 600 "$KEY_PEM"

# Validar que los archivos tienen el contenido esperado
if ! grep -q "BEGIN CERTIFICATE" "$CERT_PEM" 2>/dev/null; then
    rm -f "$CERT_PEM" "$KEY_PEM"
    echo -e "${RED}❌ Error: El archivo de certificado PEM no contiene 'BEGIN CERTIFICATE'${NC}"
    exit 1
fi

if ! grep -q "BEGIN PRIVATE KEY" "$KEY_PEM" 2>/dev/null && \
   ! grep -q "BEGIN RSA PRIVATE KEY" "$KEY_PEM" 2>/dev/null; then
    rm -f "$CERT_PEM" "$KEY_PEM"
    echo -e "${RED}❌ Error: El archivo de clave PEM no contiene 'BEGIN PRIVATE KEY' ni 'BEGIN RSA PRIVATE KEY'${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Certificado y clave exportados correctamente${NC}"
echo ""
echo "Archivos creados:"
echo "  ${CERT_PEM} (permisos 600)"
echo "  ${KEY_PEM} (permisos 600)"
echo ""
echo -e "${YELLOW}⚠️  NOTA: Estos archivos son temporales. NO los compartas ni los commitées.${NC}"
echo ""
