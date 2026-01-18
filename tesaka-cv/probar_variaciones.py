#!/usr/bin/env python3
"""Probar con el XML modificado directamente usando SoapClient"""

import os
os.environ["SIFEN_EMISOR_RUC"] = "4554737-8"

from app.sifen_client.config import SifenConfig
from app.sifen_client.soap_client import SoapClient
import base64
import zipfile
import io

# Cargar configuración
config = SifenConfig()

# Usar el XML modificado con Signature namespace SIFEN
with open('lote_con_signature_sifen.xml', 'r') as f:
    xml_content = f.read()

# Crear ZIP
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
    z.writestr("xml_file.xml", xml_content.encode('utf-8'))
zip_bytes = buf.getvalue()

# Codificar en base64
zip_base64 = base64.b64encode(zip_bytes).decode('utf-8')

# Crear payload SOAP con prefijos como en la KB
dId = "01800455473701001000000120260118"

# Usar el formato con prefijos que sugiere la KB
payload = f'<xsd:rEnvioLote xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd"><xsd:dId>{dId}</xsd:dId><xsd:xDE>{zip_base64}</xsd:xDE></xsd:rEnvioLote>'

# Enviar con SoapClient
client = SoapClient(config)
print("Enviando con Signature namespace SIFEN y prefijosxsd...")
result = client.send_recibe_lote(payload, dump_http=True)

print(f"\n=== RESULTADO ===")
print(f"Código: {result.get('dCodRes', 'N/A')}")
print(f"Mensaje: {result.get('dMsgRes', 'N/A')}")

# También probar con gCamFuFD
print("\n" + "="*50)
print("Probando con gCamFuFD agregado...")

with open('lote_con_gcamfufd.xml', 'r') as f:
    xml_content = f.read()

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
    z.writestr("xml_file.xml", xml_content.encode('utf-8'))
zip_bytes = buf.getvalue()

zip_base64 = base64.b64encode(zip_bytes).decode('utf-8')
payload = f'<xsd:rEnvioLote xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd"><xsd:dId>{dId}</xsd:dId><xsd:xDE>{zip_base64}</xsd:xDE></xsd:rEnvioLote>'

result2 = client.send_recibe_lote(payload, dump_http=True)

print(f"\n=== RESULTADO CON gCamFuFD ===")
print(f"Código: {result2.get('dCodRes', 'N/A')}")
print(f"Mensaje: {result2.get('dMsgRes', 'N/A')}")
