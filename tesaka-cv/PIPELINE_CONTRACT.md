# PIPELINE_CONTRACT (tesaka-cv)
Objetivo: mantener el pipeline SIFEN estable, trazable y anti-regresión.

## 1) Comandos canónicos (NO cambiar flags sin actualizar este contrato)
### 1.1 Envío
.venv/bin/python tools/send_sirecepde.py --env <prod|test> --xml "<XML_IN>" --bump-doc 1 --dump-http --artifacts-dir "<ARTDIR>"

### 1.2 Seguimiento de lote
.venv/bin/python tools/follow_lote.py --env <prod|test> --artifacts-dir "<ARTDIR>" --once "<response_recepcion_*.json>"

### 1.3 Loop auto-fix 0160 (end-to-end)
.venv/bin/python tools/auto_fix_0160_loop.py --env <prod|test> --artifacts-dir "<ARTDIR>" --xml "<XML_IN>" --max-iter <N> --poll-every <secs> --max-poll <N>

## 2) Reglas de seguridad (hard rules)
- Nunca borrar nodos existentes.
- Solo insertar/reordenar dentro del mismo parent.
- Mantener namespaces.
- No duplicar elementos.
- Valores por defecto seguros: "0" cuando aplique.

## 3) Polling de estados (consulta-lote)
- 0361 + "en procesamiento": entrar en polling interno (no consume iteración).
- 0362: procesamiento concluido -> leer estado por DE.
- Si tras max-poll sigue 0361, continuar con siguiente iteración.

## 4) Criterio de fix automático (0160 esperado/en lugar de)
Cuando SIFEN responde 0160 con patrón:
"El elemento esperado es: X en lugar de: Y"
-> insertar X antes de Y (en el mismo parent), respetando orden canónico.

## 5) Orden canónico gTotSub (si aplica)
El loop debe ordenar gTotSub según secuencia canónica del proyecto, sin borrar nodos.

## 6) Artefactos mínimos (trazabilidad)
En <ARTDIR> se deben guardar (por iteración o por ejecución):
- xml_bumped_*.xml
- response_recepcion_*.json
- consulta_lote_*.json (cuando se consulta)
- dumps HTTP si --dump-http está activo (si existen)

## 7) Anti-regresión (fuente única adicional)
Las reglas aprendidas/anti-regresión del proyecto viven en:
docs/aprendizajes/anti-regresion.md
Este contrato no lo reemplaza: lo complementa.

