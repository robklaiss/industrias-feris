#!/usr/bin/env python3
"""Probar con prefijos en SOAP como sugiere la KB"""

import os
os.environ["SIFEN_EMISOR_RUC"] = "4554737-8"

from pathlib import Path
from tools.send_sirecepde import build_and_sign_lote_from_xml
from app.sifen_client.config import SifenConfig
from app.sifen_client.soap_client import SoapClient
import base64
import zipfile
import io

# Cargar certificado
config = SifenConfig()
cert_path = config.cert_path
cert_password = config.cert_password

# Usar el XML que ya sabemos que funciona (lote_con_gcamfufd.xml)
with open('lote_con_gcamfufd.xml', 'r') as f:
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

# Modificar el SOAP client para usar prefijos
print("Creando SOAP con prefijosxsd...")

# Construir SOAP manualmente con prefijos
soap_payload = f'''<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope" xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd">
  <env:Header/>
  <env:Body>
    <xsd:rEnvioLote>
      <xsd:dId>{dId}</xsd:dId>
      <xsd:xDE>{zip_base64}</xsd:xDE>
    </xsd:rEnvioLote>
  </env:Body>
</env:Envelope>'''

# Guardar SOAP para debug
with open('soap_con_prefijos.xml', 'w') as f:
    f.write(soap_payload)

print("SOAP guardado en soap_con_prefijos.xml")

# Enviar directamente con requests para tener control total
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Convertir P12 a PEM si es necesario
if config.cert_path.endswith('.p12'):
    from app.sifen_client.pkcs12_utils import p12_to_temp_pem_files
    cert_pem, key_pem = p12_to_temp_pem_files(config.cert_path, config.cert_password)
    cert_tuple = (cert_pem, key_pem)
else:
    cert_tuple = config.cert_path

# Configurar retry
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)

adapter = HTTPAdapter(max_retries=retry_strategy)
session = requests.Session()
session.mount("https://", adapter)

# Headers
headers = {
    'Content-Type': 'application/soap+xml; charset=utf-8',
    'SOAPAction': 'http://ekuatia.set.gov.py/sifen/wsdl/RecibeLote'
}

# URL
url = config.base_url + '/wsdl/RecibeLote'

print(f"\nEnviando a: {url}")
print(f"Headers: {headers}")

# Enviar
response = session.post(url, data=soap_payload, headers=headers, cert=cert_tuple)

print(f"\nResponse status: {response.status_code}")
print(f"Response headers: {response.headers}")

if response.status_code == 200:
    # Parsear respuesta
    from lxml import etree
    root = etree.fromstring(response.content)
    
    # Buscar resultado
    ns = {'env': 'http://www.w3.org/2003/05/soap-envelope', 's': 'http://ekuatia.set.gov.py/sifen/xsd'}
    
    resultado = root.find('.//s:dCodRes', ns)
    mensaje = root.find('.//s:dMsgRes', ns)
    
    print(f"\n=== RESULTADO ===")
    print(f"Código: {resultado.text if resultado is not None else 'N/A'}")
    print(f"Mensaje: {mensaje.text if mensaje is not None else 'N/A'}")
else:
    print(f"\nError HTTP: {response.text}")

# Cleanup temp files
if config.cert_path.endswith('.p12'):
    from app.sifen_client.pkcs12_utils import cleanup_pem_files
    cleanup_pem_files(cert_pem, key_pem)
