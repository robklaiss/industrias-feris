#!/usr/bin/env python3
"""
Forensic XDE extractor from SOAP payload
Extrae y analiza el contenido xDE de un SOAP enviado a SIFEN
"""
import sys
import base64
import zipfile
import hashlib
import re
import io
from pathlib import Path
from lxml import etree

def extract_xde_from_soap(soap_path: str):
    """Extrae xDE base64 del SOAP y decodifica"""
    soap_path = Path(soap_path)
    if not soap_path.exists():
        print(f"ERROR: SOAP file not found: {soap_path}")
        return None, None, None
    
    # Leer SOAP
    soap_content = soap_path.read_bytes()
    
    # Parsear SOAP para extraer xDE
    try:
        root = etree.fromstring(soap_content)
        ns = {'soap': 'http://www.w3.org/2003/05/soap-envelope',
              'sifen': 'http://ekuatia.set.gov.py/sifen/xsd',
              'xsd': 'http://ekuatia.set.gov.py/sifen/xsd'}
        
        # Buscar xDE con varios prefijos posibles
        xde_elem = root.find('.//{http://ekuatia.set.gov.py/sifen/xsd}xDE')
        
        if xde_elem is None:
            print("ERROR: xDE element not found in SOAP")
            print("Available elements:")
            for elem in root.iter():
                if elem.tag:
                    print(f"  {elem.tag}")
            return None, None, None
        
        xde_b64 = xde_elem.text.strip() if xde_elem.text else ""
        
        # Limpiar whitespace del base64
        xde_b64_clean = re.sub(r'\s+', '', xde_b64)
        
        print(f"xDE base64 length (original): {len(xde_b64)}")
        print(f"xDE base64 length (cleaned): {len(xde_b64_clean)}")
        
        # Decodificar base64
        try:
            zip_bytes = base64.b64decode(xde_b64_clean, validate=True)
            print(f"ZIP decoded successfully: {len(zip_bytes)} bytes")
            print(f"ZIP SHA256: {hashlib.sha256(zip_bytes).hexdigest()}")
        except Exception as e:
            print(f"ERROR: Failed to decode base64: {e}")
            return None, None, None
        
        # Extraer lote.xml del ZIP
        try:
            zip_buffer = io.BytesIO(zip_bytes)
            with zipfile.ZipFile(zip_buffer, 'r') as zf:
                print(f"ZIP entries: {zf.namelist()}")
                
                if 'lote.xml' not in zf.namelist():
                    print("ERROR: lote.xml not found in ZIP")
                    return None, None, None
                
                lote_bytes = zf.read('lote.xml')
                print(f"lote.xml extracted: {len(lote_bytes)} bytes")
                
                # Guardar archivos
                artifacts_dir = Path('artifacts')
                artifacts_dir.mkdir(exist_ok=True)
                
                zip_out = artifacts_dir / '_forensic_from_soap.zip'
                lote_out = artifacts_dir / '_forensic_from_soap_lote.xml'
                
                zip_out.write_bytes(zip_bytes)
                lote_out.write_bytes(lote_bytes)
                
                print(f"Saved: {zip_out}")
                print(f"Saved: {lote_out}")
                
                # Analizar lote.xml
                analyze_lote_xml(lote_bytes)
                
                return zip_bytes, lote_bytes, xde_b64_clean
                
        except Exception as e:
            print(f"ERROR: Failed to extract from ZIP: {e}")
            return None, None, None
            
    except etree.XMLSyntaxError as e:
        print(f"ERROR: SOAP not well-formed: {e}")
        return None, None, None

def analyze_lote_xml(lote_bytes: bytes):
    """Analiza el contenido del lote.xml"""
    print("\n=== lote.xml Analysis ===")
    
    # Verificar BOM
    if lote_bytes.startswith(b'\xef\xbb\xbf'):
        print("WARNING: lote.xml starts with UTF-8 BOM")
    elif lote_bytes.startswith(b'<?xml'):
        print("OK: lote.xml starts with <?xml")
    else:
        print(f"WARNING: lote.xml starts with: {lote_bytes[:20]}")
    
    # Primeros 200 bytes
    print(f"First 200 bytes (hex): {lote_bytes[:200].hex()}")
    print(f"First 200 bytes (text): {lote_bytes[:200]}")
    
    # Parsear y contar elementos
    try:
        root = etree.fromstring(lote_bytes)
        ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
        
        # Contar Signature (buscar sin namespace específico)
        signatures = root.xpath('//*[local-name()="Signature"]')
        print(f"Signature elements found: {len(signatures)}")
        if signatures:
            sig_ns = signatures[0].get('xmlns')
            print(f"Signature xmlns: {sig_ns}")
            print(f"Signature parent: {signatures[0].getparent().tag}")
        
        # Contar gCamFuFD
        gcamfufd = root.xpath('.//s:gCamFuFD', namespaces=ns)
        print(f"gCamFuFD elements found: {len(gcamfufd)}")
        
        # Verificar well-formed
        print("lote.xml is well-formed")
        
    except etree.XMLSyntaxError as e:
        print(f"ERROR: lote.xml not well-formed: {e}")

def main():
    if len(sys.argv) != 2:
        print("Usage: forensic_xde_from_soap.py <soap_file.xml>")
        sys.exit(1)
    
    soap_file = sys.argv[1]
    print(f"Analyzing SOAP: {soap_file}")
    
    zip_bytes, lote_bytes, xde_b64 = extract_xde_from_soap(soap_file)
    
    if zip_bytes is None:
        print("FAILED to extract xDE")
        sys.exit(1)
    
    print("\n=== SUCCESS ===")
    print(f"ZIP bytes: {len(zip_bytes)}")
    print(f"lote.xml bytes: {len(lote_bytes)}")
    print(f"xDE base64 cleaned: {len(xde_b64)}")

if __name__ == "__main__":
    main()
