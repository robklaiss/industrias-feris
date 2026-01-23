# SIFEN Facturación Electrónica - Pipeline Anti-regresión

Pipeline robusto para envío de documentos a SIFEN con protección contra regresiones.

## Verificación rápida

Ejecuta este comando para validar todo el pipeline:
```bash
.venv/bin/python validate_pipeline_compliance.py --verbose && .venv/bin/python -m pytest -q
```

## Estructura del proyecto

```
├── tesaka-cv/                    # Módulo principal
│   ├── tools/                    # Scripts de operación
│   │   ├── auto_fix_0160_loop.py # Loop de auto-corrección
│   │   ├── send_sirecepde.py     # Envío a SIFEN
│   │   ├── follow_lote.py        # Seguimiento de lote
│   │   ├── preflight_validate_xml.py # Validación pre-envío
│   │   └── soap_picker.py        # Selector unificado de SOAP
│   └── docs/                     # Documentación
│       ├── TROUBLESHOOTING_0160.md # Guía de troubleshooting
│       └── aprendizajes/         # Lecciones aprendidas
├── tests/                        # Tests anti-regresión
└── validate_pipeline_compliance.py # Validador de compliance
```

## Flujo básico

1. **Validar XML**: `python3 tools/preflight_validate_xml.py --xml mi_lote.xml`
2. **Enviar a SIFEN**: `python3 tools/send_sirecepde.py --env prod --xml mi_lote.xml`
3. **Loop auto-fix**: `python3 tools/auto_fix_0160_loop.py --env prod --xml mi_lote.xml --artifacts-dir artifacts/run1`

## Documentación importante

- [PIPELINE_CONTRACT.md](tesaka-cv/PIPELINE_CONTRACT.md) - Contrato del pipeline v1
- [PIPELINE_CONTRACT_v2.md](tesaka-cv/PIPELINE_CONTRACT_v2.md) - Contrato del pipeline v2
- [TROUBLESHOOTING_0160.md](tesaka-cv/docs/TROUBLESHOOTING_0160.md) - Guía de resolución de 0160
- [anti-regresion.md](tesaka-cv/docs/aprendizajes/anti-regresion.md) - Reglas anti-regresión

## Tests anti-regresión

Los tests validan las reglas críticas para evitar error 0160:
```bash
.venv/bin/python -m pytest tests/test_antiregression_xml_rules.py -v
```

## Reglas críticas (anti-regresión)

1. **rDE sin atributo Id** - Prohibido en el XML final
2. **dVerFor primero** - Debe ser el primer hijo de rDE con valor "150"
3. **Signature namespace** - Usar xmlns="http://www.w3.org/2000/09/xmldsig#"
4. **dCodSeg de 9 dígitos** - Exactamente 9 dígitos numéricos
5. **QR con ?nVersion=** - No debe tener "/qrnVersion=" (sin "?")
6. **Sin microsegundos** - Fechas en formato T..:..:.. sin .XXXXXX

## Ambiente

- Python 3.9+
- Virtual environment en `.venv/`
- Dependencias en `requirements.txt`
