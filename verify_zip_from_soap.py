#!/usr/bin/env python3
"""
Script para extraer y verificar el ZIP del último SOAP enviado.
"""

import base64
import zipfile
import io
import re
from pathlib import Path

def extract_and_verify_zip(soap_file="artifacts/soap_last_request_SENT.xml"):
    """Extrae el ZIP del SOAP y verifica su estructura."""
    
    # Leer el archivo SOAP
    soap_path = Path(soap_file)
    if not soap_path.exists():
        print(f"❌ Archivo no encontrado: {soap_file}")
        return
    
    soap_content = soap_path.read_text(encoding='utf-8')
    
    # Extraer xDE (base64 del ZIP)
    xde_match = re.search(r'<xDE>(.*?)</xDE>', soap_content, re.DOTALL)
    if not xde_match:
        print("❌ No se encontró <xDE> en el SOAP")
        return
    
    xde_b64 = xde_match.group(1).strip()
    zip_bytes = base64.b64decode(xde_b64)
    
    print(f"✅ ZIP extraído: {len(zip_bytes)} bytes")
    
    # Verificar estructura del ZIP
    with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
        namelist = zf.namelist()
        print(f"✅ ZIP_NAMES: {namelist}")
        
        # Verificar método de compresión
        for filename in namelist:
            info = zf.getinfo(filename)
            comp_method = "STORED" if info.compress_type == zipfile.ZIP_STORED else "DEFLATED"
            print(f"✅ {filename}: compression method = {comp_method} ({info.compress_type})")
        
        # Leer xml_file.xml y mostrar header
        if 'xml_file.xml' in namelist:
            content = zf.read('xml_file.xml').decode('utf-8')
            print(f"✅ HEAD(160):\n{content[:160]}")
            
            # Verificar estructura
            if content.startswith('<?xml version="1.0" encoding="UTF-8"?><rLoteDE>'):
                print("✅ Estructura correcta: comienza con XML declaration y wrapper")
            else:
                print("⚠️ Estructura inesperada")
                
            # Extraer XML interno
            wrapper_match = re.search(r'<rLoteDE>(.*)</rLoteDE>', content, re.DOTALL)
            if wrapper_match:
                inner_xml = wrapper_match.group(1)
                print(f"✅ XML interno extraído: {len(inner_xml)} bytes")
                
                # Verificar que tiene el namespace
                if 'xmlns="http://ekuatia.set.gov.py/sifen/xsd"' in inner_xml:
                    print("✅ Namespace SIFEN encontrado en XML interno")
    
    # Guardar ZIP para inspección manual
    out_zip = Path("last_extracted_zip.zip")
    out_zip.write_bytes(zip_bytes)
    print(f"💾 ZIP guardado: {out_zip}")

if __name__ == "__main__":
    extract_and_verify_zip()
