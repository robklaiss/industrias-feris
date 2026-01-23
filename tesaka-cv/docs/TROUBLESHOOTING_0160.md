# TROUBLESHOOTING 0160

Guía rápida para diagnosticar y resolver errores 0160 de SIFEN.

## Cómo correr el loop

```bash
cd tesaka-cv
../scripts/run.sh -m tools.auto_fix_0160_loop \
  --env prod \
  --xml artifacts/last_lote.xml \
  --artifacts-dir artifacts/loop_$(date +%Y%m%d_%H%M%S) \
  --max-iter 10 \
  --poll-every 3 \
  --max-poll 40
```

## Interpretar códigos de respuesta

| Código | Significado | Acción |
|--------|-------------|--------|
| 0361 | Procesamiento OK | ✅ Documento aceptado |
| 0362 | Rechazo | ❌ Corregir errores específicos |
| 0160 | XML Mal Formado | 🔍 Verificar reglas anti-regresión |
| 0301 | Firma inválida | 🔍 Verificar certificado y firma |
| 0126 | Error temporal | ⏳ Reintentar más tarde |

## Dónde mirar artifacts

Los artifacts se guardan en el directorio especificado con `--artifacts-dir`:

```
artifacts/loop_20260123_143022/
├── soap_last_request_SENT.xml     # SOAP enviado a SIFEN
├── soap_last_response_RECEIVED.xml # Respuesta de SIFEN
├── _last_sent_lote.xml            # XML extraído del ZIP enviado
├── _stage_*.xml                   # XMLs intermedios del proceso
├── fix_summary_N.md               # Resumen de fixes aplicados
└── route_probe_*.json             # Debug de routing
```

**Archivos clave para 0160:**
- `soap_last_request_SENT.xml` - El SOAP tal cual fue transmitido
- `_last_sent_lote.xml` - El XML dentro del ZIP (línea 4 del SOAP)

## Comandos de verificación rápida

```bash
# Verificar rDE sin Id (prohibido)
rg -n "<rDE\\b[^>]*\\bId=" artifacts/_last_sent_lote.xml || echo "✅ OK"

# Verificar sin microsegundos en fechas
rg -n "T\\d\\d:\\d\\d:\\d\\d\\." artifacts/_last_sent_lote.xml || echo "✅ OK"

# Verificar QR con ? (no /qrnVersion=)
rg "/qrnVersion=" artifacts/_last_sent_lote.xml && echo "❌ QR mal formado" || echo "✅ QR OK"

# Verificar schemaLocation con 2 tokens
rg 'xsi:schemaLocation="([^"]+) ([^"]+)"' artifacts/_last_sent_lote.xml
```

## Cómo adjuntar a soporte

Cuando necesites abrir un ticket con soporte SIFEN:

1. **XML tal cual transmitido:**
   ```bash
   # Extraer el XML del SOAP enviado
   unzip -p artifacts/soap_last_request_SENT.xml xDE > xde.zip
   unzip -p xde.zip lote.xml > xml_para_soporte.xml
   ```

2. **XML de rechazo (si aplica):**
   - Guardar la respuesta completa: `soap_last_response_RECEIVED.xml`
   - Capturar el código y mensaje exacto

3. **Información adicional:**
   - Ambiente (prod/test)
   - Número de RUC
   - Fecha y hora de envío
   - Número de lote (dId)

## Errores comunes y soluciones

### "XML Mal Formado" (0160)
- Ejecutar preflight: `python3 tools/preflight_validate_xml.py --xml artifacts/_last_sent_lote.xml`
- Verificar todas las reglas en `docs/aprendizajes/anti-regresion.md`

### "Firma inválida" (0301)
- Verificar certificado: `openssl pkcs12 -in cert.p12 -info`
- Re-firmar con `--force-resign`

### "Procesando" persistente
- Aumentar `--max-poll` para dar más tiempo
- Verificar con `tools/follow_lote.py` manualmente

## Tips adicionales

- Usa `--env test` para pruebas antes de prod
- El artifacts directory debe existir antes de correr el loop
- Para debug detallado, usa `SIFEN_DEBUG_SOAP=1`
- Los fix summaries son tu mejor amigo para entender qué cambió entre iteraciones
