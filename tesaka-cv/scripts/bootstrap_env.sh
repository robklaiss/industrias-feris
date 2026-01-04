#!/bin/bash
# Bootstrap script para configurar entorno de desarrollo SIFEN
# Detecta Python 3.11 o 3.12, crea venv, instala dependencias críticas (lxml, xmlsec)
# Soporta macOS (Apple Silicon) con Homebrew

set -e  # Salir si cualquier comando falla

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🔧 Bootstrap de entorno SIFEN"
echo "================================"
echo ""

# 1. Detectar Python 3.12 o 3.11 (preferir 3.12)
PYTHON_CMD=""
for py_cmd in python3.12 python3.11 python3; do
    if command -v "$py_cmd" &> /dev/null; then
        PYTHON_VERSION=$("$py_cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
        MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
        
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 11 ] && [ "$MINOR" -le 12 ]; then
            PYTHON_CMD="$py_cmd"
            echo "✅ Detectado: $py_cmd (versión $PYTHON_VERSION)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ ERROR: No se encontró Python 3.11 o 3.12"
    echo "   Instale Python 3.12 recomendado:"
    echo "   - macOS: brew install python@3.12"
    echo "   - Linux: apt-get install python3.12 python3.12-venv"
    exit 1
fi

# 2. Instalar dependencias de sistema (macOS con Homebrew)
if command -v brew &> /dev/null; then
    echo ""
    echo "🍺 Detectado Homebrew, instalando dependencias de sistema..."
    echo "   (libxml2, libxslt, xmlsec1, pkg-config)"
    brew install libxml2 libxslt xmlsec1 pkg-config || {
        echo "⚠️  Algunas dependencias ya podrían estar instaladas (continuando...)"
    }
    
    # Configurar variables de entorno para compilar lxml y xmlsec contra el MISMO libxml2 de Homebrew
    # Esto evita el mismatch: lxml wheel (libxml2 embebido) vs xmlsec wheel (libxml2 de Homebrew)
    BREW_PREFIX="$(brew --prefix)"
    export PATH="$BREW_PREFIX/opt/libxml2/bin:$BREW_PREFIX/opt/libxslt/bin:$BREW_PREFIX/opt/xmlsec1/bin:$PATH"
    export PKG_CONFIG_PATH="$BREW_PREFIX/opt/libxml2/lib/pkgconfig:$BREW_PREFIX/opt/libxslt/lib/pkgconfig:$BREW_PREFIX/opt/xmlsec1/lib/pkgconfig:$BREW_PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
    export LDFLAGS="-L$BREW_PREFIX/opt/libxml2/lib -L$BREW_PREFIX/opt/libxslt/lib -L$BREW_PREFIX/opt/xmlsec1/lib ${LDFLAGS:-}"
    export CPPFLAGS="-I$BREW_PREFIX/opt/libxml2/include -I$BREW_PREFIX/opt/libxslt/include -I$BREW_PREFIX/opt/xmlsec1/include ${CPPFLAGS:-}"
    
    echo "✅ Variables de entorno configuradas para compilación consistente de lxml y xmlsec"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo ""
    echo "❌ ERROR: En macOS se requiere Homebrew para instalar xmlsec1/libxml2/libxslt"
    echo ""
    echo "   Instale Homebrew primero:"
    echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo ""
    echo "   Luego ejecute este script nuevamente."
    exit 1
fi

# 3. Crear venv en .venv
VENV_DIR="$PROJECT_ROOT/.venv"
if [ -d "$VENV_DIR" ]; then
    echo ""
    echo "⚠️  .venv ya existe, recreando..."
    rm -rf "$VENV_DIR"
fi

echo ""
echo "📦 Creando venv en .venv..."
"$PYTHON_CMD" -m venv "$VENV_DIR"

# 4. Activar venv
echo "🔌 Activando venv..."
source "$VENV_DIR/bin/activate"

# 5. Actualizar pip
echo ""
echo "⬆️  Actualizando pip..."
pip install --upgrade pip setuptools wheel

# 6. Instalar requirements base
REQUIREMENTS_FILE="$PROJECT_ROOT/app/requirements.txt"
if [ -f "$REQUIREMENTS_FILE" ]; then
    echo ""
    echo "📚 Instalando dependencias desde $REQUIREMENTS_FILE..."
    
    # PUNTO CLAVE: Forzar compilación desde fuente de lxml y xmlsec para evitar mismatch de libxml2
    # En macOS ARM, los wheels tienen libxml2 embebido (lxml) vs libxml2 de Homebrew (xmlsec)
    # Compilando ambos desde fuente contra el mismo libxml2 de Homebrew garantiza consistencia
    if command -v brew &> /dev/null; then
        echo "   🔨 Forzando compilación desde fuente de lxml y xmlsec (--no-binary)"
        echo "   Esto asegura que ambos usen el mismo libxml2 de Homebrew"
        if ! pip install --no-binary=lxml,xmlsec -r "$REQUIREMENTS_FILE"; then
            echo ""
            echo "❌ ERROR: Falló la instalación de dependencias (compilación desde fuente)"
            echo ""
            if [[ "$OSTYPE" == "darwin"* ]]; then
                echo "   En macOS, asegúrese de tener:"
                echo "   1. Xcode Command Line Tools: xcode-select --install"
                echo "   2. Homebrew instalado: brew --version"
                echo "   3. Dependencias de sistema: brew install libxml2 libxslt xmlsec1 pkg-config"
                echo ""
                echo "   Luego ejecute este script nuevamente."
            else
                echo "   En Linux, instale las dependencias de sistema:"
                echo "   - Debian/Ubuntu: apt-get install libxml2-dev libxslt1-dev libxmlsec1-dev pkg-config"
                echo "   - RedHat/CentOS: yum install libxml2-devel libxslt-devel xmlsec1-devel pkgconfig"
            fi
            exit 1
        fi
    else
        # Sin Homebrew, usar instalación normal (puede usar wheels)
        if ! pip install -r "$REQUIREMENTS_FILE"; then
            echo ""
            echo "❌ ERROR: Falló la instalación de dependencias"
            if [[ "$OSTYPE" == "darwin"* ]]; then
                echo "   En macOS, se recomienda usar Homebrew para evitar problemas de mismatch."
            fi
            exit 1
        fi
    fi
else
    echo "⚠️  No se encontró $REQUIREMENTS_FILE, instalando dependencias mínimas..."
    if command -v brew &> /dev/null; then
        if ! pip install --no-binary=lxml,xmlsec lxml xmlsec cryptography; then
            echo ""
            echo "❌ ERROR: Falló la instalación de dependencias mínimas"
            if [[ "$OSTYPE" == "darwin"* ]]; then
                echo "   En macOS, asegúrese de tener Homebrew y las dependencias instaladas."
            fi
            exit 1
        fi
    else
        if ! pip install lxml xmlsec cryptography; then
            echo ""
            echo "❌ ERROR: Falló la instalación de dependencias mínimas"
            exit 1
        fi
    fi
fi

# 7. Smoke test final (verificar que NO hay mismatch de libxml2)
echo ""
echo "🧪 Ejecutando smoke test final (verificando consistencia de libxml2)..."
python - <<'PY'
import lxml
from lxml import etree
import xmlsec

# Verificar que ambos pueden importarse sin error de mismatch
try:
    libxml_version = lxml.etree.LIBXML_VERSION
    xmlsec_version = xmlsec.__version__
    print(f"✅ OK lxml+xmlsec {libxml_version} {xmlsec_version}")
except Exception as e:
    if "version mismatch" in str(e).lower() or "library version mismatch" in str(e).lower():
        print(f"❌ ERROR: Mismatch de versión de libxml2 entre lxml y xmlsec")
        print(f"   {e}")
        print("")
        print("   Esto indica que lxml y xmlsec fueron compilados contra diferentes versiones de libxml2.")
        print("   En macOS, ejecute el bootstrap nuevamente para forzar compilación desde fuente.")
        exit(1)
    else:
        raise
PY

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ ERROR: Smoke test falló"
    echo ""
    echo "   Verifique que lxml y xmlsec estén instalados correctamente:"
    echo "   pip list | grep -E 'lxml|xmlsec'"
    exit 1
fi

echo ""
echo "✅ Bootstrap completado exitosamente"
echo ""
echo "Para activar el entorno en el futuro:"
echo "  source .venv/bin/activate"
echo ""
echo "Para desactivar:"
echo "  deactivate"

