#!/usr/bin/env python3
"""
Script para probar el envío forzando SIFEN_NO_REUSE_ZIP=1
"""

import os
import sys
from pathlib import Path

# Configurar variables de entorno
os.environ["SIFEN_NO_REUSE_ZIP"] = "1"
os.environ["SIFEN_SKIP_RUC_GATE"] = "1"
os.environ["SIFEN_SKIP_LAST_LOTE_MISMATCH"] = "1"

# Limpiar artifacts anteriores
for f in ["artifacts/soap_last_request_SENT.xml", "artifacts/soap_last_response_RECV.xml"]:
    if Path(f).exists():
        Path(f).unlink()

# Importar y ejecutar
sys.path.insert(0, str(Path(__file__).parent))
from tools.send_sirecepde import send_sirecepde

# Usar el XML corregido con namespace SIFEN
xml_path = Path("artifacts/_debug_lote_fixed.xml")
if not xml_path.exists():
    print(f"❌ El archivo {xml_path} no existe")
    print("Primero ejecuta: python tools/fix_signature_namespace.py artifacts/_debug_lote_from_xde.xml")
    sys.exit(1)

print(f"📄 Enviando: {xml_path}")
print(f"🔧 SIFEN_NO_REUSE_ZIP = {os.environ['SIFEN_NO_REUSE_ZIP']}")

result = send_sirecepde(
    xml_path=xml_path,
    env="test",
    dump_http=True
)

print("\n=== RESULTADO ===")
print(f"Success: {result.get('success')}")
if not result.get('success'):
    print(f"Error: {result.get('error')}")
    print(f"Código SIFEN: {result.get('response', {}).get('dCodRes', 'N/A')}")
    print(f"Mensaje SIFEN: {result.get('response', {}).get('dMsgRes', 'N/A')}")
