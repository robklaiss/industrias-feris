#!/usr/bin/env python3
import lxml.etree as etree
import base64
import zipfile
import io

# Leer payload
with open('payload_extraido.txt', 'r') as f:
    payload = f.read().strip()

# Extraer xDE
root = etree.fromstring(payload.encode('utf-8'))
xDE_val = None
for child in root.iter():
    if etree.QName(child).localname == 'xDE':
        xDE_val = child.text
        break

if xDE_val:
    # Decodificar ZIP
    zip_data = base64.b64decode(xDE_val)
    zf = zipfile.ZipFile(io.BytesIO(zip_data))
    
    print('Archivos en el ZIP:', zf.namelist())
    
    # Extraer el primer archivo XML
    xml_files = [f for f in zf.namelist() if f.endswith('.xml')]
    if xml_files:
        with zf.open(xml_files[0]) as f:
            lote_xml = f.read().decode('utf-8')
        
        # Analizar estructura
        doc = etree.fromstring(lote_xml.encode('utf-8'))
        ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
        
        print('=== ANÁLISIS DEL LOTE ===')
        print(f'Root tag: {doc.tag}')
        print(f'Root xmlns: {doc.get("xmlns")}')
        print()
        
        # Verificar rDE
        rde = doc.find('.//s:rDE', ns)
        if rde is not None:
            print(f'rDE Id: {rde.get("Id")}')
            children = [c.tag.split('}')[-1] for c in rde]
            print(f'rDE children: {children}')
            print(f'Primer hijo: {children[0] if children else "NONE"}')
            
            # Verificar DE
            de = rde.find('.//s:DE', ns)
            if de is not None:
                print(f'DE Id: {de.get("Id")}')
                print(f'Ids diferentes: {rde.get("Id") != de.get("Id")}')
                
            # Verificar Signature
            sig = rde.find('.//s:Signature', ns)
            if sig is not None:
                print(f'Signature xmlns: {sig.get("xmlns")}')
                
        # Guardar lote para inspección manual
        with open('lote_analizado.xml', 'w') as f:
            f.write(lote_xml)
        print(f'\nLote guardado en lote_analizado.xml (desde {xml_files[0]})')
        
        # Verificar si tiene gCamFuFD
        if '<gCamFuFD' in lote_xml:
            print('\n⚠️  ATENCIÓN: El lote contiene gCamFuFD')
        else:
            print('\n❌ El lote NO contiene gCamFuFD')
