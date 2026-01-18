#!/usr/bin/env python3
"""Probar agregando gCamFuFD después de Signature"""

import zipfile
import io
import re
from lxml import etree

# Extraer el XML actual
with open('lote_completo.xml', 'r') as f:
    xml_content = f.read()

# Quitar XML declaration para parsear
xml_sin_decl = re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', xml_content)

# Parsear
root = etree.fromstring(xml_sin_decl)
ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd', 'ds': 'http://www.w3.org/2000/09/xmldsig#'}

# Buscar rDE
rde = root.find('.//s:rDE', ns)
if rde is None:
    # Try without namespace
    rde = root.find('.//rDE')
    
if rde is not None:
    # Buscar Signature con su namespace
    sig = rde.find('.//ds:Signature', ns)
    if sig is None:
        # Try without namespace
        sig = rde.find('.//Signature')
    if sig is not None:
        # Crear gCamFuFD después de Signature
        gcamfufd = etree.SubElement(rde, "{http://ekuatia.set.gov.py/sifen/xsd}gCamFuFD")
        
        # Agregar dCarQR (placeholder)
        dcarqr = etree.SubElement(gcamfufd, "{http://ekuatia.set.gov.py/sifen/xsd}dCarQR")
        dcarqr.text = "https://ekuatia.set.gov.py/consultas-test/qr?test"
        
        # Agregar dInfAdic
        dinfadic = etree.SubElement(gcamfufd, "{http://ekuatia.set.gov.py/sifen/xsd}dInfAdic")
        dinfadic.text = ""
        
        print("gCamFuFD agregado después de Signature")
        
        # Serializar
        xml_con_gcamfufd = etree.tostring(root, encoding='utf-8', xml_declaration=True, pretty_print=False).decode('utf-8')
        
        # Guardar
        with open('lote_con_gcamfufd.xml', 'w') as f:
            f.write(xml_con_gcamfufd)
        
        print("XML guardado en lote_con_gcamfufd.xml")
        
        # Verificar estructura
        print("\nEstructura de rDE:")
        for i, child in enumerate(rde):
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            print(f"  {i}: {tag}")
        
        # Crear nuevo ZIP y enviar
        import base64
        from app.sifen_client.config import SifenConfig
        from app.sifen_client.soap_client import SoapClient
        
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
            z.writestr("xml_file.xml", xml_con_gcamfufd.encode('utf-8'))
        zip_bytes = buf.getvalue()
        
        zip_base64 = base64.b64encode(zip_bytes).decode('utf-8')
        
        config = SifenConfig()
        dId = "01800455473701001000000120260118"
        payload = f'<rEnvioLote xmlns="http://ekuatia.set.gov.py/sifen/xsd"><dId>{dId}</dId><xDE>{zip_base64}</xDE></rEnvioLote>'
        
        client = SoapClient(config)
        print("\nEnviando con gCamFuFD agregado...")
        result = client.send_recibe_lote(payload, dump_http=True)
        
        print(f"\n=== RESULTADO ===")
        print(f"Código: {result.get('dCodRes', 'N/A')}")
        print(f"Mensaje: {result.get('dMsgRes', 'N/A')}")
    else:
        print("No se encontró Signature")
else:
    print("No se encontró rDE")
