import os
os.environ["SIFEN_EMISOR_RUC"] = "4554737-8"

from app.sifen_client.soap_client import SoapClient
from app.sifen_client.config import SifenConfig

# Configurar cliente
config = SifenConfig()
client = SoapClient(config)

# Cargar XML existente
with open("lote.xml", "r") as f:
    xml_content = f.read()

print("Enviando lote con SOAP 1.2 sin prefijos (como TIPS)...")
try:
    result = client.send_recibe_lote(xml_content, dump_http=True)
    print(f"Código de respuesta: {result.get('dCodRes', 'N/A')}")
    print(f"Mensaje: {result.get('dMsgRes', 'N/A')}")
except Exception as e:
    print(f"Error: {e}")
