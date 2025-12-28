# Notas sobre Validación XSD SIFEN

## Estructura del XSD

### XSD Principal: `DE_v150.xsd`

Este XSD define:
- Complextype `tDE`: Estructura del Documento Electrónico
- Complextype `rDE`: Root element que contiene `DE` + firma + otros campos
- Tipos relacionados

### XSD para Validación: `siRecepDE_v150.xsd`

Este XSD define el elemento global `rDE`:

```xml
<xs:element name="rDE" type="rDE"/>
```

### Estructura XML Esperada

Para validación, el XML debe tener la estructura:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <dVerFor>150</dVerFor>
    <DE>
        <!-- Contenido del documento -->
    </DE>
    <ds:Signature>
        <!-- Firma digital -->
    </ds:Signature>
    <gCamFuFD>
        <!-- Campos adicionales -->
    </gCamFuFD>
</rDE>
```

**NO**:

```xml
<DE>
    <!-- Esto no es válido como raíz -->
</DE>
```

## Solución Temporal

El XML generado actualmente es una estructura básica para pruebas. Para validación completa:

1. El XML debe usar `rDE` como elemento raíz
2. Debe incluir todos los campos requeridos según el complextype `rDE`
3. Debe validarse contra `siRecepDE_v150.xsd` (o similar)

## Próximos Pasos

1. ✅ Descargar XSD oficiales - COMPLETADO
2. ✅ Resolver dependencias XSD - COMPLETADO
3. ⏳ Actualizar generador XML para usar estructura `rDE` correcta
4. ⏳ Validar contra `siRecepDE_v150.xsd`

