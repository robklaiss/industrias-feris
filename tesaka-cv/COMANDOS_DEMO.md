# SIFEN FastAPI - Comandos de Demo (MODO TEST)

## 1. Levantar el servidor
```bash
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## 2. Emitir una factura (POST)
```bash
curl -X POST http://127.0.0.1:8000/api/v1/emitir \
  -H "Content-Type: application/json" \
  -d '{
    "ruc": "04554737",
    "timbrado": "12560693",
    "establecimiento": "001",
    "punto_expedicion": "001",
    "numero_documento": "0000001",
    "tipo_documento": "1",
    "fecha": "2026-01-24",
    "hora": "22:30:00",
    "csc": "TEST123456789012345678901234567890"
  }'
```

## 3. Consultar estado (follow) - usando dId
```bash
curl "http://127.0.0.1:8000/api/v1/follow?did=0455473720260124_223000"
```

## 4. Consultar estado - usando protocolo
```bash
curl "http://127.0.0.1:8000/api/v1/follow?prot=123456789012345"
```

## 5. Listar artifacts latest
```bash
curl http://127.0.0.1:8000/api/v1/artifacts/latest
```

## 6. Ver metadata de un dId específico
```bash
curl http://127.0.0.1:8000/api/v1/artifacts/04554737-820260124_222451/meta
```

## 7. Descargar DE XML
```bash
curl -o DE.xml http://127.0.0.1:8000/api/v1/artifacts/04554737-820260124_222451/de
```

## 8. Interfaz web (opcional)
- Emitir: http://127.0.0.1:8000/ui/emitir
- Seguimiento: http://127.0.0.1:8000/ui/seguimiento
- Artifacts: http://127.0.0.1:8000/artifacts

## Fixes aplicados:
1. ✅ Archivo sifen_prod.env renombrado a .DISABLED
2. ✅ Guardrail central que fuerza env=test y prohíbe prod
3. ✅ Validación de dId actualizada para permitir formato con guiones
4. ✅ Reintentos para WSDL vacío en follow
5. ✅ Sanitizado de prefijos ds: antes de enviar

## Verificación anti-PROD:
```bash
rg -n "sifen\.set\.gov\.py|sifen-prod|SIFEN_.*PROD|config/sifen_prod\.env|\benv['\"]?prod|ENV=prod|\"prod\"|'prod'" -S app tools config run_server.py README*.md || echo "✅ Sin referencias a PROD"
```
