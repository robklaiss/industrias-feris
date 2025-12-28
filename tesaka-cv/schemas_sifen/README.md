# Esquemas XSD de SIFEN

Este directorio contiene los esquemas XSD oficiales de SIFEN descargados desde:
https://ekuatia.set.gov.py/sifen/xsd/

## Archivos principales

- **DE_v150.xsd**: Esquema para Documento Electrónico (DE) crudo
- **WS_SiRecepDE_v150.xsd**: Esquema para envelope de recepción (rEnviDe)
- **DE_Types_v150.xsd**: Tipos comunes para DE
- **Paises_v100.xsd**: Catálogo de países
- **Monedas_v150.xsd**: Catálogo de monedas
- **Departamentos_v141.xsd**: Catálogo de departamentos
- **Unidades_Medida_v141.xsd**: Catálogo de unidades de medida
- **xmldsig-core-schema.xsd**: Esquema para firma digital XML

## Cómo actualizar los XSD

Para descargar los XSD más recientes desde el índice oficial del servidor DNIT/SET:

```bash
cd tesaka-cv
python -m tools.download_xsd
```

Esto:
1. Accede al índice oficial: https://ekuatia.set.gov.py/sifen/xsd/
2. Descarga todos los archivos `.xsd` listados en el índice
3. Resuelve automáticamente dependencias (imports/includes)
4. Guarda todos los archivos en este directorio (`schemas_sifen/`)

**Nota:** El script parsea el HTML del índice para obtener la lista de archivos disponibles. Si el formato del índice cambia, puede ser necesario actualizar el script.

## Validación local

Los XSDs en este directorio se usan para validación local de XML antes de enviar a SIFEN:

```bash
# Validar DE crudo
python -m tools.validate_xsd --schema de artifacts/de_test.xml

# Validar siRecepDE
python -m tools.validate_xsd --schema sirecepde artifacts/sirecepde_test.xml
```

El validador resuelve automáticamente dependencias (imports/includes) buscando archivos locales en este directorio.

## Notas

- Los XSDs incluyen referencias a URLs remotas para includes/imports
- El validador local resuelve estas dependencias usando archivos locales cuando están disponibles
- Si falta algún XSD dependiente, el validador mostrará un error indicando qué archivo falta

