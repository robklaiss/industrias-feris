#!/usr/bin/env python3
"""
Genera y firma un XML DE con todos los requisitos para evitar error 0160:
- Sin prefijos en elementos XMLDSig
- rDE con Id único
- dVerFor como primer hijo
- gCamFuFD después de Signature
- Signature con xmlns SIFEN
"""

import sys
import os
from lxml import etree
import re

# Importaciones locales
from app.sifen_client.xml_generator_v150 import generate_cdc
from tools.send_sirecepde import sign_de_with_p12, SIFEN_NS

def generar_y_firmar_limpio():
    # Generar DE básico
    data = {
        "ruc_emisor": "4554737-8",
        "tipo_factura": "factura",
        "numero_factura": "0000004",
        "monto_total": 100000,
        "descripcion": "ITEM DE PRUEBA LIMPIO"
    }
    
    # Generar XML usando generate_cdc
    xml_str = generate_cdc(data)
    xml_bytes = xml_str.encode('utf-8')
    
    print("XML generado, limpiando prefijos...")
    
    # Limpiar prefijos ANTES de firmar
    xml_clean = xml_bytes.decode('utf-8')
    
    # Eliminar prefijos de XMLDSig si existen
    xmldsig_elements = ['SignedInfo', 'CanonicalizationMethod', 'SignatureMethod', 
                       'Reference', 'Transforms', 'Transform', 'DigestMethod', 'DigestValue',
                       'SignatureValue', 'KeyInfo', 'X509Data', 'X509Certificate']
    
    for elem in xmldsig_elements:
        # Reemplazar opening tags con prefijos
        xml_clean = re.sub(f'<ns\\d+:{elem}([^>]*)>', f'<{elem}\\1>', xml_clean)
        # Reemplazar closing tags con prefijos
        xml_clean = re.sub(f'</ns\\d+:{elem}>', f'</{elem}>', xml_clean)
    
    # Eliminar declaraciones xmlns:nsX
    xml_clean = re.sub(r' xmlns:ns\d+="http://www\.w3\.org/2000/09/xmldsig#"', '', xml_clean)
    
    xml_bytes = xml_clean.encode('utf-8')
    
    # Verificar que no hay prefijos
    if b'ns1:' in xml_bytes or b'ns2:' in xml_bytes or b'ns3:' in xml_bytes:
        print("❌ Aún hay prefijos en el XML")
        return None
    
    print("✓ XML limpio de prefijos")
    
    # Firmar
    cert_path = os.getenv('SIFEN_SIGN_P12_PATH', 'certs/test_cert.p12')
    cert_pass = os.getenv('SIFEN_SIGN_P12_PASSWORD', 'test123')
    
    print("Firmando XML...")
    signed_bytes = sign_de_with_p12(xml_bytes, cert_path, cert_pass)
    
    if signed_bytes:
        # Verificar estructura final
        root = etree.fromstring(signed_bytes)
        ns = {'s': SIFEN_NS}
        rde = root if root.tag.endswith('rDE') else root.find('.//s:rDE', ns)
        
        if rde is not None:
            print("\n=== ESTRUCTURA FINAL ===")
            children = [c.tag.split('}')[-1] for c in rde]
            print(f'Hijos de rDE: {children}')
            print(f'dVerFor primero: {children[0] == "dVerFor" if children else False}')
            print(f'gCamFuFD después de Signature: {children.index("gCamFuFD") == children.index("Signature") + 1 if "Signature" in children and "gCamFuFD" in children else False}')
            
            sig = rde.find('.//{*}Signature')
            if sig is not None:
                print(f'Signature xmlns: {sig.get("xmlns")}')
        
        return signed_bytes
    else:
        print("❌ Error al firmar")
        return None

if __name__ == '__main__':
    signed_xml = generar_y_firmar_limpio()
    
    if signed_xml:
        output_file = sys.argv[1] if len(sys.argv) > 1 else '../test_rde_limpio_firmado.xml'
        with open(output_file, 'wb') as f:
            f.write(signed_xml)
        
        print(f"\nXML guardado: {output_file}")
        print(f"Tamaño: {len(signed_xml)} bytes")
