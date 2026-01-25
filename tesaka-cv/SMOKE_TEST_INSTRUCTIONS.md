# Smoke Test para Emitir Facturas

## Ejecución

### 1. Iniciar el servidor (Modo TEST)
```bash
cd tesaka-cv
SIFEN_ENV=test python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Ejecutar smoke test
```bash
cd tesaka-cv
python3 -m tools.emit_smoke.py --ruc 4554737-8 --timbrado 12345678
```

## Salida esperada
```
DID=455473720260124_123456
OUT=/tmp/DE_TAL_CUAL_455473720260124_123456.xml
Firma: OK
RUC: OK
```

## Verificaciones
- El XML descargado NO debe contener `rsa-sha1`, `xmldsig#sha1` ni `dGhpcy`
- El campo `<dRucEm>` debe aparecer sin cero inicial: `<dRucEm>4554737</dRucEm>`
