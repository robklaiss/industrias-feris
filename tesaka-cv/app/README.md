# Tesaka CV - Aplicación Web

Aplicación web local mínima (MVP) para crear y administrar comprobantes y exportarlos a formato Tesaka (importación).

## Stack Tecnológico

- **Python 3**
- **FastAPI** + **Uvicorn** (servidor web)
- **SQLite** (base de datos)
- **Jinja2** (templates server-side)
- **jsonschema** (validación de schemas)

## Instalación

1. Crear un entorno virtual:
```bash
python -m venv .venv
```

2. Activar el entorno virtual:
```bash
# En macOS/Linux:
source .venv/bin/activate

# En Windows:
.venv\Scripts\activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

## Ejecución

Desde el directorio raíz del proyecto (`tesaka-cv`):

```bash
uvicorn app.main:app --reload
```

Luego abrir en el navegador:
```
http://127.0.0.1:8000/invoices
```

## Funcionalidades

### 1. Lista de Facturas (`/invoices`)
- Muestra todas las facturas guardadas
- Muestra: ID, fecha de emisión, comprador, total calculado, fecha de creación
- Botón para crear nueva factura

### 2. Crear Factura (`/invoices/new`)
- Formulario completo para crear una factura con todos los campos:
  - Información general (fecha de emisión, fecha/hora opcional)
  - Comprador (buyer) con todos los campos según situación
  - Transacción (condición de compra, tipo de comprobante, números, etc.)
  - Items (múltiples items con cantidad, tasa, precio, descripción)
  - Retención (todos los campos de retención)
- Validación de campos requeridos
- Guardado en SQLite como JSON

### 3. Ver Factura (`/invoices/{id}`)
- Muestra todos los detalles de la factura
- Botón "Validar contra schema importación": valida el comprobante Tesaka generado contra el schema
- Botón "Exportar JSON Tesaka": descarga el archivo JSON en formato Tesaka de importación

## Estructura de Base de Datos

Tabla `invoices`:
- `id` (INTEGER PRIMARY KEY)
- `created_at` (TIMESTAMP)
- `issue_date` (TEXT)
- `buyer_name` (TEXT)
- `data_json` (TEXT) - JSON completo de la factura interna

## Formato de Datos

Las facturas se guardan en el formato definido en `docs/formato_factura_interna.md` y se convierten automáticamente al formato Tesaka de importación usando la lógica de `src/convert_to_import.py`.

## Desarrollo

La aplicación se ejecuta en modo desarrollo con `--reload` para recargar automáticamente cuando hay cambios en el código.

## Notas

- No hay autenticación implementada (MVP)
- No se conecta a servicios remotos de Tesaka
- Solo genera y valida archivos JSON localmente

