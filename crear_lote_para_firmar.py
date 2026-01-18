#!/usr/bin/env python3
"""
Crear lote XML con el DE sin firma para que el sistema lo firme
"""

from lxml import etree
import sys
from datetime import datetime

# Namespace
SIFEN_NS = 'http://ekuatia.set.gov.py/sifen/xsd'

def crear_lote_sin_firma():
    # Leer el DE generado
    de_tree = etree.parse('test_rde_con_gcamfufd.xml')
    rde = de_tree.getroot()
    
    # Crear lote
    rLoteDE = etree.Element(f'{{{SIFEN_NS}}}rLoteDE')
    
    # Copiar el rDE al lote
    rLoteDE.append(rde)
    
    # Serializar sin prefijos
    xml_bytes = etree.tostring(rLoteDE, xml_declaration=True, encoding='utf-8', exclusive=False)
    
    # Remover prefijos ns0: si aparecen
    xml_str = xml_bytes.decode('utf-8')
    xml_str = xml_str.replace('ns0:', '').replace('xmlns:ns0=', 'xmlns=')
    xml_bytes = xml_str.encode('utf-8')
    
    return xml_bytes

if __name__ == '__main__':
    xml_bytes = crear_lote_sin_firma()
    
    # Guardar
    output_file = sys.argv[1] if len(sys.argv) > 1 else 'lote_para_firmar.xml'
    with open(output_file, 'wb') as f:
        f.write(xml_bytes)
    
    print(f"Lote generado: {output_file}")
    print(f"Tamaño: {len(xml_bytes)} bytes")
    
    # Verificar estructura
    from lxml import etree as ET
    root = ET.fromstring(xml_bytes)
    ns = {'s': SIFEN_NS}
    
    print("\nVerificación de estructura:")
    print(f"- Raíz: {root.tag.split('}')[-1]}")
    print(f"- Hijos: {[c.tag.split('}')[-1] for c in root]}")
    
    rde = root.find('.//s:rDE', ns)
    if rde is not None:
        print(f"- rDE Id: {rde.get('Id')}")
        print(f"- Hijos de rDE: {[c.tag.split('}')[-1] for c in rde]}")
        print(f"- Sin firma: {'OK' if rde.find('.//Signature') is None else 'ERROR'}")
