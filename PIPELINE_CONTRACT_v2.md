# PIPELINE_CONTRACT — SIFEN (tesaka-cv) v2.0

---
Version: 2.0
Date: 2026-01-23
Last Updated: Cascade AI Assistant
Changelog:
  - v2.0: Added exit codes table, success criteria, artifact naming v2, timeout behavior
  - v1.0: Initial version
---

Este archivo es la **fuente de verdad** del pipeline.  
**Todo cambio** en scripts (tools/*, app/*, tests/*) debe respetar este contrato.  
Si un agente propone cambios, debe **citar la sección** de este contrato que está cumpliendo.

---

## 0) Principios de estabilidad (NO negociables)

1) **No romper compatibilidad**: no cambiar defaults, flags, nombres de archivos, ni rutas de artefactos sin actualizar este contrato.
2) **Trazabilidad total**: cada iteración debe producir artefactos con nombres únicos o claramente versionados.
3) **Nunca borrar nodos XML existentes**: solo insertar o reordenar dentro del mismo parent.
4) **No duplicar elementos**: si existe, no insertar.
5) **Namespaces**: preservar namespace original de cada parent.
6) **Valores por defecto seguros**: usar `"0"` cuando corresponda (nunca vacío).

---

## 1) Variables canónicas (siempre iguales)

> Ajustá `ARTDIR` y `XML_IN`, pero **la estructura de comandos** debe ser la misma.

```bash
cd "/Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv" || exit 1
ARTDIR="/Users/robinklaiss/Desktop/SIFEN_ARTIFACTS_PROD_YYYYMMDD_HHMMSS"
XML_IN="/path/al/input.xml"
```

---

## 2) Paso A — Envío (tools/send_sirecepde.py)

**Comando canónico:**
```bash
.venv/bin/python tools/send_sirecepde.py \
  --env prod \
  --xml "$XML_IN" \
  --bump-doc 1 \
  --dump-http \
  --artifacts-dir "$ARTDIR"
```

**Salidas esperadas en `ARTDIR`:**
- `response_recepcion_*.json` (última respuesta)
- `xml_bumped_*.xml` (si bump-doc está activo)
- dumps HTTP si están habilitados

**Reglas:**
- `--bump-doc 1` se usa para evitar colisiones mientras iteramos.
- `--artifacts-dir` siempre apunta al mismo `ARTDIR` de la corrida.

---

## 3) Paso B — Consulta lote (tools/follow_lote.py)

**Comando canónico:**
```bash
LAST_RESP="$(ls -1t "$ARTDIR"/response_recepcion_*.json | head -n 1)"
.venv/bin/python tools/follow_lote.py \
  --env prod \
  --artifacts-dir "$ARTDIR" \
  --once "$LAST_RESP"
```

**Interpretación canónica:**
- `0361` = "en procesamiento" → **NO es éxito** ni fracaso. Se debe **seguir consultando**.
- `0362` = "concluido" → mirar el DE y su `dCodRes/dMsgRes`.

---

## 4) Paso C — Auto-fix loop (tools/auto_fix_0160_loop.py)

**Objetivo:** iterar automáticamente hasta eliminar `0160` o agotar iteraciones.

**Comando canónico:**
```bash
.venv/bin/python tools/auto_fix_0160_loop.py \
  --env prod \
  --artifacts-dir "$ARTDIR" \
  --xml "$XML_IN" \
  --max-iter 10 \
  --poll-every 3 \
  --max-poll 40
```

### 4.1 Comportamiento requerido del loop

**Dentro de una iteración:**
1) Enviar (Paso A)
2) Consultar (Paso B)
3) Si lote está `0361` → **POLL interno** (no consumir iteración)
4) Cuando pase a `0362`:
   - Si DE trae `0160` con patrón "esperado en lugar de":
     - aplicar fix: **insertar esperado antes del encontrado**
     - reordenar `gTotSub` a orden canónico (sin borrar)
     - generar nuevo XML de salida trazable
     - continuar a la siguiente iteración
   - Si DE NO trae `0160`:
     - **STOP exitoso** (no imprimir como error)
     - devolver "no 0160" + estado final del DE

### 4.2 STOP correcto (esto es clave)

El script SOLO puede frenar cuando:
- El DE está concluido (`0362`) y:
  - **no hay 0160** en el DE (éxito), o
  - hay un error distinto a 0160 (debe reportarlo explícitamente)

**Nunca** debe hacer STOP por "no veo 0160" si el lote está `0361` (porque todavía no hay DE).  
En `0361`, debe seguir en modo poll.

---

## 5) Artefactos mínimos por iteración (obligatorio)

Por cada iteración `N`:
- `xml_input_N.xml` - XML input usado
- `xml_output_N.xml` (si hubo fix)
- `response_recepcion_N.json` 
- `consulta_lote_N.json` 
- `fix_summary_N.md` - Resumen de fixes aplicados

**Reglas de nomenclatura:**
- Siempre incluir número de iteración `N` en el nombre
- Mantener últimas 5 iteraciones + iteración final
- La iteración final siempre se guarda sin importar el resultado

---

## 6) Orden canónico gTotSub (si aplica)

El canonical re-order se aplica **solo dentro de gTotSub** y respetando:
- no borrar
- no duplicar
- preservar namespace
- valores default seguros

```python
canonical_order = [
    "dSubExe", "dSubExo", "dSub5", "dSub10", "dTotOpe", 
    "dTotDesc", "dTotDescGlotem", "dTotAntItem", "dTotAnt",
    "dPorcDescTotal", "dTotIVA", "dTotGralOp", "dTotGrav", "dTotExe"
]
```

> **Nota:** completar/confirmar el orden exacto final cuando esté validado por casos reales.

---

## 7) Códigos de salida estándar (NO negociables) [NUEVO v2.0]

| Exit Code | Significado                | Cuándo ocurre                                    |
|-----------|----------------------------|--------------------------------------------------|
| 0         | Éxito                      | DE concluido (0362) sin 0160                     |
| 1         | Error de conexión          | HTTP error, timeout, malformación SOAP           |
| 2         | Error de configuración     | Archivos faltantes, XML inválido, env vars       |
| 3         | Error de artifacts         | No se encontraron response/consulta JSON         |
| 4         | Error en fix aplicado      | Falló aplicar patch XML                          |
| 5         | 0160 no reconocido         | Mensaje 0160 pero sin patrón reconocible         |
| 6         | Max iteraciones alcanzadas | Se alcanzó --max-iter sin resolver 0160          |

---

## 8) Criterios de éxito y fin de flujo (NO negociables) [NUEVO v2.0]

### Estados de éxito (exit code 0):
- DE concluido (0362) con dCodRes en: (0001, 0002, 0003)
- DE concluido (0362) con dCodRes en: (0101, 0102, 0103) [Aprobado]
- DE concluido (0362) con dCodRes en: (0201, 0202) [Aprobado con obs]

### Estados de error de negocio (exit code 0 pero informar):
- DE concluido (0362) con dCodRes en: (1264) [RUC no habilitado]
- DE concluido (0362) con dCodRes en: (0301) [No encolado]

### Estados de procesamiento (continuar polling):
- Lote en estado (0361) [En procesamiento]
- Lote en estado (0300) [Encolado]

### Estados de error técnico (exit code 1-6):
- Cualquier HTTP error diferente a 200
- Timeout en cualquier paso
- XML mal formado persistente (0160)
- Error interno de SIFEN (05xx, 09xx)

---

## 9) Comportamiento al alcanzar timeouts [NUEVO v2.0]

### Si se alcanza --max-poll en estado 0361:
- Continuar con siguiente iteración del loop (no es error)
- No consumir iteración principal (internal polling)
- Loggear: "Timeout en polling, continuando loop..."

### Si se alcanza --max-iter:
- Guardar estado final en `final_state_N.json`
- Exit code 6 (como implementa actualmente)
- Preservar todos los XMLs intermedios para análisis
- Generar reporte de todos los intentos realizados

---

## 10) Validación de cumplimiento [NUEVO v2.0]

Para verificar que una implementación cumple con este contrato:

```bash
# 1. Verificar estructura de comandos
grep -E "send_sirecepde.*--env.*--xml.*--bump-doc.*--dump-http.*--artifacts-dir" scripts/pipeline.sh

# 2. Verificar códigos de salida
python tools/validate_success_criteria.py artifacts/response_recepcion_1.json; echo $?

# 3. Verificar artifacts por iteración
ls -la artifacts/ | grep -E "(xml_input|xml_output|response_recepcion|consulta_lote|fix_summary)_[0-9]+\."

# 4. Verificar orden gTotSub
python -c "
from auto_fix_0160_loop import canonical_gTotSub_order
print('Orden canónico gTotSub:', [
    'dSubExe', 'dSubExo', 'dSub5', 'dSub10', 'dTotOpe', 
    'dTotDesc', 'dTotDescGlotem', 'dTotAntItem', 'dTotAnt',
    'dPorcDescTotal', 'dTotIVA', 'dTotGralOp', 'dTotGrav', 'dTotExe'
])
"
```

---

## 11) Herramientas de soporte [NUEVO v2.0]

- `tools/validate_success_criteria.py` - Valida códigos de respuesta SIFEN
- `tools/add_fix_summary.py` - Agrega generación de fix summaries
- `tools/soap_picker.py` - Selector unificado de archivos SOAP
- `tests/test_pipeline_contract.py` - Tests de cumplimiento del contrato
