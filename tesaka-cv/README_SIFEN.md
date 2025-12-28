# Guía de Generación y Validación XML para SIFEN

Este documento explica cómo generar y validar XML para SIFEN (Sistema Integrado de Facturación Electrónica Nacional) de Paraguay.

## Conceptos Clave

SIFEN requiere **dos tipos de XML**:

1. **DE crudo** (Documento Electrónico): El documento electrónico en sí, valida contra `DE_v150.xsd`
2. **siRecepDE** (Envelope de recepción): Wrapper que contiene el DE dentro de `xDE`, valida contra `WS_SiRecepDE_v150.xsd`

Según la Nota Técnica oficial NT_E_KUATIA_010_MT_V150.pdf:
> "xDE = XML del DE transmitido"

## Generación de XML

### 1. Generar DE crudo

```bash
cd tesaka-cv
python -m tools.build_de --output artifacts/de_test.xml
```

Con parámetros personalizados:

```bash
python -m tools.build_de \
  --ruc 80012345 \
  --timbrado 12345678 \
  --csc 123456789 \
  --output artifacts/de_test.xml
```

El DE crudo generado contiene:
- Elemento raíz: `<DE>` (tipo `tDE`)
- Namespace: `http://ekuatia.set.gov.py/sifen/xsd`
- Todos los campos requeridos según `DE_v150.xsd`

### 2. Generar siRecepDE (wrapper)

```bash
python -m tools.build_sirecepde \
  --de artifacts/de_test.xml \
  --output artifacts/sirecepde_test.xml \
  --did 1
```

El siRecepDE generado contiene:
- Elemento raíz: `<rEnviDe>`
- Campo `dId`: Identificador de control de envío
- Campo `xDE`: Contiene el DE crudo

## Validación

### Validación local con XSD

```bash
# Validar DE crudo contra DE_v150.xsd
python -m tools.validate_xsd --schema de artifacts/de_test.xml

# Validar siRecepDE contra WS_SiRecepDE_v150.xsd
python -m tools.validate_xsd --schema sirecepde artifacts/sirecepde_test.xml
```

El validador:
- Resuelve dependencias XSD localmente (imports/includes)
- Muestra errores con línea, columna y XPath
- Usa XSDs desde `schemas_sifen/`

### Validación con Prevalidador SIFEN (manual)

El Prevalidador oficial es una aplicación web Angular, no tiene API REST pública.

**Pasos para validar manualmente:**

1. Abrir el Prevalidador en el navegador:
   ```
   https://ekuatia.set.gov.py/prevalidador/validacion
   ```

2. Copiar el contenido del **DE crudo** generado:
   ```bash
   cat artifacts/de_test.xml
   ```

3. Pegar el XML en el formulario del Prevalidador

4. Hacer clic en "Validar"

5. Revisar los resultados de validación

**⚠️ Importante:** El Prevalidador valida el **DE crudo**, no el siRecepDE. El campo `xDE` del siRecepDE se usa para el envío al servicio SOAP, pero para prevalidación manual se usa el DE crudo.

## Smoke Test

El sistema incluye un smoke test automatizado que:

1. Genera DE crudo
2. Genera siRecepDE wrappeando el DE
3. Valida ambos XML contra sus XSDs
4. Guarda artefactos en `artifacts/`
5. Intenta prevalidar (si está disponible)

**Ejecutar smoke test:**

```bash
# Desde la aplicación web
http://localhost:8600/dev/sifen-smoke-test

# O via API
curl -X POST http://localhost:8600/dev/sifen-smoke-test
```

Los XML generados se guardan en:
- `artifacts/de_YYYYMMDD_HHMMSS.xml`
- `artifacts/sirecepde_YYYYMMDD_HHMMSS.xml`

## Estructura de Archivos

```
tesaka-cv/
├── schemas_sifen/          # XSDs oficiales descargados
│   ├── DE_v150.xsd
│   ├── WS_SiRecepDE_v150.xsd
│   ├── DE_Types_v150.xsd
│   └── ...
├── tools/
│   ├── build_de.py         # Generador de DE crudo
│   ├── build_sirecepde.py  # Generador de siRecepDE
│   ├── validate_xsd.py     # Validador XSD
│   └── xsd_resolver.py     # Resolución de dependencias XSD
├── artifacts/              # XMLs generados por smoke test
│   ├── de_*.xml
│   └── sirecepde_*.xml
└── README_SIFEN.md         # Este archivo
```

## Actualizar XSDs

Para descargar los XSD más recientes:

```bash
cd tesaka-cv
python -m tools.download_xsd
```

Esto actualiza los archivos en `schemas_sifen/` desde el índice oficial:
https://ekuatia.set.gov.py/sifen/xsd/

## Ejemplo Completo

```bash
# 1. Generar DE crudo
python -m tools.build_de \
  --ruc 80012345 \
  --timbrado 12345678 \
  --output artifacts/de_ejemplo.xml

# 2. Validar DE crudo
python -m tools.validate_xsd --schema de artifacts/de_ejemplo.xml

# 3. Generar siRecepDE
python -m tools.build_sirecepde \
  --de artifacts/de_ejemplo.xml \
  --output artifacts/sirecepde_ejemplo.xml

# 4. Validar siRecepDE
python -m tools.validate_xsd --schema sirecepde artifacts/sirecepde_ejemplo.xml

# 5. Prevalidar manualmente:
#    - Abrir https://ekuatia.set.gov.py/prevalidador/validacion
#    - Copiar contenido de artifacts/de_ejemplo.xml
#    - Pegar y validar
```

## Referencias

- **Portal oficial**: https://ekuatia.set.gov.py
- **Prevalidador**: https://ekuatia.set.gov.py/prevalidador/
- **Índice XSD**: https://ekuatia.set.gov.py/sifen/xsd/
- **Documentación técnica**: https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica
- **Nota Técnica**: NT_E_KUATIA_010_MT_V150.pdf (sobre estructura xDE)

