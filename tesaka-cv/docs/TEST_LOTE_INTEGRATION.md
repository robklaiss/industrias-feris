# Cómo Probar la Integración de Consulta Automática de Lotes

## Verificación del Flujo Completo

### Paso 1: Preparar Variables de Entorno

```bash
export SIFEN_EMISOR_RUC="4554737-8"
export SIFEN_SIGN_P12_PATH="/ruta/al/certificado.p12"
export SIFEN_SIGN_P12_PASSWORD="contraseña"
export SIFEN_ENV="test"
```

### Paso 2: Iniciar Servidor

```bash
cd tesaka-cv/
source ../.venv/bin/activate
python -m uvicorn web.main:app --reload --host 127.0.0.1 --port 8000
```

### Paso 3: Enviar un Documento desde la UI

1. Abrir http://127.0.0.1:8000
2. Crear un nuevo DE o usar uno existente
3. Hacer clic en "Enviar a SIFEN" (POST /de/{doc_id}/send)

### Paso 4: Verificar en Base de Datos

```bash
# Verificar que se creó el lote
sqlite3 tesaka.db "SELECT id, env, d_prot_cons_lote, status, last_cod_res_lot, attempts FROM sifen_lotes ORDER BY id DESC LIMIT 5;"

# Verificar que se actualizó last_cod_res_lot
sqlite3 tesaka.db "SELECT id, d_prot_cons_lote, last_cod_res_lot, last_msg_res_lot, status, attempts, last_checked_at FROM sifen_lotes WHERE last_cod_res_lot IS NOT NULL ORDER BY id DESC LIMIT 1;"
```

### Paso 5: Verificar en la UI

1. Abrir http://127.0.0.1:8000/admin/sifen/lotes
2. Verificar que aparece el lote con:
   - `d_prot_cons_lote` guardado
   - `status` actualizado (processing, done, requires_cdc, o error)
   - `last_cod_res_lot` y `last_msg_res_lot` poblados
   - `attempts` > 0
   - `last_checked_at` con timestamp

3. Hacer clic en el lote para ver detalles
4. Verificar que el XML de respuesta está guardado

## Checklist de Verificación

- [ ] Se crea el lote en `sifen_lotes` cuando se recibe `dProtConsLote`
- [ ] `d_prot_cons_lote` está guardado (solo dígitos)
- [ ] `de_document_id` está relacionado con el documento
- [ ] `status` inicial es `pending`
- [ ] La consulta async se ejecuta automáticamente
- [ ] `last_cod_res_lot` se actualiza después de la consulta
- [ ] `last_msg_res_lot` se actualiza después de la consulta
- [ ] `last_response_xml` contiene el XML completo
- [ ] `status` se actualiza según el código (0361→processing, 0362→done, 0364→requires_cdc)
- [ ] `attempts` se incrementa
- [ ] `last_checked_at` tiene un timestamp

## Nota sobre el Cambio de Flujo

**IMPORTANTE**: El endpoint `POST /de/{doc_id}/send` ahora usa `recepcion_lote` (envío por lote) en lugar de `recepcion_de` (envío individual).

**Razón del cambio**: Para obtener `dProtConsLote` y poder consultar el estado del lote automáticamente, es necesario usar el servicio de lotes (`siRecepLoteDE`).

**Impacto**:
- ✅ Se obtiene `dProtConsLote` para consulta posterior
- ✅ Se puede consultar el estado del lote automáticamente
- ⚠️ La respuesta inmediata no incluye el CDC del documento (se obtiene consultando el lote)

Si necesitas mantener el flujo anterior (envío individual con respuesta inmediata), se puede agregar un parámetro o endpoint alternativo.

