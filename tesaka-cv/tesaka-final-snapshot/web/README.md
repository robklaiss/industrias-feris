# Frontend Web TESAKA-SIFEN

Frontend web mínimo (solo lectura) para visualizar documentos electrónicos SIFEN almacenados en PostgreSQL.

## Instalación

1. Instalar dependencias:
```bash
pip install fastapi uvicorn jinja2 "psycopg[binary]"
```

O si ya existe `requirements.txt` en `app/`:
```bash
pip install -r app/requirements.txt
```

## Configuración

Configurar la variable de entorno `DATABASE_URL`:

```bash
export DATABASE_URL="postgresql://tesaka:tesaka_dev_password@localhost:5432/tesaka"
```

Para desarrollo local, si no se configura `DATABASE_URL`, se usa el fallback:
```
postgresql://tesaka:tesaka_dev_password@localhost:5432/tesaka
```

## Ejecución

Desde el directorio raíz del proyecto (`tesaka-cv`):

```bash
uvicorn web.main:app --reload --port 8000
```

Luego abrir en el navegador:
```
http://localhost:8000
```

## Funcionalidades

### 1. Lista de Documentos (`/`)
- Muestra todos los documentos de la tabla `public.de_documents`
- Columnas: ID, Fecha, CDC, RUC Emisor, Timbrado, Estado, Código
- Ordenados por fecha de creación descendente (últimos primero)
- Click en CDC o ID para ver detalle

### 2. Detalle de Documento (`/docs/{id}`)
- Muestra toda la información del documento:
  - Metadata: ID, fecha, CDC, RUC emisor, timbrado, estado, código, mensaje
  - Contenido XML en 3 bloques expandibles:
    - **DE**: Documento Electrónico original
    - **siRecepDE**: XML de envío a SIFEN
    - **Signed**: XML firmado
- Si algún XML es NULL, se muestra "(vacío)"
- Botón "Volver" para regresar a la lista

## Estructura

```
web/
├── __init__.py
├── main.py          # Aplicación FastAPI
├── db.py            # Conexión y queries a PostgreSQL
├── templates/       # Plantillas Jinja2
│   ├── base.html
│   ├── index.html
│   └── doc.html
└── static/          # Archivos estáticos
    └── app.css
```

## Base de Datos

El frontend espera una tabla `public.de_documents` en PostgreSQL con las siguientes columnas:

- `id` (INTEGER PRIMARY KEY)
- `created_at` (TIMESTAMP)
- `cdc` (TEXT)
- `ruc_emisor` (TEXT)
- `timbrado` (TEXT)
- `last_status` (TEXT)
- `last_code` (TEXT)
- `last_message` (TEXT)
- `de_xml` (TEXT)
- `sirecepde_xml` (TEXT)
- `signed_xml` (TEXT)

