# Auto-Fix 0160 Loop - Mejoras Implementadas

## Objetivo
Robustecer `tools/auto_fix_0160_loop.py` para que pueda arreglar automáticamente errores 0160 del tipo:
```
XML malformado: El elemento esperado es: <EXPECTED> en lugar de: <FOUND>
```

## Cambios Realizados

### 1. Función `parse_0160_expected_found(msg)`
- Parsea el mensaje de error 0160 usando regex
- Extrae los elementos EXPECTED y FOUND
- Retorna tupla `(expected, found)` o `None` si no hay patrón

```python
pattern = r"El elemento esperado es:\s*(\w+)\s*en lugar de:\s*(\w+)"
```

### 2. Función `ensure_expected_before_found(xml_path, expected, found)`
- Inserta el elemento EXPECTED antes de FOUND en el mismo parent
- **Reglas de seguridad implementadas:**
  - ✅ Nunca borra nodos existentes
  - ✅ Solo inserta faltantes o reordena dentro del mismo parent
  - ✅ Mantiene namespaces del parent
  - ✅ No duplica si el elemento ya existe
  - ✅ Valor por defecto seguro: "0" para campos dTot*/dPorc*

- **Genera archivos con naming:** `loopfix_<n>_<EXPECTED>.xml`
- **Retorna:** `(new_path, changed_bool, debug_dict)`

### 3. Función `canonical_gTotSub_order(doc)`
- Reordena elementos de gTotSub en orden canónico
- **Orden canónico implementado:**
```python
[
    "dSubExe", "dSubExo", "dSub5", "dSub10",
    "dTotOpe", "dTotDesc", "dTotDescGlotem",
    "dTotAntItem", "dTotAnt", "dPorcDescTotal",
    "dTotIVA", "dTotGralOp", "dTotGrav", "dTotExe"
]
```
- Preserva elementos desconocidos al final
- Crea elementos faltantes con valor "0"

### 4. Integración en el Loop Principal
- **Nuevo flujo:**
  1. Ejecutar `send_sirecepde.py`
  2. Ejecutar `follow_lote.py --once`
  3. Si viene 0160 con patrón esperado/en lugar de:
     - Aplicar `ensure_expected_before_found()`
     - Continuar siguiente iteración
  4. Si viene 0160 pero no matchea patrón:
     - Aplicar fixes existentes (dDesUniMed, gTotSub, etc.)
  5. Cortar si ya no es 0160

## Ejemplo de Uso

### Ejecución del Loop
```bash
cd tesaka-cv
python3 -m tools.auto_fix_0160_loop \
    --env prod \
    --artifacts-dir artifacts \
    --xml mi_lote.xml \
    --max-iter 10
```

### Demostración
```bash
cd tesaka-cv
python3 tools/demo_0160_loop_fix.py
```

## Tests
```bash
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado
python3 tests/test_auto_fix_0160_loop.py
```

## Secuencia de Ejemplo

El loop puede atravesar automáticamente la cadena:
```
dTotDesc → dTotDescGlotem → dTotAntItem → dTotAnt → dPorcDescTotal → dSubExe → dSubExo
```

Sin intervención manual, generando archivos:
```
lote_loopfix_1_dTotDesc.xml
lote_loopfix_2_dTotDescGlotem.xml
lote_loopfix_3_dTotAntItem.xml
lote_loopfix_4_dTotAnt.xml
lote_loopfix_5_dPorcDescTotal.xml
lote_loopfix_6_dSubExe.xml
lote_loopfix_7_dSubExo.xml
```

## Beneficios

1. **Automatización completa** de errores 0160 de orden
2. **Seguridad garantizada** con reglas estrictas
3. **Traceabilidad** con archivos nombrados por iteración
4. **Integración** con flujo existente
5. **Extensibilidad** para nuevos patrones de error

## Consideraciones

- El loop solo modifica estructura, no valores (excepto defaults seguros)
- Siempre preserva la firma XML existente
- Se detiene si encuentra un error 0160 no reconocido
- Respeta el `--max-iter` para evitar loops infinitos
