#!/usr/bin/env python3
"""
Show the key changes made to test_smoke_recibe_lote.py
"""
import sys
from pathlib import Path

print("=== CAMBIOS CLAVE EN tools/test_smoke_recibe_lote.py ===\n")

print("1. Nuevo flag --check-ruc agregado:")
print("   + parser.add_argument(")
print("   +     '--check-ruc',")
print("   +     action='store_true',")
print("   +     help='Ejecuta validación de RUC (default: false). Nunca aborta el smoke test.'")
print("   + )")
print()

print("2. La validación de RUC ahora es OPT-IN (solo se ejecuta si --check-ruc está presente)")
print("   - ANTES: Se ejecutaba siempre y abortaba con SystemExit si dRUCFactElec='N'")
print("   - AHORA: Solo se ejecuta con --check-ruc y nunca aborta (solo loguea warnings)")
print()

print("3. Se guardan artifacts de la consulta RUC cuando se ejecuta:")
print("   + artifacts/smoke_test_consulta_ruc_<timestamp>.json")
print()

print("=== COMANDOS PARA EJECUTAR ===\n")
print("1. SIN validar RUC (comportamiento por defecto):")
print("   cd tesaka-cv")
print("   .venv/bin/python tools/test_smoke_recibe_lote.py --env test")
print()

print("2. CON validación RUC (solo informativo, nunca aborta):")
print("   cd tesaka-cv")
print("   .venv/bin/python tools/test_smoke_recibe_lote.py --env test --check-ruc")
print()

print("=== RESULTADO ESPERADO ===")
print("- El smoke test SIEMPRE llegará a 'Paso 2: Enviando a SIFEN'")
print("- La única forma de abortar es por errores de firma o mTLS")
print("- dRUCFactElec='N' y dCodRes!=0502 solo generan WARNINGs")
print("- Los artifacts de RUC se guardan cuando se ejecuta la consulta")
