#!/usr/bin/env python3
"""Probar cambiando el namespace de Signature a SIFEN"""

import zipfile
import io
import re

# Extraer el XML actual
with open('lote_completo.xml', 'r') as f:
    xml_content = f.read()

# Cambiar el namespace de Signature
xml_modificado = re.sub(
    r'<Signature xmlns="http://www\.w3\.org/2000/09/xmldsig#">',
    r'<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">',
    xml_content
)

# Guardar el XML modificado
with open('lote_con_signature_sifen.xml', 'w') as f:
    f.write(xml_modificado)

print("XML modificado guardado en lote_con_signature_sifen.xml")
print("Signature namespace cambiado a SIFEN")

# Verificar el cambio
if '<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">' in xml_modificado:
    print("✅ Cambio verificado")
else:
    print("❌ No se pudo cambiar el namespace")

# Crear nuevo ZIP
import base64
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
    z.writestr("xml_file.xml", xml_modificado.encode('utf-8'))
zip_bytes = buf.getvalue()

# Codificar en base64
zip_base64 = base64.b64encode(zip_bytes).decode('utf-8')

# Crear payload SOAP
from app.sifen_client.config import SifenConfig
from app.sifen_client.soap_client import SoapClient

config = SifenConfig()
dId = "01800455473701001000000120260118"  # 15 dígitos
payload = f'<rEnvioLote xmlns="http://ekuatia.set.gov.py/sifen/xsd"><dId>{dId}</dId><xDE>{zip_base64}</xDE></rEnvioLote>'

# Enviar
client = SoapClient(config)
print("\nEnviando con Signature namespace SIFEN...")
result = client.send_recibe_lote(payload, dump_http=True)

print(f"\n=== RESULTADO ===")
print(f"Código: {result.get('dCodRes', 'N/A')}")
print(f"Mensaje: {result.get('dMsgRes', 'N/A')}")
