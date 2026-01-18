#!/usr/bin/env python3
"""
Validate lote.xml against XSD that declares rLoteDE.

Soporte para modo estricto via SIFEN_STRICT_LOTE_XSD:
- 1: Falla si falta el XSD que declara rLoteDE
-  valor por defecto (no seteado): WARNING y continúa
"""
import os
import sys
import zipfile
import io
from pathlib import Path
from lxml import etree
from urllib.parse import urlparse

# XSD search paths
XSD_PATHS = [
    "xsd/",
    "xsd_local/",
    "schemas_sifen/",
    "schemas_sifen/xsd/",
]

def find_rlotede_xsd():
    """Find XSD that declares rLoteDE element."""
    # Buscar específicamente rLoteDE_v150.xsd primero
    for base_path in XSD_PATHS:
        if not os.path.exists(base_path):
            continue
            
        # Buscar rLoteDE_v150.xsd explícitamente
        rlotede_v150 = os.path.join(base_path, 'rLoteDE_v150.xsd')
        if os.path.exists(rlotede_v150):
            return rlotede_v150
    
    # Si no encuentra, buscar en otros XSDs
    for base_path in XSD_PATHS:
        if not os.path.exists(base_path):
            continue
            
        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.endswith('.xsd'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # Look for element declaration of rLoteDE
                            if 'xs:element' in content and 'name="rLoteDE"' in content:
                                return filepath
                    except Exception as e:
                        print(f"Error reading {filepath}: {e}")
    
    return None

def extract_lote_from_soap():
    """Extract lote.xml from soap_last_request_SENT.xml."""
    soap_file = "artifacts/soap_last_request_SENT.xml"
    lote_file = "artifacts/_last_sent_lote.xml"
    
    # Check if lote file already exists
    if os.path.exists(lote_file):
        return lote_file
    
    # Extract from SOAP
    if not os.path.exists(soap_file):
        print(f"ERROR: Neither {lote_file} nor {soap_file} found")
        sys.exit(2)
    
    try:
        # Extract xDE from SOAP
        with open(soap_file, 'rb') as f:
            soap_content = f.read()
        
        # Parse SOAP to find base64 content
        soap_xml = etree.fromstring(soap_content)
        namespaces = {
            'soap': 'http://www.w3.org/2003/05/soap-envelope',
            'xsd': 'http://ekuatia.set.gov.py/sifen/xsd'
        }
        
        xde_elem = soap_xml.xpath('//xsd:xDE', namespaces=namespaces)
        if not xde_elem:
            print("ERROR: xDE element not found in SOAP")
            sys.exit(2)
        
        # Decode base64 and extract from zip
        import base64
        zip_data = base64.b64decode(xde_elem[0].text)
        
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            with zf.open('lote.xml') as lf:
                lote_content = lf.read()
                
        with open(lote_file, 'wb') as f:
            f.write(lote_content)
            
        return lote_file
        
    except Exception as e:
        print(f"ERROR extracting lote from SOAP: {e}")
        sys.exit(2)

def rewrite_schema_locations(xsd_path):
    """Rewrite remote schemaLocation to local paths."""
    with open(xsd_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Get the directory of this XSD
    xsd_dir = os.path.dirname(xsd_path)
    
    # Replace all https://ekuatia.set.gov.py/sifen/xsd/ with local relative paths
    # We'll make them relative to the XSD directory
    content = content.replace(
        'https://ekuatia.set.gov.py/sifen/xsd/',
        './'
    )
    
    # Write to temp file
    temp_path = xsd_path + '.tmp'
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return temp_path

def validate_lote_from_bytes(lote_file_path: str):
    """Validate lote.xml from file path (used by send_sirecepde)."""
    # Find XSD that declares rLoteDE
    xsd_path = find_rlotede_xsd()
    
    # Verificar modo estricto
    strict_mode = os.environ.get('SIFEN_STRICT_LOTE_XSD') == '1'
    
    if not xsd_path:
        if strict_mode:
            print("❌ XSD FAIL: No se encuentra XSD que declare rLoteDE (modo estricto)")
            sys.exit(2)
        else:
            print("⚠️ XSD WARN: No se encuentra XSD que declare rLoteDE (continuando en modo no estricto)")
            return
    
    print(f"✅ XSD OK: Usando {os.path.basename(xsd_path)} para validar rLoteDE")
    
    try:
        # Parse XSD - change to the directory containing the XSD so relative includes work
        original_cwd = os.getcwd()
        xsd_dir = os.path.dirname(xsd_path)
        os.chdir(xsd_dir)
        
        try:
            xmlschema_doc = etree.parse(os.path.basename(xsd_path))
            xmlschema = etree.XMLSchema(xmlschema_doc)
        finally:
            os.chdir(original_cwd)
        
        # Parse lote.xml
        lote_doc = etree.parse(lote_file_path)
        
        # Validate
        if xmlschema.validate(lote_doc):
            print(f"✅ XSD OK: lote.xml valida contra {os.path.basename(xsd_path)}")
            sys.exit(0)
        else:
            print(f"❌ XSD FAIL: lote.xml NO valida contra {os.path.basename(xsd_path)}")
            if xmlschema.error_log:
                error = xmlschema.error_log[0]
                print(f"   Linea {error.line}, Columna {error.column}: {error.message}")
            sys.exit(1)
            
    except Exception as e:
        print(f"ERROR during validation: {e}")
        sys.exit(1)


def validate_lote_xsd():
    """Main validation function."""
    # Extract lote.xml if needed
    lote_file = "artifacts/_last_sent_lote.xml"
    if not os.path.exists(lote_file):
        import io
        lote_file = extract_lote_from_soap()
    
    # Find XSD that declares rLoteDE
    xsd_path = find_rlotede_xsd()
    
    # Verificar modo estricto
    strict_mode = os.environ.get('SIFEN_STRICT_LOTE_XSD') == '1'
    
    if not xsd_path:
        if strict_mode:
            print("❌ XSD FAIL: No se encuentra XSD que declare rLoteDE (modo estricto)")
            sys.exit(2)
        else:
            print("⚠️ XSD WARN: No se encuentra XSD que declare rLoteDE (continuando en modo no estricto)")
            return
    
    print(f"✅ XSD OK: Usando {os.path.basename(xsd_path)} para validar rLoteDE")
    
    try:
        # Parse XSD - change to the directory containing the XSD so relative includes work
        original_cwd = os.getcwd()
        xsd_dir = os.path.dirname(xsd_path)
        os.chdir(xsd_dir)
        
        try:
            xmlschema_doc = etree.parse(os.path.basename(xsd_path))
            xmlschema = etree.XMLSchema(xmlschema_doc)
        finally:
            os.chdir(original_cwd)
        
        # Parse lote.xml
        lote_doc = etree.parse(lote_file)
        
        # Validate
        if xmlschema.validate(lote_doc):
            print(f"✅ XSD OK: lote.xml valida contra {os.path.basename(xsd_path)}")
            sys.exit(0)
        else:
            print(f"❌ XSD FAIL: lote.xml NO valida contra {os.path.basename(xsd_path)}")
            if xmlschema.error_log:
                error = xmlschema.error_log[0]
                print(f"   Linea {error.line}, Columna {error.column}: {error.message}")
            sys.exit(1)
            
    except Exception as e:
        print(f"ERROR during validation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    validate_lote_xsd()
