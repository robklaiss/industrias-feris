#!/usr/bin/env python3
"""Analizar el XML completo para encontrar la causa de 0160"""

import zipfile
import io
import re

# Extraer el XML completo
with open('artifacts/soap_last_request_SENT.xml', 'r') as f:
    soap = f.read()

# Extraer xDE
xde_match = re.search(r'<xDE>([^<]+)</xDE>', soap)
if xde_match:
    xde_b64 = xde_match.group(1)
    
    # Decodificar ZIP
    import base64
    zip_data = base64.b64decode(xde_b64)
    zf = zipfile.ZipFile(io.BytesIO(zip_data))
    
    # Extraer XML
    with zf.open('xml_file.xml') as f:
        xml_content = f.read().decode('utf-8')
    
    # Guardar XML completo
    with open('lote_completo.xml', 'w') as f:
        f.write(xml_content)
    
    print("XML completo guardado en lote_completo.xml")
    
    # Analizar estructura
    import lxml.etree as ET
    try:
        # Quitar XML declaration para parsear
        xml_sin_decl = re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', xml_content)
        root = ET.fromstring(xml_sin_decl)
        ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
        
        print("\n=== ANÁLISIS DE ESTRUCTURA ===")
        print(f"Root: {root.tag}")
        print(f"Root xmlns: {root.get('xmlns')}")
        
        # Buscar rDE
        rde = root.find('.//s:rDE', ns)
        if rde is not None:
            print(f"\nrDE encontrado:")
            print(f"  Id: {rde.get('Id')}")
            print(f"  Hijos de rDE:")
            for i, child in enumerate(rde):
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                print(f"    {i}: {tag}")
                if tag == 'dVerFor':
                    print(f"      Valor: {child.text}")
        
        # Buscar DE
        de = root.find('.//s:DE', ns)
        if de is not None:
            print(f"\nDE encontrado:")
            print(f"  Id: {de.get('Id')}")
        
        # Buscar Signature
        sig = root.find('.//s:Signature', ns)
        if sig is not None:
            print(f"\nSignature encontrado:")
            print(f"  xmlns: {sig.get('xmlns')}")
        
        # Validar XSD
        try:
            from pathlib import Path
            xsd_path = Path('schemas_sifen/rLoteDE_v150.xsd')
            if xsd_path.exists():
                xsd_doc = ET.parse(str(xsd_path))
                xsd = ET.XMLSchema(xsd_doc)
                valid = xsd.validate(ET.fromstring(xml_content))
                print(f"\nValidación XSD: {'VÁLIDO' if valid else 'INVÁLIDO'}")
            else:
                print("\nXSD no encontrado")
        except Exception as e:
            print(f"\nError validando XSD: {e}")
            
    except Exception as e:
        print(f"Error analizando XML: {e}")
