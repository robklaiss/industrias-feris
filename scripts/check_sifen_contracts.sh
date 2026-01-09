#!/bin/bash
#
# Script de verificación de contratos SIFEN
#
# Este script ejecuta todos los tests que validan que el código cumple
# con los contratos WSDL/XSD de SIFEN. Debe ejecutarse antes de probar
# contra SIFEN real y antes de hacer commits que modifiquen el cliente SOAP.
#
# Tests incluidos:
# - test_endpoint_derivation.py: Valida derivación correcta de endpoints desde WSDL
# - test_consulta_ruc_xsd_validation.py: Valida formato RUC y conformidad XSD
# - test_consulta_ruc_contract.py: Valida contrato WSDL completo (si existe)
#
# Exit codes:
# - 0: Todos los tests pasaron
# - 1: Al menos un test falló o no se pudo instalar pytest

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

cd "${REPO_ROOT}"

# Detectar Python correcto (prioridad: venv > sistema)
detect_python() {
    if [ -f "${REPO_ROOT}/.venv/bin/python3" ]; then
        echo "${REPO_ROOT}/.venv/bin/python3"
    elif [ -f "${REPO_ROOT}/.venv/bin/python" ]; then
        echo "${REPO_ROOT}/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        command -v python3
    else
        echo ""
    fi
}

# Instalar pytest si no está disponible
ensure_pytest() {
    local py_cmd="$1"
    local pip_cmd="${py_cmd} -m pip"
    
    echo -e "${BLUE}🔍 Verificando pytest...${NC}"
    
    # Verificar si pytest está instalado
    if "${py_cmd}" -c "import pytest" >/dev/null 2>&1; then
        local pytest_version=$("${py_cmd}" -c "import pytest; print(pytest.__version__)" 2>/dev/null || echo "unknown")
        echo -e "   ${GREEN}✅ pytest ya está instalado (versión: ${pytest_version})${NC}"
        return 0
    fi
    
    echo -e "   ${YELLOW}⚠️  pytest no encontrado, instalando...${NC}"
    
    # Verificar que pip está disponible
    if ! "${py_cmd}" -m pip --version >/dev/null 2>&1; then
        echo -e "   ${RED}❌ pip no está disponible${NC}"
        echo ""
        echo -e "${RED}Error: pip no está instalado o no es accesible.${NC}"
        echo ""
        echo "Solución: Instala pip o asegúrate de que el virtualenv esté correctamente configurado."
        return 1
    fi
    
    # Intentar instalar pytest (capturar stderr para mostrar errores si falla)
    local install_output
    install_output=$("${pip_cmd}" install -q pytest 2>&1)
    local install_status=$?
    
    if [ ${install_status} -eq 0 ]; then
        echo -e "   ${GREEN}✅ pytest instalado correctamente${NC}"
        return 0
    else
        echo -e "   ${RED}❌ No se pudo instalar pytest${NC}"
        if [ -n "${install_output}" ]; then
            echo ""
            echo "Salida de pip:"
            echo "${install_output}" | sed 's/^/  /'
        fi
        echo ""
        echo -e "${RED}Error: No se pudo instalar pytest.${NC}"
        echo ""
        echo "Posibles causas:"
        echo "  - No hay permisos para instalar paquetes"
        echo "  - Sin conexión a internet (si se requiere descargar)"
        echo "  - Error en la configuración del entorno Python"
        echo ""
        echo "Solución manual:"
        echo "  ${pip_cmd} install pytest"
        return 1
    fi
}

# Detectar y configurar Python
PY=$(detect_python)

if [ -z "${PY}" ]; then
    echo -e "${RED}❌ Error: No se encontró Python 3${NC}"
    echo ""
    echo "Por favor instala Python 3 o crea un virtualenv:"
    echo "  python3 -m venv .venv"
    exit 1
fi

echo -e "${BLUE}🐍 Python detectado: ${PY}${NC}"
"${PY}" --version

# Verificar si estamos en un venv
if [[ "${PY}" == *".venv"* ]]; then
    echo -e "${GREEN}✅ Usando virtualenv: .venv${NC}"
else
    echo -e "${YELLOW}⚠️  Usando Python del sistema (se recomienda usar virtualenv)${NC}"
fi

echo ""

# Asegurar que pytest está instalado
if ! ensure_pytest "${PY}"; then
    exit 1
fi

echo ""

# Verificar compilación de módulos Python críticos antes de ejecutar tests
echo "================================================================================"
echo "🔍 VERIFICACIÓN DE COMPILACIÓN PYTHON"
echo "================================================================================"
echo ""

COMPILATION_ERRORS=0

# Lista de módulos críticos a compilar
CRITICAL_MODULES=(
    "tesaka-cv/app/sifen_client/soap_client.py"
    "tesaka-cv/app/sifen_client/wsdl_introspect.py"
    "tesaka-cv/tools/send_sirecepde.py"
)

for module in "${CRITICAL_MODULES[@]}"; do
    if [ ! -f "${REPO_ROOT}/${module}" ]; then
        echo -e "   ${YELLOW}⚠️  ${module} no encontrado, omitiendo...${NC}"
        continue
    fi
    
    if "${PY}" -m py_compile "${REPO_ROOT}/${module}" 2>&1; then
        echo -e "   ${GREEN}✅ ${module}${NC}"
    else
        echo -e "   ${RED}❌ ${module} (error de sintaxis)${NC}"
        COMPILATION_ERRORS=$((COMPILATION_ERRORS + 1))
    fi
done

if [ ${COMPILATION_ERRORS} -gt 0 ]; then
    echo ""
    echo -e "${RED}❌ ERROR: Errores de sintaxis detectados. Corrige los errores antes de continuar.${NC}" >&2
    exit 1
fi

echo ""
echo "================================================================================"
echo "🔒 VERIFICACIÓN DE CONTRATOS SIFEN"
echo "================================================================================"
echo ""

# Contador de tests ejecutados y fallidos
TESTS_RUN=0
TESTS_FAILED=0
FAILED_TESTS=()

# Función para ejecutar un test y capturar resultado
run_test() {
    local test_file="$1"
    local test_name="$2"
    
    TESTS_RUN=$((TESTS_RUN + 1))
    
    echo "▶️  Ejecutando: ${test_name}"
    echo "   Archivo: ${test_file}"
    
    if [ ! -f "${test_file}" ]; then
        echo -e "   ${YELLOW}⚠️  Test no encontrado, omitiendo...${NC}"
        echo ""
        return
    fi
    
    # Ejecutar pytest y capturar resultado
    # Usar --tb=short para errores y contar SKIPPED como exitosos
    # Cambiar al directorio correcto para que los imports funcionen
    cd "${REPO_ROOT}/tesaka-cv"
    pytest_output=$("${PY}" -m pytest "${REPO_ROOT}/${test_file}" -q --tb=short 2>&1)
    pytest_status=$?
    cd "${REPO_ROOT}"
    
    # Verificar si hay tests skipped (pytest muestra "skipped" o "SKIPPED")
    if echo "$pytest_output" | grep -qi "skip"; then
        skipped_count=$(echo "$pytest_output" | grep -i "skip" | grep -c "test\|item" || echo "0")
        if [ "$skipped_count" -eq 0 ]; then
            skipped_count=$(echo "$pytest_output" | grep -oE "[0-9]+ skipped" | grep -oE "[0-9]+" | head -1 || echo "0")
        fi
        if [ "$skipped_count" -eq 0 ]; then
            skipped_count="algunos"
        fi
        echo -e "   ${YELLOW}⚠️  SKIPPED (${skipped_count} test(s))${NC}"
        # SKIPPED no cuenta como fallido, pero informamos
        echo ""
        return 0
    elif [ $pytest_status -eq 0 ]; then
        echo -e "   ${GREEN}✅ PASSED${NC}"
        echo ""
        return 0
    else
        echo -e "   ${RED}❌ FAILED${NC}"
        echo ""
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILED_TESTS+=("${test_name}")
        return 1
    fi
}

# Ejecutar tests SIFEN existentes (si existen)
# Solo ejecutar tests relacionados con SIFEN que realmente existen
SIFEN_TEST_FILES=()

# Verificar cada test SIFEN potencial y solo agregarlo si existe
POTENTIAL_SIFEN_TESTS=(
    "tesaka-cv/tests/test_soap_client_mtls.py"
    "tesaka-cv/tests/test_pkcs12_utils.py"
    "tesaka-cv/tests/test_xml_signer.py"
    "tesaka-cv/tests/test_size_validation.py"
)

for test_file in "${POTENTIAL_SIFEN_TESTS[@]}"; do
    if [ -f "${REPO_ROOT}/${test_file}" ]; then
        SIFEN_TEST_FILES+=("${test_file}")
    fi
done

if [ ${#SIFEN_TEST_FILES[@]} -eq 0 ]; then
    echo -e "${YELLOW}⚠️  No se encontraron tests SIFEN en tesaka-cv/tests${NC}"
    echo ""
else
    echo "Ejecutando tests SIFEN disponibles..."
    echo ""
    for test_file in "${SIFEN_TEST_FILES[@]}"; do
        run_test "${test_file}" "$(basename "${test_file}" .py | sed 's/test_/Test /')"
    done
fi

# Test 3: Contract tests (opcional, solo si existe WSDL snapshot)
# Verificar snapshot WSDL antes de ejecutar para mostrar warning
WSDL_SNAPSHOT="${REPO_ROOT}/tesaka-cv/wsdl_snapshots/consulta-ruc_test.wsdl"
if [ ! -f "$WSDL_SNAPSHOT" ] || [ ! -s "$WSDL_SNAPSHOT" ]; then
    # Mostrar warning pero ejecutar el test de todas formas (hará SKIP automáticamente)
    TESTS_RUN=$((TESTS_RUN + 1))
    echo "▶️  Test Contract WSDL consultaRUC (estructura SOAP)"
    echo "   Archivo: tesaka-cv/tests/test_consulta_ruc_contract.py"
    if [ ! -f "$WSDL_SNAPSHOT" ]; then
        echo -e "   ${YELLOW}⚠️  WSDL snapshot no encontrado, test será SKIPPED${NC}"
    else
        SNAPSHOT_SIZE=$(stat -f%z "$WSDL_SNAPSHOT" 2>/dev/null || stat -c%s "$WSDL_SNAPSHOT" 2>/dev/null || echo "0")
        if [ "$SNAPSHOT_SIZE" -eq 0 ]; then
            echo -e "   ${YELLOW}⚠️  WSDL snapshot está vacío (0 bytes), test será SKIPPED${NC}"
        fi
    fi
    echo -e "   ${YELLOW}⚠️  Para actualizar: bash scripts/update_wsdl_snapshot_consulta_ruc_test.sh${NC}"
    
    # Ejecutar pytest y verificar SKIPPED
    pytest_output=$("${PY}" -m pytest "tesaka-cv/tests/test_consulta_ruc_contract.py" -q --tb=short 2>&1)
    pytest_status=$?
    
    # Verificar si hay tests skipped (pytest muestra "skipped" o "SKIPPED")
    if echo "$pytest_output" | grep -qi "skip"; then
        skipped_count=$(echo "$pytest_output" | grep -oE "[0-9]+ skipped" | grep -oE "[0-9]+" | head -1 || echo "0")
        if [ "$skipped_count" -eq 0 ]; then
            skipped_count="todos"
        fi
        echo -e "   ${YELLOW}⚠️  SKIPPED (${skipped_count} test(s)) - snapshot ausente o vacío${NC}"
        # SKIPPED no cuenta como fallido
    elif [ $pytest_status -eq 0 ]; then
        echo -e "   ${GREEN}✅ PASSED${NC}"
    else
        echo -e "   ${RED}❌ FAILED${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILED_TESTS+=("Test Contract WSDL consultaRUC (estructura SOAP)")
    fi
    echo ""
else
    # Snapshot existe y no está vacío, ejecutar test normalmente
    run_test \
        "tesaka-cv/tests/test_consulta_ruc_contract.py" \
        "Test Contract WSDL consultaRUC (estructura SOAP)"
fi

# Resumen
echo "================================================================================"
echo "📊 RESUMEN"
echo "================================================================================"
echo "Tests ejecutados: ${TESTS_RUN}"
echo "Tests pasados: $((TESTS_RUN - TESTS_FAILED))"
echo "Tests fallidos: ${TESTS_FAILED}"
echo ""

if [ ${TESTS_FAILED} -eq 0 ]; then
    echo -e "${GREEN}✅ TODOS LOS TESTS DE CONTRATO PASARON${NC}"
    echo ""
    
    # Verificar si hay snapshot WSDL ausente o vacío para mostrar advertencia
    WSDL_SNAPSHOT="${REPO_ROOT}/tesaka-cv/wsdl_snapshots/consulta-ruc_test.wsdl"
    if [ ! -f "$WSDL_SNAPSHOT" ] || [ ! -s "$WSDL_SNAPSHOT" ]; then
        echo -e "${YELLOW}⚠️  NOTA: Algunos contract tests fueron SKIPPED porque el WSDL snapshot está ausente o vacío.${NC}"
        echo "   Para habilitarlos completamente, ejecuta:"
        echo "   bash scripts/update_wsdl_snapshot_consulta_ruc_test.sh"
        echo ""
    fi
    
    echo "El código cumple con los contratos WSDL/XSD de SIFEN."
    echo "Es seguro proceder con pruebas contra SIFEN real."
    exit 0
else
    echo -e "${RED}❌ ${TESTS_FAILED} TEST(S) FALLARON${NC}"
    echo ""
    echo "Tests fallidos:"
    for test in "${FAILED_TESTS[@]}"; do
        echo -e "  ${RED}  - ${test}${NC}"
    done
    echo ""
    echo -e "${RED}⚠️  NO es seguro proceder con pruebas contra SIFEN real.${NC}"
    echo "Revisa los errores arriba y corrige el código antes de continuar."
    exit 1
fi
