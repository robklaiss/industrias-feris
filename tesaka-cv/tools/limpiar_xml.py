#!/usr/bin/env python3
"""
Procesa un XML existente para eliminar prefijos y cumplir requisitos
"""

import sys
import re
from lxml import etree

def limpiar_xml_para_firma(xml_bytes):
    """
    Limpia el XML para que cumpla con los requisitos de SIFEN
    """
    # Si ya no hay firma, simplemente eliminar xmlns:nsX
    if b'<Signature' not in xml_bytes:
        xml_str = xml_bytes.decode('utf-8')
        # Eliminar cualquier declaración xmlns:nsX
        xml_str = re.sub(r' xmlns:ns\d+="[^"]*"', '', xml_str)
        return xml_str.encode('utf-8')
    
    # Si hay firma, devolver sin cambios (ya está firmado)
    return xml_bytes

if __name__ == '__main__':
    # Leer XML existente
    input_file = sys.argv[1] if len(sys.argv) > 1 else '../test_rde_final_correct.xml'
    output_file = sys.argv[2] if len(sys.argv) > 2 else '../test_rde_para_firmar_limpio.xml'
    
    with open(input_file, 'rb') as f:
        xml_bytes = f.read()
    
    # Eliminar firma existente si la hay
    if b'<Signature' in xml_bytes:
        # Extraer rDE sin Signature
        root = etree.fromstring(xml_bytes)
        ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
        rde = root if root.tag.endswith('rDE') else root.find('.//s:rDE', ns)
        
        if rde is not None:
            # Eliminar Signature
            sig = rde.find('.//{*}Signature')
            if sig is not None:
                sig.getparent().remove(sig)
                print("✓ Firma existente eliminada")
    
    # Corregir RUC para que incluya DV
    xml_str = xml_bytes.decode('utf-8')
    xml_str = xml_str.replace('<dRucEm>4554737', '<dRucEm>4554737-8')
    xml_bytes = xml_str.encode('utf-8')
    
    # Limpiar XML
    xml_limpio = limpiar_xml_para_firma(xml_bytes)
    
    # Guardar
    with open(output_file, 'wb') as f:
        f.write(xml_limpio)
    
    print(f"XML limpio guardado: {output_file}")
    print(f"Tamaño: {len(xml_limpio)} bytes")
    
    # Verificar
    if b'ns1:' in xml_limpio or b'ns2:' in xml_limpio or b'ns3:' in xml_limpio:
        print("❌ Aún hay prefijos")
    else:
        print("✓ Sin prefijos")
