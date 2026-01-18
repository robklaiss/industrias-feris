#!/usr/bin/env python3
"""
Crear lote XML con el DE completo para enviar a SIFEN
"""

from lxml import etree
import sys
from datetime import datetime

# Namespace
SIFEN_NS = 'http://ekuatia.set.gov.py/sifen/xsd'

def crear_lote_con_de_completo():
    # Leer el DE generado
    de_tree = etree.parse('test_rde_completo_real.xml')
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
    xml_bytes = crear_lote_con_de_completo()
    
    # Guardar
    output_file = sys.argv[1] if len(sys.argv) > 1 else 'lote_completo_oficial.xml'
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
        print(f"- Orden correcto: {rde[0].tag.split('}')[-1] == 'dVerFor' and rde[1].tag.split('}')[-1] == 'DE' and rde[2].tag.split('}')[-1] == 'Signature' and rde[3].tag.split('}')[-1] == 'gCamFuFD'}")
