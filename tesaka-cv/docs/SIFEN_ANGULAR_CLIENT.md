# Cliente para Aplicación Angular del Prevalidador SIFEN

Este módulo permite comunicarse directamente con la aplicación Angular del Prevalidador SIFEN, descubriendo y usando los endpoints API REST que la aplicación utiliza internamente.

## Características

### 1. Descubrimiento Automático de Endpoints

El cliente `AngularPrevalidadorClient` inspecciona:
- Código HTML de la aplicación Angular
- Archivos JavaScript cargados (main.js, vendor.js, etc.)
- Referencias a servicios HTTP y endpoints API

Endpoints comunes que busca:
- `/api/validar`
- `/api/prevalidate`
- `/api/prevalidar`
- `/api/validate`
- `/api/validacion`

### 2. Múltiples Métodos de Comunicación

El cliente intenta múltiples estrategias para comunicarse:

1. **POST JSON**: Envía XML como JSON `{"xml": "..."}`
2. **POST XML**: Envía XML directamente con Content-Type `application/xml`
3. **Multipart Form-Data**: Simula el formulario web de Angular
4. **Form URL-Encoded**: Envía como formulario tradicional

### 3. Integración en Smoke Test

El smoke test ahora intenta automáticamente comunicarse con la aplicación Angular antes de otros métodos.

## Uso

### Desde Python

```python
from app.sifen_client.angular_prevalidador import AngularPrevalidadorClient

client = AngularPrevalidadorClient()

# Probar conexión
connection_info = client.test_connection()
print(f"Conectado: {connection_info['connected']}")
print(f"Endpoints: {connection_info['endpoints_discovered']}")

# Prevalidar XML
result = client.prevalidate_xml(xml_content)
print(f"Método usado: {result.get('method')}")
print(f"Endpoint: {result.get('endpoint')}")
print(f"Válido: {result.get('valid')}")

client.close()
```

### Desde la UI Web

#### 1. Probar Conexión Angular

En la página del smoke test (`/dev/sifen-smoke-test`):
1. Haz clic en **"Probar Conexión Angular"**
2. Verás los endpoints descubiertos y el estado de la conexión

#### 2. Prevalidar con App Angular

1. Pega tu XML en el textarea
2. Haz clic en **"Prevalidar con App Angular"**
3. El sistema intentará comunicarse directamente con los endpoints API de Angular

#### 3. Smoke Test Automático

El smoke test (`POST /dev/sifen-smoke-test`) ahora intenta automáticamente:
1. Validar estructura XML
2. Validar contra XSD
3. Comunicarse con app Angular del Prevalidador
4. Fallback a otros métodos si Angular no responde

## Endpoints FastAPI

### `GET /dev/sifen-test-angular`

Prueba la conexión con la aplicación Angular y descubre endpoints.

**Respuesta:**
```json
{
  "ok": true,
  "connection": {
    "connected": true,
    "status_code": 200,
    "endpoints_discovered": {
      "validar": "https://ekuatia.set.gov.py/prevalidador/api/validar",
      ...
    },
    "is_angular_app": false,
    "has_api_endpoints": true
  }
}
```

### `POST /dev/sifen-prevalidate-angular`

Prevalida XML usando directamente la aplicación Angular.

**Request:**
```json
{
  "xml": "<?xml version=\"1.0\"?>..."
}
```

**Respuesta:**
```json
{
  "ok": true,
  "result": {
    "valid": true,
    "method": "API JSON (validar)",
    "endpoint": "https://ekuatia.set.gov.py/prevalidador/api/validar",
    "response": {...}
  }
}
```

## Limitaciones

1. **Endpoints No Públicos**: Los endpoints API pueden no estar documentados públicamente
2. **Cambios en Angular**: La aplicación Angular puede cambiar sus endpoints sin aviso
3. **Autenticación**: Algunos endpoints pueden requerir autenticación/tokens
4. **CORS**: Algunos endpoints pueden tener restricciones CORS

## Troubleshooting

### No se encuentran endpoints

```
Endpoints descubiertos: {}
```

**Solución**: 
- La aplicación Angular puede no exponer endpoints API públicos
- Verifica manualmente en DevTools del navegador (Network tab) qué endpoints se usan
- Actualiza `angular_prevalidador.py` con los endpoints descubiertos

### Respuesta HTML en lugar de JSON

```
response_type: "html"
```

**Solución**:
- El endpoint devuelve la aplicación web completa
- No hay API REST disponible públicamente
- Usa el formulario web manualmente

### Timeout

**Solución**:
- Verifica conectividad a internet
- Aumenta el timeout en `AngularPrevalidadorClient(timeout=60)`

## Próximos Pasos

1. Monitorear Network tab en DevTools para descubrir endpoints reales
2. Documentar endpoints descubiertos manualmente
3. Implementar autenticación si es requerida
4. Manejar tokens de sesión si la app Angular los usa

