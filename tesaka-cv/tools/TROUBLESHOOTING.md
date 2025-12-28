# Troubleshooting Validación XSD

## Problema: "No matching global declaration available for the validation root"

Este error indica que se está usando el XSD incorrecto para el tipo de XML, o que el elemento raíz no está declarado como elemento global en el XSD.

### Solución 1: Usar el XSD correcto según el tipo de XML

- **DE crudo** (elemento raíz `DE`): usar `DE_v150.xsd`
  ```bash
  python -m tools.validate_xsd --schema de archivo_de.xml
  ```

- **siRecepDE** (elemento raíz `rEnviDe`): usar `WS_SiRecepDE_v150.xsd`
  ```bash
  python -m tools.validate_xsd --schema sirecepde archivo_sirecepde.xml
  ```

- **rDE** (elemento raíz `rDE`): usar `siRecepDE_v150.xsd`
  ```bash
  python -m tools.validate_xml archivo_rde.xml  # Auto-detecta
  ```

### Solución 2: Verificar Namespace

El XML debe usar el mismo namespace que el XSD:

```xml
<DE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
```

### Solución 2: Verificar que el XSD está completo

El elemento `DE` debe estar declarado como elemento global en el XSD (no dentro de otro elemento):

```xml
<xs:element name="DE" type="tDE" />
```

### Solución 3: Verificar dependencias

Asegúrate de que todos los XSD dependientes estén descargados:

```bash
python -m tools.download_xsd
```

Verifica que estos archivos existan en `xsd/`:
- `DE_v150.xsd` (o versión correcta)
- `DE_Types_v150.xsd`
- `Paises_v100.xsd`
- `Departamentos_v141.xsd`
- `Monedas_v150.xsd`
- `Unidades_Medida_v141.xsd`
- `xmldsig-core-schema.xsd`

### Solución 4: El XML puede ser válido estructuralmente pero no coincidir con el esquema

El XML generado es una estructura tentativa. Para generar XML válido según SIFEN:

1. Revisar el Manual Técnico V150
2. Comparar con ejemplos oficiales
3. Ajustar el generador según la estructura exacta requerida

## Problema: "Failed to load document" al validar XSD

El resolutor de dependencias no está encontrando los archivos XSD dependientes.

### Solución:

1. Verificar que todos los XSD están descargados
2. Los archivos deben estar en `tesaka-cv/xsd/`
3. El resolutor busca archivos por nombre, verifica que los nombres coincidan

## Verificación Manual

Para verificar manualmente que el XSD funciona:

```python
from lxml import etree

# Parsear XSD
xsd = etree.parse('xsd/DE_v150.xsd')
schema = etree.XMLSchema(xsd)

# Parsear XML
xml = etree.parse('test.xml')

# Validar
schema.validate(xml)
```

Si falla, los errores estarán en `schema.error_log`.

