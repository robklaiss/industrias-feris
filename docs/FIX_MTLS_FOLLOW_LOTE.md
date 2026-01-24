# Fix mTLS Follow Lote - Resumen

## Problema
El script `follow_lote.py` en ambiente TEST intentaba convertir certificados PEM (.pem/.key) a formato P12, generando los errores:
- "Extensión inusual para certificado PKCS#12: .pem"
- "Error al convertir certificado P12 a PEM… wrong tag…"

## Causa Raíz
`tools/consulta_lote_de.py` no utilizaba la configuración unificada de mTLS (`get_mtls_config()`) y llamaba directamente a `p12_to_temp_pem_files` sin verificar si estaba en modo PEM.

## Solución Implementada

### 1. Refactorización de `tools/consulta_lote_de.py`
- Se importó `get_mtls_config` desde `app.sifen_client.config`
- Se creó helper `_resolve_mtls()` para centralizar la resolución de certificados
- Se modificaron las funciones:
  - `create_zeep_transport()`: Usa `_resolve_mtls()` y respeta el modo PEM
  - `_http_consulta_lote_manual()`: Recibe `cert_tuple` directamente
  - `call_consulta_lote_raw()`: Usa el helper unificado y limpia temporales solo si es P12
  - `main()`: Usa `get_mtls_config()` para obtener configuración

### 2. Tests de Regresión
- Se creó `tests/test_follow_lote_mtls_regression.py`
- Verifica que `p12_to_temp_pem_files` NO se llame con certificados PEM
- Tests para modo PEM, modo P12 e integración completa

## Comandos de Verificación

### Ejecutar tests de regresión:
```bash
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado
python3 -m pytest tests/test_follow_lote_mtls_regression.py -v
```

### Ejecutar follow_lote en TEST (sin error PKCS12):
```bash
cd tesaka-cv
./tools/sifen_run.sh test follow --once response_con_prot.json
```

## Guardrails Anti-regresión
1. **Siempre usar `get_mtls_config()`** para determinar modo PEM vs P12
2. **Nunca tratar .pem/.key como P12** - verificar extensión antes de convertir
3. **Limpiar archivos temporales solo si son P12 convertidos**
4. **Usar cert tuples** para `session.cert` en lugar de paths individuales

## Archivos Modificados
- `tesaka-cv/tools/consulta_lote_de.py` - Refactorización completa de mTLS
- `tests/test_follow_lote_mtls_regression.py` - Tests de regresión

El fix asegura que `follow_lote` funcione correctamente en ambos ambientes (TEST y PROD) sin intentar conversiones innecesarias de PEM a P12.
