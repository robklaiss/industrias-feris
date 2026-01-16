#!/usr/bin/env bash
# Source-only helper to configure SIFEN environment variables on macOS.
# Usage:  source ./scripts/sifen_env.sh

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "❌ Este script debe ejecutarse con 'source scripts/sifen_env.sh'"
  exit 1
fi

_sifen_die() { echo "❌ $*" >&2; return 1; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || _sifen_die "No se pudo acceder al repo root"

export PYTHONPATH="$REPO_ROOT"
export SIFEN_ARTIFACTS_DIR="$REPO_ROOT/artifacts"
mkdir -p "$SIFEN_ARTIFACTS_DIR"

# Load environment variables from .env.sifen_test if it exists
if [[ -f "$REPO_ROOT/.env.sifen_test" ]]; then
  set -a
  source "$REPO_ROOT/.env.sifen_test"
  set +a
fi

# Resolver P12: si alguna variable ya está definida, respetarla; sino usar default.
DEFAULT_P12="$HOME/.sifen/certs/F1T_65478.p12"
_p12_path="${SIFEN_SIGN_P12_PATH:-${SIFEN_P12_PATH:-${SIFEN_CERT_PATH:-$DEFAULT_P12}}}"

export SIFEN_P12_PATH="$_p12_path"
export SIFEN_SIGN_P12_PATH="$_p12_path"
export SIFEN_CERT_PATH="$_p12_path"

if [[ ! -f "$SIFEN_P12_PATH" ]]; then
  _sifen_die "No existe el certificado P12 en '$SIFEN_P12_PATH'"
fi

SERVICE="sifen_sign_p12_password"
ACCOUNT="${USER:-sifen_user}"
MAX_ATTEMPTS=2

_validate_p12_password() {
  openssl pkcs12 -in "$SIFEN_SIGN_P12_PATH" -nokeys -passin env:SIFEN_SIGN_P12_PASSWORD >/dev/null 2>&1
}

_maybe_load_from_keychain() {
  security find-generic-password -s "$SERVICE" -a "$ACCOUNT" -w 2>/dev/null
}

if [[ -n "${SIFEN_SIGN_P12_PASSWORD:-}" ]]; then
  :
else
  keychain_pwd="$(_maybe_load_from_keychain || true)"
  if [[ -n "$keychain_pwd" ]]; then
    export SIFEN_SIGN_P12_PASSWORD="$keychain_pwd"
  fi
fi

attempt=0
while true; do
  if [[ -z "${SIFEN_SIGN_P12_PASSWORD:-}" ]]; then
    read -s -p "P12 password: " SIFEN_SIGN_P12_PASSWORD
    echo
    export SIFEN_SIGN_P12_PASSWORD
  fi
  attempt=$((attempt + 1))
  if _validate_p12_password; then
    break
  fi
  echo "⚠️  Password incorrecta (intento $attempt/$MAX_ATTEMPTS)."
  unset SIFEN_SIGN_P12_PASSWORD
  if (( attempt >= MAX_ATTEMPTS )); then
    _sifen_die "No se pudo validar el password del P12."
  fi
done

if [[ "${SIFEN_KEYCHAIN_SAVE:-0}" == "1" ]]; then
  security add-generic-password -U -s "$SERVICE" -a "$ACCOUNT" -w "$SIFEN_SIGN_P12_PASSWORD" >/dev/null 2>&1 || true
fi

echo "[OK] root=$REPO_ROOT"
echo "[OK] P12=$(basename "$SIFEN_P12_PATH")"
echo "[OK] password=SET (len=${#SIFEN_SIGN_P12_PASSWORD})"
echo "[OK] artifacts=$SIFEN_ARTIFACTS_DIR"
