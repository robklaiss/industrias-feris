#!/bin/bash
#
# Bootstrap script para entorno de desarrollo
# Crea venv, instala dependencias y corre prechecks
#
# Uso: bash scripts/bootstrap_dev.sh
#
set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TESAKA_CV_DIR="${REPO_ROOT}/tesaka-cv"
VENV_DIR="${REPO_ROOT}/.venv"

echo "=== Bootstrap Dev Environment ==="
echo "Repo root: ${REPO_ROOT}"
echo "Tesaka CV dir: ${TESAKA_CV_DIR}"

# Crear venv si no existe
if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "${VENV_DIR}"
else
    echo "Virtual environment already exists"
fi

# Activar venv
echo "Activating virtual environment..."
source "${VENV_DIR}/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
python -m pip install --upgrade pip setuptools wheel

# Instalar dependencias
echo "Installing dependencies from tesaka-cv/requirements.txt..."
pip install -r "${TESAKA_CV_DIR}/requirements.txt"

# Mostrar versiones
echo ""
echo "=== Environment Info ==="
python --version
pip --version
echo ""

# Precheck: compilar módulos SIFEN clave
echo "=== Precheck: Compiling SIFEN modules ==="
cd "${TESAKA_CV_DIR}"
python -m py_compile app/sifen/config.py || { echo "ERROR: Failed to compile config.py"; exit 1; }
python -m py_compile app/sifen/ruc.py || { echo "ERROR: Failed to compile ruc.py"; exit 1; }
python -m py_compile app/sifen/consulta_ruc.py || { echo "ERROR: Failed to compile consulta_ruc.py"; exit 1; }
python -m py_compile app/sifen/send_de.py || { echo "ERROR: Failed to compile send_de.py"; exit 1; }
echo "✓ All SIFEN modules compiled successfully"

# Precheck: correr tests básicos
echo ""
echo "=== Precheck: Running SIFEN normalize tests ==="
python -m pytest -q -k "sifen_ruc_normalize" -vv || { echo "ERROR: Tests failed"; exit 1; }
echo "✓ Tests passed"

echo ""
echo "=== Bootstrap completed successfully ==="
exit 0
