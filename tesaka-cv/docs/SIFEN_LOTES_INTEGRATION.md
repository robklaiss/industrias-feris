# Integración de Consulta de Lotes SIFEN

Este documento describe la integración del sistema de consulta automática de lotes SIFEN.

## Resumen

Cuando se envía un lote a SIFEN (`siRecepLoteDE`) y se recibe el `dProtConsLote`, el sistema:

1. **Extrae y guarda** el `dProtConsLote` en la base de datos
2. **Consulta automáticamente** el estado del lote usando SOAP RAW
3. **Actualiza el estado** según la respuesta de SIFEN
4. **Permite reintentos** configurable mediante polling

## Componentes

### 1. Base de Datos (`web/lotes_db.py`)

Tabla `sifen_lotes` con campos:
- `id`: ID único del lote
- `env`: Ambiente (test/prod)
- `d_prot_cons_lote`: Número de lote (solo dígitos)
- `created_at`: Fecha de creación
- `last_checked_at`: Última consulta
- `last_cod_res_lot`: Código de respuesta (ej: "0361", "0362", "0364")
- `last_msg_res_lot`: Mensaje de respuesta
- `last_response_xml`: XML completo de respuesta
- `status`: Estado (pending, processing, done, expired_window, requires_cdc, error)
- `attempts`: Número de intentos de consulta
- `de_document_id`: ID del documento relacionado (opcional)

### 2. Módulo de Consulta (`app/sifen_client/lote_checker.py`)

Funciones principales:
- `validate_prot_cons_lote(prot)`: Valida que el número de lote sea solo dígitos
- `parse_lote_response(xml_response)`: Parsea XML de respuesta para extraer `dCodResLot` y `dMsgResLot`
- `check_lote_status(env, prot, ...)`: Consulta el estado de un lote en SIFEN
- `determine_status_from_cod_res_lot(cod_res_lot)`: Determina el estado basado en el código

### 3. Job de Polling (`tools/poll_sifen_lotes.py`)

Script ejecutable que:
- Consulta lotes en estado `pending` o `processing`
- Actualiza el estado según la respuesta
- Soporta ejecución continua (loop) o única (para cron)
- Implementa backoff gradual en intervalos

### 4. Endpoint de Envío (`web/main.py`)

- `POST /de/{doc_id}/send?mode=lote` (default): Envía como lote (siRecepLoteDE)
  - Guarda `dProtConsLote` en `sifen_lotes`
  - Consulta automáticamente el estado del lote
  - Respuesta asíncrona (requiere consulta posterior para obtener CDC)
  
- `POST /de/{doc_id}/send?mode=direct`: Envía directamente (siRecepDE)
  - Respuesta inmediata con CDC (si está aprobado)
  - No crea registros en `sifen_lotes`
  - Útil para pruebas rápidas o cuando se necesita respuesta inmediata

### 5. Endpoints Admin (`web/main.py`)

- `GET /admin/sifen/lotes`: Lista lotes con filtros (env, status)
- `GET /admin/sifen/lotes/{id}`: Detalle de un lote con XML de respuesta

## Flujo de Integración

### Envío de Lote

Cuando se envía un lote (`tools/send_sirecepde.py`):

1. Se llama a `SoapClient.recepcion_lote()`
2. La respuesta incluye `d_prot_cons_lote` (extraído en `soap_client.py`)
3. Se crea un registro en `sifen_lotes` con estado `pending`

```python
# En tools/send_sirecepde.py (línea ~505)
d_prot_cons_lote = response.get('d_prot_cons_lote')
if d_prot_cons_lote:
    from web.lotes_db import create_lote
    lote_id = create_lote(env=env, d_prot_cons_lote=d_prot_cons_lote)
```

### Consulta Automática

El job de polling (`tools/poll_sifen_lotes.py`) consulta lotes automáticamente:

```bash
# Ejecución continua (loop cada 60s)
python -m tools.poll_sifen_lotes --env test

# Ejecución única (útil para cron)
python -m tools.poll_sifen_lotes --env test --once

# Con límite de intentos
python -m tools.poll_sifen_lotes --env test --max-attempts 10
```

### Estados y Códigos

| Código | Estado | Descripción |
|--------|--------|-------------|
| 0361 | `processing` | Lote en procesamiento (continuar consultando) |
| 0362 | `done` | Lote procesado exitosamente (detener) |
| 0364 | `expired_window` | Ventana de 48h expirada, requiere consulta por CDC (detener) |
| Otros | `error` | Error u otro código no reconocido |

## Variables de Entorno

Requeridas para el polling:

```bash
# Certificado para mTLS
export SIFEN_CERT_PATH="/ruta/al/certificado.p12"
export SIFEN_CERT_PASSWORD="contraseña"

# O alternativamente:
export SIFEN_SIGN_P12_PATH="/ruta/al/certificado.p12"
export SIFEN_SIGN_P12_PASSWORD="contraseña"

# Ambiente (opcional, default: test)
export SIFEN_ENV="test"  # o "prod"
```

## Uso

### 1. Enviar un Lote

```bash
# El lote se guarda automáticamente cuando se recibe dProtConsLote
python -m tools.send_sirecepde --env test --xml artifacts/signed.xml
```

### 2. Consultar Lotes Manualmente

```python
from app.sifen_client.lote_checker import check_lote_status

result = check_lote_status(env="test", prot="123456789")
print(result["cod_res_lot"], result["msg_res_lot"])
```

### 3. Ejecutar Polling

```bash
# Modo continuo (recomendado para desarrollo)
python -m tools.poll_sifen_lotes --env test

# Modo único (recomendado para cron)
python -m tools.poll_sifen_lotes --env test --once
```

### 4. Ver Lotes en Web

Abrir en navegador:
- Lista: http://127.0.0.1:8000/admin/sifen/lotes
- Detalle: http://127.0.0.1:8000/admin/sifen/lotes/{id}

### 5. Configurar Cron (Producción)

```cron
# Consultar lotes cada 5 minutos
*/5 * * * * cd /ruta/al/proyecto && /ruta/al/venv/bin/python -m tools.poll_sifen_lotes --env prod --once >> /var/log/sifen_poll.log 2>&1
```

## Validaciones

### dProtConsLote

- **Debe ser solo dígitos**: Si contiene letras o caracteres especiales, se rechaza antes de llamar a SIFEN
- **Validación automática**: Se valida en `create_lote()` y `check_lote_status()`

```python
# Ejemplo de validación
if not d_prot_cons_lote.strip().isdigit():
    raise ValueError("dProtConsLote debe ser solo dígitos")
```

## Tests

Ejecutar tests unitarios:

```bash
python -m pytest tests/test_lote_checker.py -v
```

Tests incluidos:
- Validación de `dProtConsLote` (válido/inválido)
- Parsing de respuestas XML (0361, 0362, 0364)
- Determinación de estado desde código

## Troubleshooting

### Error: "dProtConsLote debe ser solo dígitos"

- Verificar que el valor recibido de SIFEN sea numérico
- Revisar logs del envío para ver el valor exacto

### Error: "Faltan certificado P12 o contraseña"

- Configurar `SIFEN_CERT_PATH` y `SIFEN_CERT_PASSWORD`
- O `SIFEN_SIGN_P12_PATH` y `SIFEN_SIGN_P12_PASSWORD`

### Lote queda en "pending" indefinidamente

- Verificar que el polling esté ejecutándose
- Revisar logs del polling para errores
- Verificar conectividad con SIFEN

### Código 0364 (Ventana expirada)

- En TEST, la ventana es de 48 horas
- Después de 48h, SIFEN no permite consultar el lote
- Se debe consultar cada documento individual por CDC

## Archivos Modificados/Creados

### Nuevos
- `web/lotes_db.py`: Gestión de base de datos para lotes
- `app/sifen_client/lote_checker.py`: Módulo de consulta de lotes
- `tools/poll_sifen_lotes.py`: Job de polling automático
- `web/templates/admin_lotes_list.html`: Template para lista de lotes
- `web/templates/admin_lote_detail.html`: Template para detalle de lote
- `tests/test_lote_checker.py`: Tests unitarios

### Modificados
- `app/sifen_client/soap_client.py`: Extrae `d_prot_cons_lote` de respuestas
- `tools/send_sirecepde.py`: Guarda lote en BD cuando se recibe `dProtConsLote`
- `web/main.py`: Agregados endpoints admin para lotes
- `tools/consulta_lote_de.py`: Corregido typo `Clientcle` → `Client`

## Próximos Pasos

1. **Relacionar lotes con documentos**: Actualizar `de_document_id` cuando se envía un lote desde un documento específico
2. **Notificaciones**: Agregar notificaciones cuando un lote cambia de estado
3. **Dashboard**: Crear dashboard con estadísticas de lotes
4. **Retry inteligente**: Implementar retry con backoff exponencial para errores transitorios

