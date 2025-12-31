# Ejemplos de Uso: POST /de/{doc_id}/send

## Envío por Lote (Default)

Envía el documento como lote (siRecepLoteDE). Guarda `dProtConsLote` y consulta automáticamente el estado.

```bash
curl -X POST "http://127.0.0.1:8000/de/1/send?mode=lote" \
  -H "Cookie: session=..." \
  -L
```

O sin especificar `mode` (default es "lote"):

```bash
curl -X POST "http://127.0.0.1:8000/de/1/send" \
  -H "Cookie: session=..." \
  -L
```

**Comportamiento**:
- Construye `rEnvioLote` con ZIP base64
- Llama a `SoapClient.recepcion_lote()`
- Guarda `dProtConsLote` en `sifen_lotes`
- Ejecuta consulta automática del estado del lote
- Respuesta asíncrona (requiere consulta posterior para obtener CDC)

## Envío Directo

Envía el documento directamente (siRecepDE). Respuesta inmediata con CDC si está aprobado.

```bash
curl -X POST "http://127.0.0.1:8000/de/1/send?mode=direct" \
  -H "Cookie: session=..." \
  -L
```

**Comportamiento**:
- Construye `rEnviDe` directamente
- Llama a `SoapClient.recepcion_de()`
- Respuesta inmediata con CDC (si está aprobado)
- No crea registros en `sifen_lotes`
- Útil para pruebas rápidas o cuando se necesita respuesta inmediata

## Validación de Parámetros

Si `mode` tiene un valor inválido, retorna error 400:

```bash
curl -X POST "http://127.0.0.1:8000/de/1/send?mode=invalid" \
  -H "Cookie: session=..." \
  -v
```

**Respuesta esperada**:
```
HTTP/1.1 400 Bad Request
{
  "detail": "Parámetro 'mode' inválido: 'invalid'. Valores permitidos: 'lote', 'direct'"
}
```

