#!/usr/bin/env bash
set -euo pipefail

# Wrapper universal para SIFEN:
# 1) Ejecuta comando de generación (GEN_CMD) -> produce XML sin firma
# 2) Ejecuta comando de firma (SIGN_CMD) -> produce XML firmado
# 3) Recalcula dCarQR sin tocar firma (tools/make_valid_de.py) -> produce XML final

# Función para cargar archivo .env de forma segura
load_env_file() {
  local env_file="$1"
  if [[ -f "$env_file" ]]; then
    echo "Cargando variables desde: $env_file"
    while IFS='=' read -r key value; do
      # Ignorar líneas vacías y comentarios
      [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
      
      # Remover espacios alrededor
      key=$(echo "$key" | xargs)
      value=$(echo "$value" | xargs)
      
      # Exportar variable si no está ya seteada
      if [[ -z "${!key:-}" ]]; then
        export "$key"="$value"
      fi
    done < "$env_file"
  fi
}

# Función para resolver secretos según ambiente
resolve_secrets() {
  local env="${1:-test}"
  
  # Si ya están seteadas directamente, usarlas (tienen prioridad)
  if [[ -n "${SIFEN_IDCSC:-}" && -n "${SIFEN_CSC:-}" ]]; then
    echo "Usando credenciales directas (override)"
    export SIFEN_IDCSC SIFEN_CSC
    return
  fi
  
  # Según ambiente
  case "$env" in
    test)
      export SIFEN_IDCSC="${SIFEN_IDCSC_TEST:-}"
      export SIFEN_CSC="${SIFEN_CSC_TEST:-}"
      ;;
    prod)
      export SIFEN_IDCSC="${SIFEN_IDCSC_PROD:-}"
      export SIFEN_CSC="${SIFEN_CSC_PROD:-}"
      ;;
    *)
      echo "Error: Ambiente '$env' no válido. Usar 'test' o 'prod'"
      exit 1
      ;;
  esac
  
  # Verificar que se cargaron
  if [[ -z "${SIFEN_IDCSC:-}" || -z "${SIFEN_CSC:-}" ]]; then
    echo "❌ Error: Faltan variables para el ambiente '$env'"
    echo ""
    echo "Soluciones:"
    echo "1) Crear archivo .env con:"
    echo "   SIFEN_ENV=$env"
    echo "   SIFEN_IDCSC_${env^^}=0001"
    echo "   SIFEN_CSC_${env^^}=TU_CSC"
    echo ""
    echo "2) O exportar directamente:"
    echo "   export SIFEN_IDCSC=0001"
    echo "   export SIFEN_CSC=TU_CSC"
    exit 1
  fi
}

usage() {
  cat <<'TXT'
Uso:
  # Ambiente test (default)
  tools/make_de_wrapper.sh \
    --gen  '.venv/bin/python tools/generar_prevalidador.py' \
    --sign 'echo "YA FIRMA EL GENERADOR"' \
    --out  '~/Desktop/de_final.xml'

  # Ambiente producción
  tools/make_de_wrapper.sh \
    --env prod \
    --gen  '.venv/bin/python tools/generar_prevalidador.py' \
    --sign 'echo "YA FIRMA EL GENERADOR"' \
    --out  '~/Desktop/de_final.xml'

  # Con archivo .env personalizado
  tools/make_de_wrapper.sh \
    --env-file '/path/al/.env' \
    --env test \
    --gen  '.venv/bin/python tools/generar_prevalidador.py' \
    --sign 'echo "YA FIRMA EL GENERADOR"' \
    --out  '~/Desktop/de_final.xml'

Variables de entorno:
  SIFEN_ENV=test|prod (default: test)
  SIFEN_IDCSC / SIFEN_CSC (override directo)
  O usar por ambiente:
    SIFEN_IDCSC_TEST / SIFEN_CSC_TEST
    SIFEN_IDCSC_PROD / SIFEN_CSC_PROD

Opciones:
- --env-file PATH  (archivo .env, default: .env o .env.sifen)
- --env test|prod   (ambiente, default: test)
- --keep-tmp        (no borra temporales)

TXT
}

KEEP_TMP=0
OUT=""
GEN_CMD=""
SIGN_CMD=""
ENV_FILE=""
ENV=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --gen) GEN_CMD="$2"; shift 2;;
    --sign) SIGN_CMD="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --env-file) ENV_FILE="$2"; shift 2;;
    --env) ENV="$2"; shift 2;;
    --keep-tmp) KEEP_TMP=1; shift 1;;
    -h|--help) usage; exit 0;;
    *) echo "Arg desconocido: $1"; usage; exit 2;;
  esac
done

if [[ -z "$GEN_CMD" || -z "$SIGN_CMD" || -z "$OUT" ]]; then
  echo "Faltan argumentos."
  usage
  exit 2
fi

# Determinar ambiente
ENV="${ENV:-${SIFEN_ENV:-test}}"

# Cargar archivo .env
if [[ -z "$ENV_FILE" ]]; then
  # Buscar .env o .env.sifen en la raíz del repo
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if [[ -f "$REPO_ROOT/.env" ]]; then
    ENV_FILE="$REPO_ROOT/.env"
  elif [[ -f "$REPO_ROOT/.env.sifen" ]]; then
    ENV_FILE="$REPO_ROOT/.env.sifen"
  fi
fi

load_env_file "$ENV_FILE"

# Resolver secretos
resolve_secrets "$ENV"

echo "🔧 Ambiente: $ENV"
echo "🔑 IdCSC: $SIFEN_IDCSC"
echo "🔒 CSC: *** (oculto)"

TMP_XML="/tmp/sifen_de.xml"
TMP_SIGNED="/tmp/sifen_de_signed.xml"
OUT_EXPANDED="$(python3 - <<PY
import os
from pathlib import Path
print(Path(os.path.expanduser(r'''$OUT''')).resolve())
PY
)"

echo ""
echo "== 1) Generar XML =="
echo "$GEN_CMD"
eval "$GEN_CMD"

# Heurística: si el comando no escribe a TMP_XML, intentamos detectarlo
if [[ ! -f "$TMP_XML" ]]; then
  # Para el generador prevalidador, busca en ~/Desktop
  if [[ "$GEN_CMD" == *"generar_prevalidador"* ]]; then
    CANDIDATE="$HOME/Desktop/prevalidador_rde_signed.xml"
    if [[ -f "$CANDIDATE" ]]; then
      cp "$CANDIDATE" "$TMP_SIGNED"
      echo "XML firmado detectado: $CANDIDATE"
    fi
  else
    # busca el xml más reciente en /tmp
    CANDIDATE="$(ls -t /tmp/*.xml 2>/dev/null | head -n 1 || true)"
    if [[ -n "$CANDIDATE" ]]; then
      TMP_XML="$CANDIDATE"
    fi
  fi
fi

# Si ya tenemos el firmado (caso prevalidador), saltamos firma
if [[ -f "$TMP_SIGNED" ]]; then
  echo "XML ya está firmado (generador prevalidador)"
else
  [[ -f "$TMP_XML" ]] || { echo "No encuentro XML generado. Ajustá tu --gen para escribir /tmp/sifen_de.xml"; exit 1; }
  echo "XML generado: $TMP_XML"

  echo ""
  echo "== 2) Firmar XML =="
  echo "$SIGN_CMD"
  eval "$SIGN_CMD"

  if [[ ! -f "$TMP_SIGNED" ]]; then
    CANDIDATE="$(ls -t /tmp/*signed*.xml /tmp/*firm*.xml 2>/dev/null | head -n 1 || true)"
    if [[ -n "$CANDIDATE" ]]; then
      TMP_SIGNED="$CANDIDATE"
    fi
  fi
  [[ -f "$TMP_SIGNED" ]] || { echo "No encuentro XML firmado. Ajustá tu --sign para escribir /tmp/sifen_de_signed.xml"; exit 1; }
  echo "XML firmado: $TMP_SIGNED"
fi

echo ""
echo "== 3) Recalcular QR (sin tocar firma) =="
python3 tools/make_valid_de.py --in "$TMP_SIGNED" --out "$OUT_EXPANDED" --env "$ENV"

echo ""
echo "✅ LISTO: $OUT_EXPANDED"

if [[ "$KEEP_TMP" -eq 0 ]]; then
  # No borramos si los nombres son distintos de los default
  [[ "$TMP_XML" == "/tmp/sifen_de.xml" ]] && rm -f "$TMP_XML" || true
  [[ "$TMP_SIGNED" == "/tmp/sifen_de_signed.xml" ]] && rm -f "$TMP_SIGNED" || true
fi
