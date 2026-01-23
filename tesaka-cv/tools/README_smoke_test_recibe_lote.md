# Smoke Test para recibe-lote SIFEN

## Descripción

Script de testing end-to-end para validar el servicio `recibe-lote` de SIFEN de forma WSDL-driven.

## Características

- Construye un DE XML mínimo válido según SIFEN v150
- Firma y empaqueta el lote usando el pipeline existente
- Envía a SIFEN usando SOAP 1.2 con headers correctos
- Implementa retries con backoff exponencial + jitter
- Guarda artifacts completos para diagnóstico
- Sale con código no-zero si hay error

## Uso

```bash
# Ejecutar en ambiente test (default)
.venv/bin/python tools/test_smoke_recibe_lote.py

# Ejecutar en producción
.venv/bin/python tools/test_smoke_recibe_lote.py --env prod

# Logging verbose
.venv/bin/python tools/test_smoke_recibe_lote.py --verbose
```

## Variables de entorno

Opcional, para configurar retries:

```bash
export SIFEN_SOAP_MAX_RETRIES=3
export SIFEN_SOAP_BACKOFF_BASE=0.6
export SIFEN_SOAP_BACKOFF_MAX=8.0
```

## Artifacts generados

El script guarda los siguientes archivos en `artifacts/`:

- `smoke_test_de_minimal.xml` - DE mínimo generado
- `smoke_test_lote.xml` - Lote XML firmado
- `smoke_test_metadata_{env}_{timestamp}.json` - Metadata del envío
- `smoke_test_response_{env}_{timestamp}.xml` - Respuesta SOAP
- `smoke_test_route_{env}_{timestamp}.json` - Evidencia de routing

## Validaciones realizadas

1. **Endpoint POST**: Usa exactamente la URL del WSDL (incluyendo `.wsdl`)
2. **Headers SOAP 1.2**: Sin action param para recibe-lote (soapActionRequired=false)
3. **Retries**: Reintentos automáticos en errores de conexión
4. **Respuesta**: Verifica que la respuesta sea parseable y contenga dCodRes

## Ejemplo de salida exitosa

```
=== Paso 1: Creando lote mínimo ===
Construyendo DE mínimo...
DE guardado en: artifacts/smoke_test_de_minimal.xml
Construyendo y firmando lote...
Lote guardado en: artifacts/smoke_test_lote.xml

=== Paso 2: Enviando a SIFEN ===
Enviando lote a SIFEN test...
Endpoint: https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl

=== Paso 3: Guardando artifacts ===
Metadata guardada en: artifacts/smoke_test_metadata_test_20260122_123456.json
Respuesta guardada en: artifacts/smoke_test_response_test_20260122_123456.xml

=== Paso 4: Validando respuesta ===
Código de respuesta SIFEN: OK

=== Resumen ===
✅ Envío exitoso a test
Endpoint: https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl
dId: 202601221234567
```

## Troubleshooting

- Verificar que las credenciales SIFEN estén configuradas
- Revisar artifacts generados para detalles del error
- Usar `--verbose` para logging detallado
