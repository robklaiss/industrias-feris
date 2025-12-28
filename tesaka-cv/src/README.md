# Validador de Comprobantes Virtuales Tesaka

Herramienta CLI para validar archivos JSON de comprobantes virtuales según las especificaciones técnicas de Tesaka.

## Instalación

### Opción 1: Sin entorno virtual (instalación global)

```bash
pip install jsonschema
```

### Opción 2: Con entorno virtual (recomendado)

```bash
# Crear entorno virtual
python3 -m venv venv

# Activar entorno virtual
# En Linux/Mac:
source venv/bin/activate
# En Windows:
venv\Scripts\activate

# Instalar dependencias
pip install jsonschema
```

## Uso

El validador acepta dos comandos: `import` y `export`.

### Validar comprobante de importación

```bash
python validate.py import <archivo.json>
```

**Ejemplo:**
```bash
python validate.py import ../ejemplos/comprobante_importacion.json
```

### Validar comprobante de exportación

```bash
python validate.py export <archivo.json>
```

**Ejemplo:**
```bash
python validate.py export ../ejemplos/comprobante_exportacion.json
```

## Ejemplos de Salida

### Validación exitosa

```
✅ Validación exitosa para comprobante.json
```

### Validación con errores

```
❌ Validación fallida para comprobante.json (3 error(es)):

1. Campo: informado -> ruc (ruta absoluta: 0 -> informado -> ruc)
  Error: Campo requerido faltante: 'ruc'

2. Campo: transaccion -> numeroTimbrado (ruta absoluta: 0 -> transaccion -> numeroTimbrado)
  Error: Formato inválido. Patrón esperado: ^\d{8}$

3. Campo: detalle -> 0 -> cantidad (ruta absoluta: 0 -> detalle -> 0 -> cantidad)
  Error: Tipo incorrecto. Se esperaba: number
```

## Estructura de Proyecto

```
tesaka-cv/
├── docs/
│   ├── fuentes/
│   │   ├── Exportacion.pdf
│   │   └── Importacion.pdf
│   └── resumen_requisitos.md
├── schemas/
│   ├── importacion.schema.json
│   └── exportacion.schema.json
└── src/
    ├── validate.py
    └── README.md
```

## Requisitos

- Python 3.6 o superior
- jsonschema (se instala con `pip install jsonschema`)

## Notas

- Los schemas están basados en JSON Schema Draft 2020-12
- El validador verifica estructura, tipos, formatos, valores permitidos y reglas condicionales
- Los errores muestran la ruta completa al campo que falló la validación
- Para más detalles sobre los requisitos, consulta `/docs/resumen_requisitos.md`

