import os
os.environ["SIFEN_EMISOR_RUC"] = "4554737-8"

from tools.send_sirecepde import send_sirecepde_lote
from pathlib import Path

print("Generando y enviando lote con SOAP 1.2 sin prefijos...")

# Usar el XML existente que tiene el RUC correcto
xml_file = Path("lote.xml")

try:
    result = send_sirecepde_lote(
        xml_file=xml_file,
        env="test",
        dump_http=True
    )
    
    print(f"\n=== RESULTADO ===")
    print(f"Código: {result.get('dCodRes', 'N/A')}")
    print(f"Mensaje: {result.get('dMsgRes', 'N/A')}")
    if result.get('dProtConsLote'):
        print(f"Protocolo: {result['dProtConsLote']}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
