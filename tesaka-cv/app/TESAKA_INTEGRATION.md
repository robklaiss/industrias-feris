# Integración con Tesaka (SET) - Documentación

## Configuración

1. **Crear archivo `.env`** en el directorio raíz del proyecto (`tesaka-cv/`) con las siguientes variables:

```env
# Entorno: 'prod' (producción) o 'homo' (homologación)
TESAKA_ENV=homo

# Credenciales de autenticación Basic Auth
TESAKA_USER=tu_usuario
TESAKA_PASS=tu_contraseña

# Timeout de peticiones HTTP en segundos
REQUEST_TIMEOUT=30
```

2. **Instalar dependencias**:
```bash
pip install -r requirements.txt
```

Esto instalará `httpx` y `python-dotenv` necesarios para la integración.

## Uso

### Envío de Facturas

Desde la vista de una factura (`/invoices/{id}`), puedes:

1. **Validar** la factura contra el schema de importación
2. **Exportar** el JSON Tesaka para descarga
3. **Enviar a SET** directamente:
   - Botón "Enviar a SET (Factura)" - Para facturas normales
   - Botón "Enviar a SET (Retención)" - Para retenciones
   - Botón "Enviar a SET (Autofactura)" - Para autofacturas
4. **Ver historial** de envíos con el botón "Ver Historial de Envíos"

### Endpoints API

#### POST `/invoices/{invoice_id}/send/{kind}`

Envía una factura a Tesaka.

- `invoice_id`: ID de la factura
- `kind`: Tipo de comprobante (`factura`, `retencion`, `autofactura`)

**Respuesta exitosa:**
```json
{
  "ok": true,
  "response": { ... }
}
```

**Respuesta con error:**
```json
{
  "ok": false,
  "error": "Mensaje de error"
}
```

#### GET `/invoices/{invoice_id}/submissions`

Obtiene el historial de envíos de una factura.

**Respuesta:**
```json
{
  "submissions": [
    {
      "id": 1,
      "kind": "factura",
      "env": "homo",
      "created_at": "2025-12-26 20:00:00",
      "ok": true,
      "error": null,
      "request_json": { ... },
      "response_json": { ... }
    }
  ]
}
```

## Estructura de Base de Datos

Se ha agregado la tabla `submissions` para registrar todos los envíos:

```sql
CREATE TABLE submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('factura', 'retencion', 'autofactura')),
    env TEXT NOT NULL CHECK(env IN ('prod', 'homo')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    request_json TEXT NOT NULL,
    response_json TEXT,
    ok INTEGER DEFAULT 0,
    error TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);
```

## Endpoints de Tesaka

### Producción
- Facturas: `https://marangatu.set.gov.py/eset-restful/facturas/guardar`
- Retenciones: `https://marangatu.set.gov.py/eset-restful/retenciones/guardar`
- Autofacturas: `https://marangatu.set.gov.py/eset-restful/autofacturas/guardar`
- Consultar Contribuyente: `https://marangatu.set.gov.py/eset-restful/contribuyentes/consultar`

### Homologación
- Base URL: `https://m2hom.set.gov.py/servicios-retenciones`

## Flujo de Envío

1. El usuario hace clic en "Enviar a SET"
2. El sistema:
   - Carga la factura desde la BD
   - Convierte a formato Tesaka usando `convert_to_tesaka()`
   - Valida contra el schema usando `validate_tesaka()`
   - Envía a Tesaka usando `TesakaClient`
   - Guarda el resultado en la tabla `submissions`
   - Retorna el resultado al usuario

## Manejo de Errores

El cliente maneja automáticamente:
- **401**: Error de autenticación (credenciales incorrectas)
- **400**: Error de validación del comprobante
- **500+**: Errores del servidor Tesaka
- **Timeout**: Peticiones que exceden el timeout configurado
- **Errores de conexión**: Problemas de red

Todos los errores se registran en la tabla `submissions` con `ok=0` y el mensaje de error.

