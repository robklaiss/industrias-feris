# Configuración de Validación XSD para SIFEN

Este documento explica cómo configurar la validación de XML contra esquemas XSD oficiales de SIFEN.

## 1. Descargar Esquemas XSD Oficiales

### Opción A: Script Automático

```bash
python -m tools.download_xsd
```

Este script:
- Descarga XSD desde https://ekuatia.set.gov.py/sifen/xsd/
- Guarda en `tesaka-cv/xsd/`
- Resuelve imports/includes automáticamente

### Opción B: Descarga Manual

1. Visitar: https://ekuatia.set.gov.py/sifen/xsd/
2. Descargar archivos `.xsd` relevantes
3. Guardar en `tesaka-cv/xsd/`

**XSD Principal esperado**: `DE_v150.xsd` o `DE_v130.xsd`

## 2. Descargar "Estructura xml_DE"

La estructura oficial puede estar disponible como:
- Paquete `.rar` desde DNIT
- Documentación técnica en PDF

**Ubicación esperada**: `tesaka-cv/manual/estructura_xml_DE/`

Si dispones del paquete, descomprímelo en ese directorio.

## 3. Descargar Manual Técnico V150

1. Visitar: https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica
2. Descargar "Manual Técnico V150" (o versión disponible)
3. Guardar en `tesaka-cv/manual/`

**Nombre esperado**: `Manual_Tecnico_SIFEN_V150.pdf` o similar

## 4. Validación Local

Una vez descargados los XSD, puedes validar XML localmente:

### Desde Línea de Comandos

```bash
# Validación básica
python -m tools.validate_xml archivo.xml

# Con prevalidación SIFEN
python -m tools.validate_xml archivo.xml --prevalidate

# Especificar XSD
python -m tools.validate_xml archivo.xml --xsd xsd/DE_v150.xsd
```

### Desde Código Python

```python
from app.sifen_client.validator import SifenValidator

validator = SifenValidator()
result = validator.validate_against_xsd(xml_content)

if result["valid"]:
    print("✅ XML válido")
    print(f"XSD usado: {result.get('xsd_used')}")
else:
    print("❌ XML inválido:")
    for error in result["errors"]:
        print(f"  - {error}")
```

### En el Smoke Test

El smoke test (`/dev/sifen-smoke-test`) ahora valida automáticamente contra XSD si está disponible.

## 5. Estructura de Directorios

```
tesaka-cv/
├── xsd/                  # Esquemas XSD oficiales
│   ├── DE_v150.xsd
│   ├── DE_v130.xsd
│   └── ...
├── manual/               # Documentación oficial
│   ├── Manual_Tecnico_SIFEN_V150.pdf
│   └── estructura_xml_DE/
├── tools/                # Herramientas de desarrollo
│   ├── download_xsd.py
│   └── validate_xml.py
└── app/
    └── sifen_client/
        └── validator.py  # Validador integrado
```

## 6. Resolución de Problemas

### XSD no encontrado

```
Error: Esquema XSD no encontrado
```

**Solución**: Ejecutar `python -m tools.download_xsd`

### Error al parsear XSD

```
Error: Error al parsear XSD: ...
```

**Posibles causas**:
- XSD corrupto o incompleto
- Faltan dependencias (imports/includes)
- Versión de lxml incompatible

**Solución**: 
- Re-descargar XSD
- Verificar que todos los imports estén disponibles
- Actualizar lxml: `pip install --upgrade lxml`

### XML válido pero rechazado por Prevalidador

El Prevalidador puede tener validaciones adicionales no cubiertas por XSD:
- Validaciones de negocio
- Verificación de timbrado/CSC
- Validaciones de datos de prueba

**Solución**: Revisar errores del Prevalidador y ajustar según documentación oficial.

## 7. Próximos Pasos

Una vez configurado:

1. ✅ Validar XML localmente contra XSD
2. ✅ Integrar validación en flujo de generación de documentos
3. ✅ Actualizar generador XML según estructura oficial
4. ✅ Implementar pruebas automatizadas

## Referencias

- Portal SIFEN: https://ekuatia.set.gov.py/
- Índice XSD: https://ekuatia.set.gov.py/sifen/xsd/
- Documentación Técnica: https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica
- Prevalidador: https://ekuatia.set.gov.py/prevalidador/validacion

