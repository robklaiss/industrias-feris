# Auto-fix 0160 gTotSub

## Configuración de ambientes (TEST vs PROD)

Guía rápida y diferencias clave (endpoints, certificados, riesgos y switch rápido con wrapper):
- **docs/SIFEN_TEST_VS_PROD.md**

Uso recomendado:
- `./tools/sifen_run.sh test ...` para loops / pruebas
- `./tools/sifen_run.sh prod ...` solo cuando ya está validado en TEST


Script automático para corregir errores 0160 de SIFEN relacionados con el orden incorrecto de tags en `gTotSub`.

## Descripción

Cuando SIFEN devuelve un error 0160 con el mensaje:
```
XML malformado: [El elemento esperado es: X en lugar de: dTotIVA]
```

Significa que el tag `X` debe aparecer antes que `dTotIVA` dentro del elemento `gTotSub`. Este script:
1. Envía el XML a SIFEN
2. Consulta el estado del lote
3. Si recibe error 0160 por orden incorrecto, corrige automáticamente el XML
4. Reenvía el XML corregido
5. Repite el proceso hasta que el error sea diferente o se alcance el máximo de iteraciones

## Uso

```bash
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv

python3 tools/autofix_0160_gTotSub.py \
  --env prod \
  --xml "/path/to/xml/file.xml" \
  --artifacts-dir "/path/to/artifacts" \
  --max-iters 20 \
  --start-iteration 1 \
  --bump-doc 1 \
  --dump-http
```

### Parámetros

- `--env`: Ambiente (`prod` o `test`)
- `--xml`: XML inicial a enviar (requerido)
- `--artifacts-dir`: Directorio donde se guardarán los artifacts (requerido)
- `--max-iters`: Máximo de iteraciones (default: 20)
- `--start-iteration`: Número de iteración inicial (default: 1)
- `--bump-doc`: Incrementar número de documento (0 o 1, default: 1)
- `--dump-http`: Mostrar HTTP dump

## Ejemplo completo

```bash
# Ejecutar con artifacts existentes
cd "/Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv" || exit 1

.venv/bin/python tools/autofix_0160_gTotSub.py \
  --env prod \
  --xml "/Users/robinklaiss/Desktop/SIFEN_ARTIFACTS_PROD_20260123_100940/fix_reorder4_20260123_220047.xml" \
  --artifacts-dir "/Users/robinklaiss/Desktop/SIFEN_ARTIFACTS_PROD_20260123_100940" \
  --max-iters 20 \
  --start-iteration 15 \
  --bump-doc 1 \
  --dump-http
```

## Comportamiento

### El script corrige automáticamente:
- **Tags faltantes**: Si el tag esperado no existe, lo crea con valor "0"
- **Tags desordenados**: Si el tag existe pero está después de `dTotIVA`, lo mueve antes
- **Múltiples gTotSub**: Aplica las correcciones a todos los nodos `gTotSub` del XML

### El script se detiene cuando:
- El lote es aprobado (código 0)
- Recibe un rechazo diferente a 0160
- Alcanza el máximo de iteraciones
- El error 0160 no coincide con el patrón esperado

## Archivos generados

Por cada iteración donde se corrige el XML, se genera un archivo:
```
autofix_iter{N}_{TAG}.xml
```
Donde:
- `{N}` es el número de iteración
- `{TAG}` es el tag que se corrigió (ej: dTotOpe, dTotGrav, dTotExe)

## Tests

Para ejecutar los tests unitarios:
```bash
cd tesaka-cv
python3 tools/test_autofix_0160.py
```

## Dependencias

- `lxml`: Para manipulación de XML
- Módulos estándar de Python

## Notas importantes

- El script preserva los namespaces del XML original
- El XML se guarda sin pretty print para mantener la validez de la firma
- Solo se corrigen errores 0160 con el patrón específico de orden de tags
- Los cambios son seguros: solo agrega tags faltantes con valor "0" o reordena tags existentes
