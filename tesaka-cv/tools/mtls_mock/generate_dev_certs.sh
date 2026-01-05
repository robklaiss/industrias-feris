#!/usr/bin/env bash
# Genera certificados DEV para el mock server mTLS (NO para producción)
# Uso: ./generate_dev_certs.sh

set -euo pipefail

CERT_DIR="$(cd "$(dirname "$0")" && pwd)/certs"
ARTIFACTS_DIR="$(cd "$(dirname "$0")" && pwd)/artifacts"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Generando certificados DEV para mTLS Mock Server ===${NC}"

# Crear directorios si no existen
mkdir -p "$CERT_DIR"
mkdir -p "$ARTIFACTS_DIR"

cd "$CERT_DIR"

# 1. CA (Certificate Authority) DEV
echo -e "\n${YELLOW}1. Generando CA DEV...${NC}"
openssl genrsa -out ca-dev.key 2048
openssl req -new -x509 -days 3650 -key ca-dev.key -out ca-dev.crt \
    -subj "/C=PY/ST=Asuncion/L=Asuncion/O=DEV-SIFEN-MOCK/CN=ca-dev-mock"

# 2. Server cert (para el mock server)
echo -e "\n${YELLOW}2. Generando certificado del servidor...${NC}"
openssl genrsa -out server-dev.key 2048
openssl req -new -key server-dev.key -out server-dev.csr \
    -subj "/C=PY/ST=Asuncion/L=Asuncion/O=DEV-SIFEN-MOCK/CN=localhost"
# Crear extensiones para SAN (Subject Alternative Name)
cat > server-dev.ext <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
subjectAltName=@alt_names

[alt_names]
DNS.1=localhost
DNS.2=*.localhost
IP.1=127.0.0.1
IP.2=::1
EOF
openssl x509 -req -in server-dev.csr -CA ca-dev.crt -CAkey ca-dev.key \
    -CAcreateserial -out server-dev.crt -days 3650 -extfile server-dev.ext

# 3. Client cert (para el cliente de prueba)
echo -e "\n${YELLOW}3. Generando certificado del cliente...${NC}"
openssl genrsa -out client-dev.key 2048
openssl req -new -key client-dev.key -out client-dev.csr \
    -subj "/C=PY/ST=Asuncion/L=Asuncion/O=DEV-SIFEN-MOCK/CN=client-dev-mock"
openssl x509 -req -in client-dev.csr -CA ca-dev.crt -CAkey ca-dev.key \
    -CAcreateserial -out client-dev.crt -days 3650

# 4. Crear P12 del cliente (para compatibilidad con el flujo real)
echo -e "\n${YELLOW}4. Creando P12 del cliente...${NC}"
openssl pkcs12 -export -out client-dev.p12 \
    -inkey client-dev.key -in client-dev.crt -certfile ca-dev.crt \
    -passout pass:dev123 \
    -name "client-dev-mock"

# 5. Crear bundle CA (para verificación del cliente)
echo -e "\n${YELLOW}5. Creando bundle CA...${NC}"
cp ca-dev.crt ca-bundle-dev.crt

# Limpiar archivos temporales
rm -f server-dev.csr server-dev.ext *.srl

echo -e "\n${GREEN}=== Certificados generados exitosamente ===${NC}"
echo -e "${GREEN}Directorio: $CERT_DIR${NC}"
echo -e "\n${YELLOW}Archivos generados:${NC}"
ls -lh "$CERT_DIR"

echo -e "\n${YELLOW}Para usar con el cliente:${NC}"
echo -e "  Cert: $CERT_DIR/client-dev.crt"
echo -e "  Key:  $CERT_DIR/client-dev.key"
echo -e "  P12:  $CERT_DIR/client-dev.p12 (password: dev123)"
echo -e "  CA:   $CERT_DIR/ca-bundle-dev.crt"

echo -e "\n${YELLOW}Para el servidor mock:${NC}"
echo -e "  Cert: $CERT_DIR/server-dev.crt"
echo -e "  Key:  $CERT_DIR/server-dev.key"
echo -e "  CA:   $CERT_DIR/ca-dev.crt"

echo -e "\n${RED}⚠️  ADVERTENCIA: Estos certificados son SOLO para desarrollo local.${NC}"
echo -e "${RED}   NO usar en producción ni commitear al repositorio.${NC}"

