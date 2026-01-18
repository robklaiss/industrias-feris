#!/usr/bin/env python3
"""
Comparar nuestro XML contra especificación exacta de SIFEN.
Buscar diferencias sutiles que puedan causar 0160.
"""
import sys
import zipfile
from lxml import etree

def analyze_lote(zip_path):
    """Analizar lote y buscar posibles causas de 0160."""
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        lote_xml = zf.read('lote.xml')
    
    print("=" * 80)
    print("ANÁLISIS DETALLADO DEL LOTE")
    print("=" * 80)
    print()
    
    # 1. Verificar declaración XML
    print("1. DECLARACIÓN XML")
    if lote_xml.startswith(b'<?xml'):
        decl_end = lote_xml.find(b'?>')
        decl = lote_xml[:decl_end+2].decode('utf-8')
        print(f"   {decl}")
        
        # Verificar comillas
        if "version='1.0'" in decl:
            print("   ⚠ WARNING: Usa comillas simples en version (debería ser dobles)")
        if "encoding='utf-8'" in decl:
            print("   ⚠ WARNING: Usa comillas simples en encoding (debería ser dobles)")
    print()
    
    # 2. Parsear y verificar estructura
    tree = etree.fromstring(lote_xml)
    NS = {'s': 'http://ekuatia.set.gov.py/sifen/xsd', 'ds': 'http://www.w3.org/2000/09/xmldsig#'}
    
    print("2. ESTRUCTURA rLoteDE")
    print(f"   Tag: {tree.tag}")
    print(f"   Namespace: {tree.nsmap.get(None)}")
    
    # Verificar que NO tenga xmlns:ds en el root
    if 'ds' in tree.nsmap:
        print("   ✗ ERROR: rLoteDE tiene xmlns:ds declarado (prohibido por SIFEN)")
    else:
        print("   ✓ OK: rLoteDE no tiene xmlns:ds")
    print()
    
    # 3. Verificar rDE
    rde = tree.find('.//s:rDE', NS)
    if rde is None:
        print("3. ✗ ERROR: No se encontró rDE")
        return
    
    print("3. ESTRUCTURA rDE")
    print(f"   Id: {rde.get('Id')}")
    
    # Verificar atributos de rDE
    attrs = dict(rde.attrib)
    print(f"   Atributos: {list(attrs.keys())}")
    
    # Verificar si tiene xsi:schemaLocation
    xsi_schema = rde.get('{http://www.w3.org/2001/XMLSchema-instance}schemaLocation')
    if xsi_schema:
        print(f"   ⚠ WARNING: Tiene xsi:schemaLocation: {xsi_schema}")
    
    # Verificar orden de hijos
    children = [c.tag.split('}')[-1] for c in rde]
    print(f"   Hijos: {children}")
    
    expected_order = ['dVerFor', 'DE', 'Signature']
    if children[:3] == expected_order:
        print("   ✓ OK: Orden correcto (dVerFor, DE, Signature)")
    else:
        print(f"   ✗ ERROR: Orden incorrecto. Esperado: {expected_order}, actual: {children[:3]}")
    print()
    
    # 4. Verificar Signature en el XML serializado
    print("4. SIGNATURE EN XML SERIALIZADO")
    lote_str = lote_xml.decode('utf-8')
    
    # Buscar el tag Signature exacto
    import re
    sig_match = re.search(r'<Signature[^>]*>', lote_str)
    if sig_match:
        sig_tag = sig_match.group(0)
        print(f"   Tag encontrado: {sig_tag[:100]}")
        
        if 'xmlns="http://www.w3.org/2000/09/xmldsig#"' in sig_tag:
            print("   ✓ OK: Tiene xmlns explícito")
        else:
            print("   ✗ ERROR: NO tiene xmlns explícito")
            
        # Verificar si tiene prefijos ds:
        if 'ds:' in sig_tag:
            print("   ✗ ERROR: Tiene prefijo ds: (prohibido)")
    print()
    
    # 5. Verificar que no haya xmlns:ds en ningún lado
    print("5. VERIFICACIÓN xmlns:ds")
    if b'xmlns:ds=' in lote_xml:
        print("   ✗ ERROR: Encontrado xmlns:ds= en el XML")
        idx = lote_xml.find(b'xmlns:ds=')
        context = lote_xml[max(0, idx-50):idx+100].decode('utf-8', errors='replace')
        print(f"   Contexto: {context}")
    else:
        print("   ✓ OK: No hay xmlns:ds en el XML")
    print()
    
    # 6. Verificar que no haya prefijos ds:
    print("6. VERIFICACIÓN PREFIJOS ds:")
    if b'<ds:' in lote_xml or b'</ds:' in lote_xml:
        print("   ✗ ERROR: Encontrados prefijos ds: en el XML")
        # Contar ocurrencias
        count = lote_xml.count(b'<ds:') + lote_xml.count(b'</ds:')
        print(f"   Total: {count} ocurrencias")
    else:
        print("   ✓ OK: No hay prefijos ds: en el XML")
    print()
    
    # 7. Verificar encoding y caracteres especiales
    print("7. ENCODING Y CARACTERES")
    try:
        lote_xml.decode('utf-8')
        print("   ✓ OK: UTF-8 válido")
    except:
        print("   ✗ ERROR: No es UTF-8 válido")
    
    # Verificar BOM
    if lote_xml.startswith(b'\xef\xbb\xbf'):
        print("   ✗ ERROR: Tiene BOM UTF-8")
    else:
        print("   ✓ OK: Sin BOM")
    
    # Verificar newlines
    if b'\n' in lote_xml or b'\r' in lote_xml:
        print("   ⚠ WARNING: Contiene newlines/returns")
    else:
        print("   ✓ OK: Sin newlines")
    print()
    
    # 8. Verificar tamaño
    print("8. INFORMACIÓN GENERAL")
    print(f"   Tamaño lote.xml: {len(lote_xml)} bytes")
    print(f"   Tamaño ZIP: {zip_path}")
    print()
    
    print("=" * 80)
    print("FIN DEL ANÁLISIS")
    print("=" * 80)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python compare_with_sifen_spec.py <lote.zip>")
        sys.exit(1)
    
    analyze_lote(sys.argv[1])
