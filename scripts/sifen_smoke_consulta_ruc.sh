#!/bin/bash
#
# Smoke test para consultaRUC contra SIFEN TEST
#
# Requiere tener /tmp/sifen_cert.pem y /tmp/sifen_key.pem (llama automáticamente
# al script de export si no existen).
#
# Uso:
#   export SIFEN_RUC_CONS="80012345-7"  # requerido
#   export SIFEN_DID="1"                # opcional, default: 1
#   export SIFEN_ENV="test"             # opcional, default: test
#   bash scripts/sifen_smoke_consulta_ruc.sh
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

# Configuración
SIFEN_ENV="${SIFEN_ENV:-test}"
SIFEN_RUC_CONS="${SIFEN_RUC_CONS:-}"
SIFEN_DID="${SIFEN_DID:-1}"
SIFEN_SMOKE_ALLOW_0160="${SIFEN_SMOKE_ALLOW_0160:-0}"

# Validar RUC requerido
if [ -z "$SIFEN_RUC_CONS" ]; then
    echo -e "${RED}❌ Error: SIFEN_RUC_CONS es requerido${NC}"
    echo ""
    echo "Uso:"
    echo "  export SIFEN_RUC_CONS=\"80012345\""
    echo "  bash scripts/sifen_smoke_consulta_ruc.sh"
    exit 1
fi

# Función de normalización de RUC según reglas reales de Paraguay
# Reglas:
# - RUC nunca tiene letras (solo dígitos)
# - RUC tiene 7-8 dígitos totales (incluyendo DV)
# - Input puede venir con guión (ej: 4554737-8) o sin guión (45547378)
# - Output siempre sin guión, con DV incluido
normalize_ruc_py_rule() {
    local ruc_input="$1"
    local ruc_clean
    local base
    local dv
    local base_len
    local ruc_norm
    
    # Trim espacios
    ruc_clean=$(echo "$ruc_input" | tr -d ' ')
    
    if [ -z "$ruc_clean" ]; then
        echo "❌ Error: RUC no puede estar vacío" >&2
        return 2
    fi
    
    # Si contiene guión, separar
    if echo "$ruc_clean" | grep -q "-"; then
        base=$(echo "$ruc_clean" | cut -d'-' -f1)
        dv=$(echo "$ruc_clean" | cut -d'-' -f2)
        
        # Validar que base contenga solo dígitos
        if ! echo "$base" | grep -qE '^[0-9]+$'; then
            echo "❌ Error: RUC base contiene caracteres no numéricos: '${base}'. El RUC paraguayo solo contiene dígitos. Input: '${ruc_input}'" >&2
            echo "   Ejemplos válidos: 4554737-8, 45547378" >&2
            return 2
        fi
        
        # Validar longitud de base (debe ser 6 o 7 dígitos)
        base_len=${#base}
        if [ "$base_len" -lt 6 ] || [ "$base_len" -gt 7 ]; then
            echo "❌ Error: RUC base tiene longitud inválida: ${base_len} (debe ser 6 o 7 dígitos). Input: '${ruc_input}', Base: '${base}'" >&2
            echo "   Ejemplos válidos: 4554737-8 (7 base + 1 DV = 8 total), 455473-7 (6 base + 1 DV = 7 total)" >&2
            return 2
        fi
        
        # Validar que DV contenga solo dígitos y sea 1 caracter
        if [ -z "$dv" ]; then
            echo "❌ Error: RUC con guión debe incluir dígito verificador (DV). Input: '${ruc_input}'" >&2
            echo "   Ejemplo válido: 4554737-8" >&2
            return 2
        fi
        
        if ! echo "$dv" | grep -qE '^[0-9]+$'; then
            echo "❌ Error: Dígito verificador (DV) contiene caracteres no numéricos: '${dv}'. El DV debe ser un dígito. Input: '${ruc_input}'" >&2
            echo "   Ejemplo válido: 4554737-8" >&2
            return 2
        fi
        
        # Tomar solo el primer dígito del DV si tiene más de uno
        if [ ${#dv} -gt 1 ]; then
            dv="${dv:0:1}"
        fi
        
        # Concatenar base + dv
        ruc_norm="${base}${dv}"
        
        # Validar longitud final (debe ser 7 u 8 dígitos)
        if [ ${#ruc_norm} -lt 7 ] || [ ${#ruc_norm} -gt 8 ]; then
            echo "❌ Error: RUC normalizado tiene longitud inválida: ${#ruc_norm} (debe ser 7 u 8 dígitos). Input: '${ruc_input}', Normalizado: '${ruc_norm}'" >&2
            echo "   Ejemplos válidos: 45547378 (8 dígitos), 4554737 (7 dígitos)" >&2
            return 2
        fi
    else
        # No tiene guión, validar directamente
        # Eliminar cualquier carácter no numérico
        ruc_norm=$(echo "$ruc_clean" | tr -cd '0-9')
        
        if [ -z "$ruc_norm" ]; then
            echo "❌ Error: RUC no contiene dígitos válidos. Input: '${ruc_input}'" >&2
            echo "   Ejemplos válidos: 45547378 (8 dígitos), 4554737 (7 dígitos)" >&2
            return 2
        fi
        
        # Validar longitud (debe ser 7 u 8 dígitos)
        if [ ${#ruc_norm} -lt 7 ] || [ ${#ruc_norm} -gt 8 ]; then
            echo "❌ Error: RUC tiene longitud inválida: ${#ruc_norm} (debe ser 7 u 8 dígitos). Input: '${ruc_input}', Normalizado: '${ruc_norm}'" >&2
            echo "   Ejemplos válidos: 45547378 (8 dígitos), 4554737 (7 dígitos)" >&2
            return 2
        fi
    fi
    
    # Validación final estricta: regex ^[0-9]{7,8}$
    if ! echo "$ruc_norm" | grep -qE '^[0-9]{7,8}$'; then
        echo "❌ Error: RUC normalizado no cumple especificación: debe ser 7 u 8 dígitos. Input: '${ruc_input}', Normalizado: '${ruc_norm}'" >&2
        echo "   Ejemplos válidos: 45547378 (8 dígitos), 4554737 (7 dígitos)" >&2
        return 2
    fi
    
    # Retornar valor normalizado (echo a stdout)
    echo "$ruc_norm"
    return 0
}

echo -e "${BLUE}📋 Normalizando RUC según especificación SIFEN...${NC}"
echo "   Input SIFEN_RUC_CONS: ${SIFEN_RUC_CONS}"

# Normalizar RUC
RUC_NORM=$(normalize_ruc_py_rule "${SIFEN_RUC_CONS}")
normalize_exit_code=$?

if [ "$normalize_exit_code" -ne 0 ]; then
    # El error ya fue impreso por la función a stderr
    echo -e "${RED}   Error de normalización de RUC${NC}"
    exit 2
fi

echo "   Normalizado dRUCCons: ${RUC_NORM}"
echo ""

# Endpoints según ambiente
if [ "$SIFEN_ENV" = "test" ]; then
    ENDPOINT_URL="https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl"
else
    ENDPOINT_URL="https://sifen.set.gov.py/de/ws/consultas/consulta-ruc.wsdl"
fi

# Archivos PEM temporales
CERT_PEM="/tmp/sifen_cert.pem"
KEY_PEM="/tmp/sifen_key.pem"

# Archivos de request/response
REQ_XML="/tmp/sifen_ruc_req.xml"
RESP_XML="/tmp/sifen_ruc_resp.xml"
RESP_HDR="/tmp/sifen_ruc_resp.hdr"

# Convertir SIFEN_ENV a uppercase (compatible bash 3.2)
ENV_UPPER="$(printf "%s" "$SIFEN_ENV" | tr '[:lower:]' '[:upper:]')"

echo -e "${BLUE}🧪 Smoke test consultaRUC contra SIFEN ${ENV_UPPER}${NC}"
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

echo -e "${BLUE}📝 Construyendo SOAP request...${NC}"

# Construir SOAP 1.2 request (sin indentación antes del heredoc para evitar espacios)
cat > "$REQ_XML" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope"
                 xmlns:ns0="http://ekuatia.set.gov.py/sifen/xsd">
  <soap12:Header/>
  <soap12:Body>
    <ns0:rEnviConsRUC>
      <ns0:dId>1</ns0:dId>
      <ns0:dRUCCons>${RUC_NORM}</ns0:dRUCCons>
    </ns0:rEnviConsRUC>
  </soap12:Body>
</soap12:Envelope>
XML

# Validación preventiva anti-0160: verificar que el XML empiece con "<"
FIRST_BYTES=$(head -c 5 "$REQ_XML" | cat -v)
if ! echo "$FIRST_BYTES" | grep -q "^<"; then
    echo -e "${RED}❌ Error: El XML request no empieza con '<'${NC}"
    echo "   Primeros bytes: ${FIRST_BYTES}"
    echo "   Esto causará error 0160 (XML Mal Formado)"
    exit 2
fi

# Validar que contiene rEnviConsRUC y dRUCCons
if ! grep -q "rEnviConsRUC" "$REQ_XML"; then
    echo -e "${RED}❌ Error: El XML request no contiene 'rEnviConsRUC'${NC}"
    exit 2
fi

if ! grep -q "dRUCCons" "$REQ_XML"; then
    echo -e "${RED}❌ Error: El XML request no contiene 'dRUCCons'${NC}"
    exit 2
fi

echo -e "   ${GREEN}✅ Request XML creado y validado: ${REQ_XML}${NC}"
echo ""

echo -e "${BLUE}🌐 Enviando request a: ${ENDPOINT_URL}${NC}"
echo ""

# Hacer POST con curl y mTLS
# NOTA: NO usar --fail ni --fail-with-body porque SOAP faults suelen venir con HTTP 400 pero con XML útil
HTTP_CODE=$(curl -sS \
    --cert "$CERT_PEM" \
    --key "$KEY_PEM" \
    --header "Content-Type: application/soap+xml; charset=utf-8; action=\"rEnviConsRUC\"" \
    --header "SOAPAction: rEnviConsRUC" \
    --data-binary @"$REQ_XML" \
    --write-out "%{http_code}" \
    --output "$RESP_XML" \
    --dump-header "$RESP_HDR" \
    --max-time 30 \
    "$ENDPOINT_URL" 2>&1) || true

# Extraer HTTP code del output si curl falló
if ! echo "$HTTP_CODE" | grep -qE '^[0-9]{3}$'; then
    # curl falló, intentar extraer el código del header
    if [ -f "$RESP_HDR" ]; then
        HTTP_CODE=$(grep -i "^HTTP" "$RESP_HDR" | head -1 | grep -oE '[0-9]{3}' | tail -1 || echo "000")
    else
        HTTP_CODE="000"
    fi
fi

# Validar respuesta
if [ "$HTTP_CODE" = "000" ]; then
    echo -e "${RED}❌ Error: No se pudo establecer conexión mTLS${NC}"
    if [ -f "$RESP_XML" ]; then
        echo ""
        echo "Respuesta recibida:"
        cat "$RESP_XML" | head -20
    fi
    exit 1
fi

if [ ! -f "$RESP_XML" ] || [ ! -s "$RESP_XML" ]; then
    echo -e "${RED}❌ Error: No se recibió respuesta XML${NC}"
    echo "   HTTP Code: ${HTTP_CODE}"
    exit 1
fi

# Validar que la respuesta contiene XML válido (tiene tags)
if ! grep -q "<" "$RESP_XML"; then
    echo -e "${RED}❌ Error: La respuesta no parece ser XML válido${NC}"
    echo ""
    echo "HTTP Code: ${HTTP_CODE}"
    echo "Respuesta:"
    cat "$RESP_XML"
    exit 1
fi

# Extraer dCodRes y dMsgRes si existen (robusto, sin depender del prefijo namespace)
# Usar perl para extraer el contenido sin importar el prefijo (ns2:, ns0:, etc.)
if command -v perl >/dev/null 2>&1; then
    DCOD_RES=$(perl -0777 -ne 'print $1 if /<[^:>]*:?dCodRes[^>]*>([^<]+)<\/[^:>]*:?dCodRes>/s' "$RESP_XML" 2>/dev/null | head -n1 || echo "")
    DMSG_RES=$(perl -0777 -ne 'print $1 if /<[^:>]*:?dMsgRes[^>]*>([^<]+)<\/[^:>]*:?dMsgRes>/s' "$RESP_XML" 2>/dev/null | head -n1 || echo "")
else
    # Fallback si perl no está disponible (menos robusto)
    DCOD_RES=$(grep -oE '<[^:>]*:?dCodRes[^>]*>([0-9]+)</[^:>]*:?dCodRes>' "$RESP_XML" | grep -oE '[0-9]+' | head -1 || echo "")
    DMSG_RES=$(grep -oE '<[^:>]*:?dMsgRes[^>]*>([^<]+)</[^:>]*:?dMsgRes>' "$RESP_XML" | sed 's/<[^>]*>//g' | head -1 || echo "")
fi

# Mostrar resumen
echo -e "${GREEN}✅ Respuesta recibida${NC}"
echo ""
echo "================================================================================"
echo "📊 RESUMEN"
echo "================================================================================"
echo "HTTP Code: ${HTTP_CODE}"
RESP_SIZE=$(stat -f%z "$RESP_XML" 2>/dev/null || stat -c%s "$RESP_XML" 2>/dev/null || echo "0")
echo "Tamaño respuesta: ${RESP_SIZE} bytes"
echo ""

if [ -n "$DCOD_RES" ]; then
    echo -e "${GREEN}dCodRes: ${DCOD_RES}${NC}"
else
    echo -e "${YELLOW}dCodRes: (no encontrado)${NC}"
fi

if [ -n "$DMSG_RES" ]; then
    echo -e "${GREEN}dMsgRes: ${DMSG_RES}${NC}"
else
    echo -e "${YELLOW}dMsgRes: (no encontrado)${NC}"
fi

echo ""
echo "Archivos guardados:"
echo "  Request:  ${REQ_XML}"
echo "  Response: ${RESP_XML}"
echo "  Headers:  ${RESP_HDR}"
echo ""

# Criterio de "smoke pasó": si tiene dCodRes y dMsgRes, llegó al servicio
# Esto verifica mTLS + endpoint + parsing, aunque HTTP sea 400

# Modo estricto: si dCodRes=0160 (XML Mal Formado), considerar error a menos que esté permitido
if [ -n "$DCOD_RES" ] && [ "$DCOD_RES" = "0160" ]; then
    if [ "$SIFEN_SMOKE_ALLOW_0160" = "1" ]; then
        echo -e "${YELLOW}⚠️  dCodRes=0160 (XML Mal Formado) detectado, pero SIFEN_SMOKE_ALLOW_0160=1 => modo conectividad${NC}"
        echo -e "${GREEN}✅ Respuesta contiene dCodRes => llegó al servicio SIFEN (conectividad OK)${NC}"
        exit 0
    else
        echo -e "${RED}❌ Error: dCodRes=0160 (XML Mal Formado)${NC}"
        echo "   Esto indica que el request XML no cumple el XSD de SIFEN"
        echo ""
        echo "   Para verificar solo conectividad (ignorar 0160):"
        echo "   export SIFEN_SMOKE_ALLOW_0160=1"
        echo "   bash scripts/sifen_smoke_consulta_ruc.sh"
        echo ""
        echo "   HTTP Code: ${HTTP_CODE}"
        if [ -n "$DMSG_RES" ]; then
            echo "   dMsgRes: ${DMSG_RES}"
        fi
        echo ""
        echo "   Request XML:"
        cat "$REQ_XML" | head -20
        echo ""
        exit 3
    fi
fi

# Casos exitosos
if [ -n "$DCOD_RES" ] && [ -n "$DMSG_RES" ]; then
    echo -e "${GREEN}✅ Respuesta contiene dCodRes y dMsgRes => llegó al servicio SIFEN${NC}"
    echo -e "${GREEN}✅ Smoke test completado exitosamente${NC}"
    exit 0
elif [ -n "$DCOD_RES" ]; then
    # Tiene dCodRes pero no dMsgRes, también considerar éxito
    echo -e "${GREEN}✅ Respuesta contiene dCodRes => llegó al servicio SIFEN${NC}"
    echo -e "${GREEN}✅ Smoke test completado exitosamente${NC}"
    exit 0
elif grep -q "rResEnviConsRUC" "$RESP_XML"; then
    # Tiene rResEnviConsRUC aunque no tenga dCodRes/dMsgRes extraídos
    echo -e "${GREEN}✅ Respuesta contiene rResEnviConsRUC => llegó al servicio SIFEN${NC}"
    echo -e "${GREEN}✅ Smoke test completado exitosamente${NC}"
    exit 0
else
    # No se pudo extraer dCodRes/dMsgRes ni rResEnviConsRUC
    echo -e "${RED}❌ Error: La respuesta no contiene dCodRes/dMsgRes ni rResEnviConsRUC${NC}"
    echo "   Esto puede indicar que no llegó al servicio SIFEN o hubo un error de parsing"
    echo ""
    echo "HTTP Code: ${HTTP_CODE}"
    echo "Respuesta completa:"
    cat "$RESP_XML" | head -50
    echo ""
    exit 1
fi


# ==============================================================================
# EJEMPLOS DE TESTS MANUALES (comentarios de referencia)
# ==============================================================================
#
# Test 1: RUC con guión válido (7 base + 1 DV = 8 total)
#   export SIFEN_RUC_CONS="4554737-8"
#   bash scripts/sifen_smoke_consulta_ruc.sh
#   => RUC_NORM="45547378" => debe avanzar (HTTP 200 + dCodRes/dMsgRes)
#
# Test 2: RUC sin guión válido (8 dígitos)
#   export SIFEN_RUC_CONS="45547378"
#   bash scripts/sifen_smoke_consulta_ruc.sh
#   => RUC_NORM="45547378" => debe avanzar
#
# Test 3: RUC sin guión válido (7 dígitos)
#   export SIFEN_RUC_CONS="4554737"
#   bash scripts/sifen_smoke_consulta_ruc.sh
#   => RUC_NORM="4554737" => debe avanzar
#
# Test 4: RUC con letras (inválido)
#   export SIFEN_RUC_CONS="RUC_VALIDO_SIN_GUION"
#   bash scripts/sifen_smoke_consulta_ruc.sh
#   => debe fallar exit 2 con error claro (no contiene dígitos)
#
# Test 5: RUC con base de 8 dígitos + DV (inválido, total sería 9)
#   export SIFEN_RUC_CONS="80012345-7"
#   bash scripts/sifen_smoke_consulta_ruc.sh
#   => debe fallar exit 2 (base debe ser 6-7 dígitos, no 8)
#
# Test 6: RUC muy corto (inválido)
#   export SIFEN_RUC_CONS="1234"
#   bash scripts/sifen_smoke_consulta_ruc.sh
#   => debe fallar exit 2 (longitud inválida, mínimo 7 dígitos)
#
# Test 7: RUC con guión pero base de 6 dígitos válido
#   export SIFEN_RUC_CONS="455473-7"
#   bash scripts/sifen_smoke_consulta_ruc.sh
#   => RUC_NORM="4554737" (6 base + 1 DV = 7 total) => debe avanzar
#
# Test 8: RUC con DV que tiene letras (inválido)
#   export SIFEN_RUC_CONS="4554737-A"
#   bash scripts/sifen_smoke_consulta_ruc.sh
#   => debe fallar exit 2 (DV debe ser dígito)
#
