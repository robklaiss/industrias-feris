# Integración de Consulta Automática de Lotes en Backend FastAPI

## Resumen

Se integró la consulta automática de lotes SIFEN dentro del backend FastAPI `tesaka-cv/web/main.py`. Cuando se envía un documento como lote a SIFEN y se recibe `dProtConsLote`, el sistema:

1. **Extrae y valida** `dProtConsLote` (solo dígitos con regex `^\d+$`)
2. **Guarda el lote** en la base de datos SQLite
3. **Consulta automáticamente** el estado del lote usando SOAP RAW
4. **Actualiza el estado** según la respuesta (0361→processing, 0362→done, 0364→requires_cdc)

## Archivos Modificados

### 1. `web/main.py`

**Cambios principales:**

- **`POST /de/{doc_id}/send`**: Modificado para usar `recepcion_lote` en lugar de `recepcion_de`
  - Construye el lote usando `build_r_envio_lote_xml` desde `tools/send_sirecepde`
  - Extrae `d_prot_cons_lote` de la respuesta
  - Valida con regex `^\d+$` antes de guardar
  - Guarda el lote en BD y consulta automáticamente el estado

- **`_check_lote_status_async()`**: Nueva función helper async
  - Ejecuta la consulta en thread pool para no bloquear
  - Usa `check_lote_status` desde `app.sifen_client.lote_checker`
  - Actualiza el estado del lote según la respuesta

- **`POST /admin/sifen/lotes/{lote_id}/check`**: Nuevo endpoint
  - Permite consultar manualmente el estado de un lote
  - Útil para reintentos o verificación manual

### 2. `app/sifen_client/lote_checker.py`

**Cambios:**

- **`determine_status_from_cod_res_lot()`**: Corregido para usar `requires_cdc` cuando el código es 0364
  - Antes usaba `expired_window`, ahora usa `requires_cdc` (más descriptivo)

### 3. `web/templates/admin_lote_detail.html`

**Cambios:**

- Agregado botón "Consultar Estado Ahora" que llama a `POST /admin/sifen/lotes/{lote_id}/check`

## Flujo de Integración

### 1. Envío de Lote

```
POST /de/{doc_id}/send
  ↓
Construir rEnvioLote (ZIP base64)
  ↓
SoapClient.recepcion_lote(payload_xml)
  ↓
Extraer d_prot_cons_lote de respuesta
  ↓
Validar con regex ^\d+$
  ↓
Guardar en sifen_lotes (estado: pending)
  ↓
Consultar automáticamente (async)
  ↓
Actualizar estado según respuesta
```

### 2. Consulta Automática

```
_check_lote_status_async()
  ↓
check_lote_status() (SOAP RAW)
  ↓
Parsear XML respuesta
  ↓
Extraer dCodResLot y dMsgResLot
  ↓
Determinar estado:
  - 0361 → processing
  - 0362 → done
  - 0364 → requires_cdc
  - otros → error
  ↓
Actualizar lote en BD
```

## Estados de Lote

| Código | Estado | Descripción |
|--------|--------|-------------|
| 0361 | `processing` | Lote en procesamiento (continuar consultando) |
| 0362 | `done` | Lote procesado exitosamente (detener) |
| 0364 | `requires_cdc` | Ventana de 48h expirada, requiere consulta por CDC (detener) |
| Otros | `error` | Error u otro código no reconocido |

## Cómo Probar

### 1. Configurar Variables de Entorno

```bash
export SIFEN_EMISOR_RUC="4554737-8"
export SIFEN_SIGN_P12_PATH="/ruta/al/certificado.p12"
export SIFEN_SIGN_P12_PASSWORD="contraseña"
export SIFEN_ENV="test"  # o "prod"
```

### 2. Iniciar Servidor

```bash
cd tesaka-cv/
source ../.venv/bin/activate
python -m uvicorn web.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Enviar Documento

1. Abrir http://127.0.0.1:8000
2. Crear un nuevo DE o usar uno existente
3. Hacer clic en "Enviar a SIFEN" (POST /de/{doc_id}/send)
4. El sistema:
   - Envía el lote a SIFEN
   - Recibe `dProtConsLote`
   - Guarda el lote en BD
   - Consulta automáticamente el estado

### 4. Ver Lotes

- **Lista**: http://127.0.0.1:8000/admin/sifen/lotes
- **Detalle**: http://127.0.0.1:8000/admin/sifen/lotes/{lote_id}
- **Consultar manualmente**: Botón "Consultar Estado Ahora" en el detalle

## Validaciones Implementadas

### dProtConsLote

- **Regex**: `^\d+$` (solo dígitos)
- **Validación**: Antes de guardar en BD
- **Si falla**: Se loguea warning pero no se guarda ni consulta

### Manejo de Errores

- **Errores de red**: Se capturan y se marca el lote como `error`
- **Errores de consulta**: No fallan el envío del documento
- **Lote duplicado**: Se loguea warning pero no se interrumpe el flujo

## Endpoints Disponibles

### Documentos

- `POST /de/{doc_id}/send` - Envía documento como lote y consulta automáticamente

### Lotes (Admin)

- `GET /admin/sifen/lotes` - Lista lotes con filtros (env, status)
- `GET /admin/sifen/lotes/{lote_id}` - Detalle de lote con XML
- `POST /admin/sifen/lotes/{lote_id}/check` - Consulta manual del estado

## Notas Técnicas

### SOAP RAW

- **NO se usa Zeep** para consulta de lote
- Se usa `call_consulta_lote_raw` desde `tools/consulta_lote_de`
- Headers: `Connection: close` para evitar problemas de conexión

### mTLS

- Se usa `p12_to_pem_files` para convertir P12 a PEM temporales
- Los archivos PEM se borran en `finally` después de la consulta
- Se usa `requests.Session` con `session.cert = (cert_pem, key_pem)`

### Async/Await

- La consulta automática se ejecuta en `run_in_executor` para no bloquear
- El envío del documento no espera la consulta (fire-and-forget)

### Persistencia

- Se usa SQLite (`tesaka.db`)
- Tabla `sifen_lotes` con todos los campos requeridos
- Relación con `de_documents` mediante `de_document_id`

## Troubleshooting

### Error: "dProtConsLote no es solo dígitos"

- Verificar que SIFEN devuelva un valor numérico
- Revisar logs del servidor para ver el valor exacto recibido

### Error: "Faltan certificado P12 o contraseña"

- Configurar `SIFEN_SIGN_P12_PATH` y `SIFEN_SIGN_P12_PASSWORD`
- O `SIFEN_CERT_PATH` y `SIFEN_CERT_PASSWORD`

### Lote queda en "pending"

- La consulta automática puede fallar silenciosamente
- Usar el botón "Consultar Estado Ahora" para reintentar manualmente
- Revisar logs del servidor para errores

### Código 0364 (Requires CDC)

- En TEST, la ventana es de 48 horas
- Después de 48h, SIFEN no permite consultar el lote
- Se debe consultar cada documento individual por CDC

## Próximos Pasos (Opcional)

1. **Background Task**: Implementar polling automático con FastAPI BackgroundTasks
2. **Notificaciones**: Agregar notificaciones cuando un lote cambia de estado
3. **Retry inteligente**: Implementar retry con backoff exponencial para errores transitorios
4. **Dashboard**: Crear dashboard con estadísticas de lotes

