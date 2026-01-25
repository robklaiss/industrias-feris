# API SIFEN - Emisión de Facturas Electrónicas (MVP Web)

Este módulo expone endpoints web (FastAPI) para **emitir** documentos a SIFEN y **consultar** el estado del lote.

> Proyecto: `tesaka-cv` dentro del repo  
> `/Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv` 

---

## Endpoints

### 1) POST `/api/v1/emitir` 
Emite un documento (genera XML, firma, envía a SIFEN) y devuelve un identificador para seguimiento.

**Request (ejemplo mínimo):**
```json
{
  "env": "test"
}
```

> Nota: el payload real depende de la implementación en `app/routes_emit.py`.
> Si querés un ejemplo "completo" de factura, usar el JSON que ya usa tu UI `/ui/emitir` 
> o el que generes desde tu flujo actual de datos.

**Response (ejemplo):**
```json
{
  "ok": true,
  "dId": "202601241923444",
  "cdc": "0104554737800100....",
  "dProtConsLote": "47353168697838706",
  "status": "PENDIENTE",
  "artifacts_dir": "artifacts/..."
}
```

---

### 2) GET `/api/v1/follow` 
Consulta el estado del lote por `did` o por `prot` (`dProtConsLote`).

**Ejemplos:**
```
GET /api/v1/follow?did=202601241923444
GET /api/v1/follow?prot=47353168697838706
```

**Response (ejemplo):**
```json
{
  "dProtConsLote": "47353168697838706",
  "dEstRes": "Rechazado",
  "dCodRes": "0160",
  "dMsgRes": "XML Mal Formado."
}
```

---

### 3) GET `/ui/emitir` 
UI mínima para probar emisión (form + textarea JSON).

### 4) GET `/ui/seguimiento` 
UI mínima para consultar estado (follow).

---

## Cómo iniciar el servidor (dev)

Desde `tesaka-cv`:

```bash
cd "/Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv" || exit 1
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Luego:
- UI: `http://127.0.0.1:8000/ui/emitir` 
- API: `http://127.0.0.1:8000/api/v1/emitir` 

---

## Cómo probar sin inundar la terminal

### Emitir con curl
```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/emitir"   -H "Content-Type: application/json"   -d '{"env":"test"}' | .venv/bin/python -m json.tool
```

### Follow con curl
```bash
curl -sS "http://127.0.0.1:8000/api/v1/follow?prot=47353168697838706" | .venv/bin/python -m json.tool
```

---

## Artifacts / Evidencia

El sistema guarda artifacts para auditoría y debugging (XML generado, SOAP request/response, JSON de respuesta, etc.).
La ruta exacta depende del flujo, pero normalmente se guarda bajo:
- `tesaka-cv/artifacts/` 
- o un `ARTIFACTS_DIR` configurado en variables/args de tooling.

Si aparece un **0160**, siempre necesitas:
- **XML tal cual transmitido** (el `sent_lote_*.xml` correspondiente a ese `dId`)
- **XML de respuesta / rechazo** (SOAP / consulta lote)

### Reporte compacto (0160)
Si tenés un folder externo de artifacts (ej. Desktop), podés correr tu extractor:

```bash
cd "/Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv" || exit 1
bash tools/run_agent_extract_0160_artifacts.sh "/Users/robinklaiss/Desktop/SIFEN_ARTIFACTS_TEST_20260123"
```

Ese runner genera un `agent_report_0160_*.txt` sin dumpear XML completo en stdout.

---

## Configuración (env files)

El entorno se carga desde archivos `config/sifen_*.env` (por ejemplo `config/sifen_test.env`).
Verifica y edita los paths de certificados y endpoints ahí.

Archivos relevantes:
- `tesaka-cv/config/sifen_test.env` 
- `tesaka-cv/config/sifen_prod.env` (si aplica)

---

## Archivos clave del MVP

- `app/main.py` → inicializa FastAPI y registra rutas
- `app/routes_emit.py` → `/api/v1/emitir`, `/api/v1/follow`, `/ui/emitir`, `/ui/seguimiento` 
- `app/routes_artifacts.py` → descargas de artifacts por dId
- `tools/*` → scripts y herramientas de diagnóstico (0160, búsqueda por dId, etc.)

---

## Estado / TODO (para el lunes)

- [ ] Confirmar que el `sent_lote_*.xml` correspondiente al `dId` se guarda siempre en artifacts (por dId).
- [ ] Alinear `gTotSub` del XML transmitido a lo que exige SIFEN (evitar 0160).
- [ ] End-to-end: emitir desde UI → obtener `dProtConsLote` → follow → Aceptado.
