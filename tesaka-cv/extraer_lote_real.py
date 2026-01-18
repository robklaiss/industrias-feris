#!/usr/bin/env python3
"""Extraer y revisar el lote del payload real"""

import lxml.etree as etree
import base64
import zipfile
import io

# Leer payload del archivo
with open('payload.txt', 'r') as f:
    payload = f.read().strip().strip("'")

print('Payload length:', len(payload))
print('Payload starts:', payload[:100])
print()

# Extraer y decodificar el xDE
root = etree.fromstring(payload.encode('utf-8'))
xDE_val = None
for child in root.iter():
    if etree.QName(child).localname == 'xDE':
        xDE_val = child.text
        break

if xDE_val:
    print('xDE length:', len(xDE_val))
    
    # Decodificar el base64
    zip_data = base64.b64decode(xDE_val)
    print('ZIP data length:', len(zip_data))
    
    zf = zipfile.ZipFile(io.BytesIO(zip_data))
    print('ZIP files:', zf.namelist())
    
    # Extraer lote.xml
    with zf.open('lote.xml') as f:
        lote_xml = f.read().decode('utf-8')
    
    print('\n=== Estructura del lote ===')
    doc = etree.fromstring(lote_xml.encode('utf-8'))
    ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
    
    # Verificar rLoteDE
    print(f'rLoteDE xmlns: {doc.get("xmlns")}')
    
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
    else:
        print('ERROR: No se encontró rDE')
        
    # Guardar lote para inspección
    with open('lote_extraido.xml', 'w') as f:
        f.write(lote_xml)
    print('\nLote guardado en lote_extraido.xml')
else:
    print('ERROR: No se encontró xDE')
