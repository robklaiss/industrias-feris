#!/usr/bin/env python3
import re
import base64
import zipfile
import io

# Extraer y analizar el lote del SOAP enviado
with open('artifacts/soap_last_request_SENT.xml', 'r') as f:
    soap = f.read()

# Extraer xDE
xde_match = re.search(r'<xDE>([^<]+)</xDE>', soap)
if xde_match:
    xde_b64 = xde_match.group(1)
    
    # Decodificar ZIP
    zip_data = base64.b64decode(xde_b64)
    zf = zipfile.ZipFile(io.BytesIO(zip_data))
    
    # Extraer XML
    with zf.open('xml_file.xml') as f:
        xml_content = f.read().decode('utf-8')
    
    # Guardar para análisis
    with open('lote_actual.xml', 'w') as f:
        f.write(xml_content)
    
    print('=== LOTE ACTUAL ===')
    print(xml_content[:500])
    print()
    
    # Verificar estructura
    if xml_content.startswith('<?xml'):
        # Quitar XML declaration
        xml_no_decl = re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', xml_content)
        
        # Verificar si tiene doble wrapper
        if '<rLoteDE><rLoteDE' in xml_no_decl:
            print('❌ TIENE DOBLE WRAPPER: <rLoteDE><rLoteDE>')
        elif '<rLoteDE xmlns=' in xml_no_decl and '</rLoteDE></rLoteDE>' not in xml_no_decl:
            print('✅ ESTRUCTURA CORRECTA: Un solo <rLoteDE> con xmlns')
        else:
            print('⚠️  ESTRUCTURA INESPERADA')
            
        # Contar rLoteDE
        count = xml_no_decl.count('<rLoteDE')
        print(f'Cantidad de <rLoteDE>: {count}')
else:
    print('No se encontró xDE')
