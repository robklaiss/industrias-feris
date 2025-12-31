#!/bin/bash
set -euo pipefail

# Script para ejecutar el smoke test de SIFEN
# Carga variables desde .env si existe y ejecuta el main

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Cargar variables desde .env si existe
if [ -f .env ]; then
    echo "Cargando variables desde .env..."
    # Exportar variables sin imprimirlas (por seguridad)
    set -a
    source .env
    set +a
fi

# Compilar y ejecutar
echo "Compilando proyecto..."
mvn -q -DskipTests clean package

echo "Ejecutando smoke test..."
mvn -q exec:java

