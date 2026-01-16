# Cert-Ready Precheck

Guía para validar que el entorno está listo para operaciones SIFEN con certificados.

## Quick Start

```bash
# 1. Bootstrap del entorno
make bootstrap

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env y configurar SIFEN_P12_PATH y SIFEN_P12_PASSWORD

# 3. Smoke test de consulta RUC
export SIFEN_RUC_CONS="45547378"
make smoke-ruc

# 4. Ejecutar tests SIFEN
make test-sifen
```

## Comandos Disponibles

### `make bootstrap`

Configura el entorno de desarrollo completo:
- Crea virtual environment (`.venv/`) si no existe
- Instala dependencias desde `tesaka-cv/requirements.txt`
- Compila módulos SIFEN clave
- Ejecuta tests básicos de normalización RUC

**Requisitos:**
- Python 3.9+
- Acceso a internet (para pip install)

**Resultado esperado:**
- Virtual environment activo
- Dependencias instaladas
- Tests de normalización pasando

### `make smoke-ruc`

Ejecuta un smoke test end-to-end de consultaRUC contra SIFEN.

**Requisitos:**
- Variable `SIFEN_RUC_CONS` configurada (ej: `export SIFEN_RUC_CONS="45547378"`)
- Certificado P12 configurado en `.env` (SIFEN_P12_PATH y SIFEN_P12_PASSWORD)
- Acceso a internet (llama a SIFEN TEST)

**Uso:**
```bash
export SIFEN_RUC_CONS="45547378"
make smoke-ruc
```

**Resultado esperado:**
- Consulta RUC exitosa
- Respuesta válida de SIFEN
- Evidencia guardada en `evidence/sifen_test/YYYY-MM-DD/`

### `make test-sifen`

Ejecuta la suite completa de tests SIFEN.

**Resultado esperado:**
- Tests pasan o se skippean automáticamente si faltan dependencias opcionales
- Sin errores de collection
- Reporte de tests passed/skipped

### `make send-de-test`

Envío de DE de prueba (pendiente fixture).

**Estado:** Pendiente implementación de fixture de prueba.

## Variables de Entorno

Ver `.env.example` para la lista completa. Variables críticas:

- `SIFEN_ENV`: Ambiente ('test' o 'prod')
- `SIFEN_P12_PATH`: Ruta al certificado P12
- `SIFEN_P12_PASSWORD`: Password del certificado (requerido en web)
- `SIFEN_RUC_CONS`: RUC para smoke tests
- `SIFEN_SKIP_RUC_GATE`: Saltar validación RUC (0=validar, 1=skip)

## Evidencia

Los intercambios SIFEN se guardan automáticamente en:
- `evidence/sifen_{env}/YYYY-MM-DD/`

Cada operación guarda:
- `request_{kind}_{timestamp}.xml` - XML enviado
- `response_{kind}_{timestamp}.xml` - XML recibido
- `meta_{kind}_{timestamp}.json` - Metadata (http_code, dCodRes, dMsgRes, etc.)

**Importante:** Los archivos de evidencia NO incluyen:
- Passwords
- PEMs completos
- Datos sensibles

## Notas de Seguridad

1. **NO commits .env**: El archivo `.env` está en `.gitignore`. Nunca commits secretos.
2. **NO commits passwords**: Nunca agregar passwords a variables de entorno versionadas.
3. **NO commits certificados**: Los archivos `.p12`, `.pem`, `.key` están en `.gitignore`.
4. **Evidencia**: Los archivos de evidencia pueden contener XMLs con datos de facturación.
   Revisar antes de compartir.

## Troubleshooting

### Error: "jsonschema no está instalado"

**Solución:** Ejecutar `make bootstrap` para instalar dependencias.

### Error: "Configuración SIFEN inválida"

**Solución:** Verificar que `.env` tiene:
- `SIFEN_P12_PATH` apuntando a un archivo existente
- `SIFEN_P12_PASSWORD` configurado (en modo web)

### Tests skippeados automáticamente

**Normal:** Si faltan dependencias opcionales (signxml/xmlsec), los tests se skippean.
Para correr suite completa:
```bash
pip install signxml python-xmlsec
```

### Error en bootstrap: "Failed to compile"

**Solución:** Verificar que Python 3.9+ está disponible y que no hay errores de sintaxis en los módulos.

## Dependencias Opcionales

Algunas dependencias son opcionales y pueden ser difíciles de instalar en macOS:

- `xmlsec` / `python-xmlsec`: Requiere `brew install xmlsec1 libxml2 libxslt pkg-config`
- `signxml`: Depende de xmlsec

Si no están instaladas, los tests correspondientes se skippean automáticamente sin romper collection.
