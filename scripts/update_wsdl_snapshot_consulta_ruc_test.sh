#!/bin/bash
#
# Actualiza el snapshot WSDL de consultaRUC desde SIFEN TEST
#
# Requiere tener /tmp/sifen_cert.pem y /tmp/sifen_key.pem (llama automáticamente
# al script de export si no existen).
#
# Uso:
#   bash scripts/update_wsdl_snapshot_consulta_ruc_test.sh
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

# URLs y rutas
WSDL_URL="https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl?wsdl"
WSDL_SNAPSHOT_DIR="${REPO_ROOT}/tesaka-cv/wsdl_snapshots"
WSDL_SNAPSHOT="${WSDL_SNAPSHOT_DIR}/consulta-ruc_test.wsdl"

# Archivos PEM temporales
CERT_PEM="/tmp/sifen_cert.pem"
KEY_PEM="/tmp/sifen_key.pem"

echo -e "${BLUE}📥 Descargando snapshot WSDL de consultaRUC${NC}"
echo ""

# Verificar que los archivos PEM existen, si no, llamar al script de export
if [ ! -f "$CERT_PEM" ] || [ ! -f "$KEY_PEM" ]; then
    echo -e "${YELLOW}⚠️  Archivos PEM no encontrados, ejecutando export...${NC}"
    echo ""
    bash "${SCRIPT_DIR}/sifen_export_p12_to_pem.sh"
    echo ""
fi

# Validar que los PEM existen y tienen contenido
if [ ! -f "$CERT_PEM" ] || [ ! -s "$CERT_PEM" ]; then
    echo -e "${RED}❌ Error: Certificado PEM no encontrado o vacío: ${CERT_PEM}${NC}"
    exit 1
fi

if [ ! -f "$KEY_PEM" ] || [ ! -s "$KEY_PEM" ]; then
    echo -e "${RED}❌ Error: Clave PEM no encontrada o vacía: ${KEY_PEM}${NC}"
    exit 1
fi

# Validar que curl está disponible
if ! command -v curl >/dev/null 2>&1; then
    echo -e "${RED}❌ Error: curl no está disponible${NC}"
    exit 1
fi

# Crear directorio de snapshots si no existe
mkdir -p "$WSDL_SNAPSHOT_DIR"

# Si el directorio está vacío, agregar .gitkeep
if [ ! -f "${WSDL_SNAPSHOT_DIR}/.gitkeep" ] && [ -z "$(ls -A "${WSDL_SNAPSHOT_DIR}" 2>/dev/null)" ]; then
    touch "${WSDL_SNAPSHOT_DIR}/.gitkeep"
fi

echo -e "${BLUE}🌐 Descargando WSDL desde: ${WSDL_URL}${NC}"
echo ""

# Descargar WSDL con mTLS
HTTP_CODE=$(curl -sS \
    --cert "$CERT_PEM" \
    --key "$KEY_PEM" \
    --output "$WSDL_SNAPSHOT" \
    --write-out "%{http_code}" \
    --max-time 30 \
    --fail-with-body \
    "$WSDL_URL" 2>&1) || true

# Validar descarga
if [ "$HTTP_CODE" != "200" ]; then
    echo -e "${RED}❌ Error: HTTP ${HTTP_CODE} al descargar WSDL${NC}"
    if [ -f "$WSDL_SNAPSHOT" ]; then
        echo ""
        echo "Contenido recibido:"
        cat "$WSDL_SNAPSHOT" | head -20
        rm -f "$WSDL_SNAPSHOT"
    fi
    exit 1
fi

if [ ! -f "$WSDL_SNAPSHOT" ] || [ ! -s "$WSDL_SNAPSHOT" ]; then
    echo -e "${RED}❌ Error: WSDL descargado está vacío${NC}"
    exit 1
fi

# Validar que contiene WSDL válido
if ! grep -q "wsdl:definitions" "$WSDL_SNAPSHOT"; then
    echo -e "${RED}❌ Error: El archivo descargado no parece ser un WSDL válido${NC}"
    echo ""
    echo "Contenido:"
    cat "$WSDL_SNAPSHOT" | head -20
    rm -f "$WSDL_SNAPSHOT"
    exit 1
fi

SNAPSHOT_SIZE=$(stat -f%z "$WSDL_SNAPSHOT" 2>/dev/null || stat -c%s "$WSDL_SNAPSHOT" 2>/dev/null || echo "0")

echo -e "${GREEN}✅ WSDL snapshot actualizado${NC}"
echo ""
echo "Archivo: ${WSDL_SNAPSHOT}"
echo "Tamaño: ${SNAPSHOT_SIZE} bytes"
echo ""
echo -e "${BLUE}📋 Validaciones:${NC}"
echo "  ✅ Contiene 'wsdl:definitions'"
echo "  ✅ Tamaño > 0 bytes"
echo ""

# Intentar extraer información útil
if grep -q "rEnviConsRUC" "$WSDL_SNAPSHOT"; then
    echo -e "  ${GREEN}✅ Contiene operación 'rEnviConsRUC'${NC}"
else
    echo -e "  ${YELLOW}⚠️  No se encontró operación 'rEnviConsRUC'${NC}"
fi

if grep -q "soap12:address" "$WSDL_SNAPSHOT" || grep -q "soap:address" "$WSDL_SNAPSHOT"; then
    echo -e "  ${GREEN}✅ Contiene endpoint SOAP address${NC}"
else
    echo -e "  ${YELLOW}⚠️  No se encontró SOAP address${NC}"
fi

echo ""
echo -e "${GREEN}✅ Snapshot WSDL actualizado correctamente${NC}"
echo ""
echo "Para ejecutar el contract test:"
echo "  bash scripts/check_sifen_contracts.sh"
echo ""
