# Guía de Desarrollo - SIFEN Integration

## Requisitos Previos

- **Python 3.11 o 3.12** (recomendado 3.12)
  - Python 3.14+ no tiene wheels para lxml/xmlsec y causará errores
  - Verificar versión: `python3 --version`

## Envío de Documentos - Modo Automático

El script `tools/send_sirecepde.py` ahora soporta selección automática de XMLs:

```bash
# Enviar el XML base más reciente (sin firmar)
python -m tools.send_sirecepde --env test --xml latest

# Enviar a producción con el XML más reciente
python -m tools.send_sirecepde --env prod --xml latest --dump-http

# Reenviar el XML firmado más reciente
python -m tools.send_sirecepde --env prod --xml signed_latest
```

Valores especiales para `--xml`:
- `latest` o `newest`: Selecciona automáticamente el XML base más reciente
- `signed_latest` o `latest_signed`: Selecciona el XML firmado más reciente

Ver `docs/DEV_USAGE.md` para más detalles.

## Setup Rápido

### Opción 1: Script Automático (Recomendado)

```bash
cd tesaka-cv
./scripts/bootstrap_env.sh
```

Este script:
- Detecta Python 3.11 o 3.12
- Crea venv en `.venv`
- Instala todas las dependencias (incluyendo lxml y xmlsec)
- Ejecuta smoke test para verificar que todo funciona

### Opción 2: Manual

```bash
cd tesaka-cv

# 1. Crear venv con Python 3.12 (o 3.11)
python3.12 -m venv .venv

# 2. Activar venv
source .venv/bin/activate

# 3. Actualizar pip
pip install --upgrade pip setuptools wheel

# 4. Instalar dependencias
pip install -r app/requirements.txt

# 5. Verificar instalación crítica
python -c "import lxml, xmlsec; from lxml import etree; print('OK lxml+xmlsec')"
```

## Verificación de Dependencias Críticas

**IMPORTANTE**: Sin `lxml` y `xmlsec`, el sistema **NO enviará documentos** a SIFEN (bloqueo automático).

Para verificar:

```bash
source .venv/bin/activate
python -c "import lxml, xmlsec; from lxml import etree; print('✅ Dependencias OK')"
```

Si falta alguna:
```bash
pip install lxml python-xmlsec
```

## Ejecutar Servidor Web

```bash
cd tesaka-cv
source .venv/bin/activate

# Configurar variables de entorno (crear .env si no existe)
export SIFEN_EMISOR_RUC="4554737-8"
export SIFEN_ENV="test"
export SIFEN_MTLS_P12_PATH="/path/to/cert.p12"
export SIFEN_MTLS_P12_PASSWORD="password"

# Ejecutar servidor
./web/run.sh
# O manualmente:
python -m uvicorn web.main:app --reload --host 127.0.0.1 --port 8000
```

## Pruebas Locales (Sin Enviar a SIFEN)

### Smoke Test de Firma y ZIP

```bash
source .venv/bin/activate
python -m tools.smoke_sign_and_zip --xml artifacts/algun_de.xml
```

Este comando:
- Normaliza el XML a rDE
- Firma con xmlsec (rsa-sha256/sha256)
- Crea ZIP con lote.xml correcto
- Ejecuta preflight
- Guarda artifacts: `last_xde.zip`, `last_lote.xml`
- **NO envía a SIFEN** (solo valida localmente)

### Diagnóstico de Consulta de Lote

```bash
source .venv/bin/activate
python -m tools.print_last_consulta_lote_result
```

## Estructura del Pipeline de Envío

Cuando se presiona "Send" en la web:

1. **Normalización**: XML → rDE con dVerFor=150
2. **Firma Real**: xmlsec con rsa-sha256/sha256
3. **Validación Post-Firma**: Verifica algoritmos y URI correctos
4. **Empaquetado ZIP**: lote.xml (rLoteDE → rDE firmado)
5. **Validación ZIP**: Estructura correcta, sin dId/xDE
6. **Preflight**: Validación completa antes de enviar
7. **Envío**: Solo si todo pasa

Si cualquier paso falla:
- Se guardan artifacts en `artifacts/`
- Se muestra error claro en UI
- **NO se envía a SIFEN**

## Troubleshooting

### Error: "ModuleNotFoundError: No module named 'lxml'"

**Causa**: Python 3.14+ o venv no activado

**Solución**:
```bash
# Verificar versión de Python
python3 --version  # Debe ser 3.11 o 3.12

# Recrear venv con Python correcto
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt
```

### Error: "BLOQUEADO: Dependencias de firma faltantes"

**Causa**: lxml o xmlsec no instalados

**Solución**:
```bash
source .venv/bin/activate
pip install lxml python-xmlsec
python -c "import lxml, xmlsec; print('OK')"
```

### Error: "dCodRes=0160 XML Mal Formado"

**Causa**: lote.xml contiene dId/xDE o firma incorrecta

**Solución**:
1. Verificar artifacts: `unzip -p artifacts/last_xde.zip lote.xml | head -n 5`
2. Verificar que NO contenga dId/xDE: `unzip -p artifacts/last_xde.zip lote.xml | grep -nE "<dId|<xDE" || echo "OK"`
3. Verificar firma: `unzip -p artifacts/last_xde.zip lote.xml | grep -E "SignatureMethod|DigestMethod"`

## Archivos Importantes

- `scripts/bootstrap_env.sh` - Script de bootstrap automático
- `app/requirements.txt` - Dependencias del proyecto
- `tools/smoke_sign_and_zip.py` - Pruebas locales sin SIFEN
- `tools/send_sirecepde.py` - Pipeline principal de envío
- `web/main.py` - Endpoint web `/de/{id}/send`

## Notas

- **Python 3.14+ NO es compatible** con lxml/xmlsec (no hay wheels)
- El sistema **bloquea automáticamente** si faltan dependencias críticas
- Todos los artifacts se guardan en `artifacts/` para debugging

