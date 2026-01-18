import os
os.environ["SIFEN_EMISOR_RUC"] = "4554737-8"

from app.sifen_client.soap_client import SoapClient
from app.sifen_client.config import SifenConfig
from pathlib import Path

# Cargar un lote ya procesado que tenga dId y xDE
with open("artifacts/recibe_lote_sent_20260118_162216.xml", "r") as f:
    xml_content = f.read()

# Extraer solo el rEnvioLote con el namespace correcto
import lxml.etree as etree
import re

# Buscar rEnvioLote y extraer su contenido
match = re.search(r'<xsd:rEnvioLote[^>]*>(.*?)</xsd:rEnvioLote>', xml_content, re.DOTALL)
if match:
    # Extraer dId y xDE
    inner = match.group(1)
    dId_match = re.search(r'<xsd:dId>(.*?)</xsd:dId>', inner)
    xDE_match = re.search(r'<xsd:xDE>(.*?)</xsd:xDE>', inner)
    
    if dId_match and xDE_match:
        dId = dId_match.group(1)
        xDE = xDE_match.group(1)
        
        # Crear payload en nuevo formato (sin prefijos)
        payload = f'<rEnvioLote xmlns="http://ekuatia.set.gov.py/sifen/xsd"><dId>{dId}</dId><xDE>{xDE}</xDE></rEnvioLote>'
        
        print("Payload creado con nuevo formato (sin prefijos)")
        print(f"dId: {dId}")
        print(f"xDE: {'(presente)' if xDE else '(vacío)'}")
        
        # Enviar
        config = SifenConfig()
        client = SoapClient(config)
        
        print("\nEnviando con SOAP 1.2 sin prefijos (estilo TIPS)...")
        result = client.send_recibe_lote(payload, dump_http=True)
        
        print(f"\n=== RESULTADO ===")
        print(f"Código: {result.get('dCodRes', 'N/A')}")
        print(f"Mensaje: {result.get('dMsgRes', 'N/A')}")
        
        # Guardar el SOAP generado para comparar
        if Path("artifacts/soap_last_request_SENT.xml").exists():
            with open("artifacts/soap_last_request_SENT.xml", "r") as f:
                soap_gen = f.read()
            print("\n=== SOAP GENERADO ===")
            print(soap_gen[:300] + "...")
    else:
        print("No se encontró dId o xDE")
else:
    print("No se encontró rEnvioLote")
