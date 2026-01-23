# PIPELINE_CONTRACT Improvements Proposal

## Current Compliance Status: 85%

The current implementation follows most of the PIPELINE_CONTRACT requirements but the contract itself needs enhancements for 100% clarity and compliance.

## Missing Sections to Add

### 7) Exit Codes Table (NEW)

```markdown
## 7) Códigos de salida estándar (NO negociables)

| Exit Code | Significado                | Cuándo ocurre                                    |
|-----------|----------------------------|--------------------------------------------------|
| 0         | Éxito                      | DE concluido (0362) sin 0160                     |
| 1         | Error de conexión          | HTTP error, timeout, malformación SOAP           |
| 2         | Error de configuración     | Archivos faltantes, XML inválido, env vars       |
| 3         | Error de artifacts         | No se encontraron response/consulta JSON         |
| 4         | Error en fix aplicado      | Falló aplicar patch XML                          |
| 5         | 0160 no reconocido         | Mensaje 0160 pero sin patrón reconocible         |
| 6         | Max iteraciones alcanzadas | Se alcanzó --max-iter sin resolver 0160          |
```

### 8) Artifact Naming Convention (ENHANCED)

```markdown
## 8) Nomenclatura de artifacts por iteración (versión 2)

Por cada iteración `N`:
- `response_recepcion_N.json` - Respuesta del envío
- `consulta_lote_N.json` - Respuesta de la consulta
- `xml_input_N.xml` - XML usado como input
- `xml_output_N.xml` - XML generado si hubo fix (solo si aplica)
- `fix_summary_N.md` - Resumen de fixes aplicados (NUEVO)

Reglas:
- Siempre incluir número de iteración en el nombre
- Mantener últimos 5 iteraciones + iteración final
- La iteración final siempre se guarda sin importar el resultado
```

### 9) Success Criteria (NEW)

```markdown
## 9) Criterios de éxito y fin de flujo (NO negociables)

### Estados de éxito (exit code 0):
- DE concluido (0362) con dCodRes en: (0001, 0002, 0003)
- DE concluido (0362) con dCodRes en: (0101, 0102, 0103) [Aprobado]
- DE concluido (0362) con dCodRes en: (0201, 0202) [Aprobado con obs]

### Estados de error de negocio (exit code 0 pero informar):
- DE concluido (0362) con dCodRes en: (1264) [RUC no habilitado]
- DE concluido (0362) con dCodRes en: (0301) [No encolado]

### Estados de error técnico (exit code 1-6):
- Cualquier HTTP error diferente a 200
- Timeout en cualquier paso
- XML mal formado (0160 persistente)
- Error interno de SIFEN (05xx, 09xx)
```

### 10) Polling Timeout Behavior (ENHANCED)

```markdown
## 10) Comportamiento al alcanzar timeouts

### Si se alcanza --max-poll en estado 0361:
- Continuar con siguiente iteración del loop (no es error)
- No consumir iteración principal (internal polling)
- Loggear: "Timeout en polling, continuando loop..."

### Si se alcanza --max-iter:
- Guardar estado final en `final_state_N.json`
- Exit code 6 (como implementa actualmente)
- Preservar todos los XMLs intermedios para análisis
- Generar reporte de todos los intentos realizados
```

## Implementation Changes Needed

### 1. Add fix_summary_N.md generation

In `auto_fix_0160_loop.py`, after line 1029:

```python
# Generate fix summary markdown
fix_summary_file = artifacts_dir / f"fix_summary_{i}.md"
fix_summary_content = f"""# Fix Summary - Iteration {i}

## Applied Fixes:
{chr(10).join(f"- {fx}" for fx in fixes_applied)}

## Files:
- Input: {current_xml}
- Output: {out_xml}

## Status:
- dCodRes: {st.de_cod}
- Message: {st.de_msg}
"""
fix_summary_file.write_text(fix_summary_content, encoding="utf-8")
```

### 2. Include iteration number in all artifacts

Modify `send_sirecepde.py` to accept optional iteration parameter:

```python
parser.add_argument(
    "--iteration",
    type=int,
    default=None,
    help="Número de iteración (para naming de artifacts)"
)
```

And update timestamp generation to include iteration:

```python
if args.iteration is not None:
    timestamp = f"{timestamp}_iter{args.iterition}"
```

### 3. Add explicit success validation

Create `validate_success_criteria.py`:

```python
def is_success_status(dCodRes):
    success_codes = ["0001", "0002", "0003", "0101", "0102", "0103", "0201", "0202"]
    return dCodRes in success_codes

def is_business_error(dCodRes):
    business_codes = ["1264", "0301"]
    return dCodRes in business_codes
```

## Contract Versioning

Add version tracking to PIPELINE_CONTRACT:

```markdown
---
Version: 2.0
Date: 2026-01-23
Last Updated: [name]
Changelog:
  - v2.0: Added exit codes, success criteria, artifact naming v2
  - v1.0: Initial version
---
```

## Benefits of These Improvements

1. **Clarity absoluta** sobre cuándo detenerse y qué significa éxito
2. **Trazabilidad completa** con artifacts numerados por iteración
3. **Debugging mejorado** con fix summaries por iteración
4. **Automatización fácil** con códigos de salida estandarizados
5. **Mantenimiento simple** con contrato versionado

## Priority Order

1. **High**: Add exit codes table and success criteria
2. **Medium**: Implement fix_summary_N.md generation
3. **Medium**: Add iteration numbers to all artifacts
4. **Low**: Add contract versioning

These changes will bring the contract to 100% compliance and make the pipeline more maintainable and debuggable.
