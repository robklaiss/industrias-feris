#!/usr/bin/env python3
"""
Script de diagnóstico completo para error SIFEN 0160 "XML Mal Formado"
Verifica todas las reglas conocidas del knowledge base
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

def diagnose_xml_0160(xml_file: str):
    """Diagnostica XML según reglas SIFEN para error 0160"""
    
    print(f"=== DIAGNÓSTICO SIFEN 0160: {xml_file} ===\n")
    
    # Leer archivo
    try:
        with open(xml_file, 'rb') as f:
            xml_bytes = f.read()
    except Exception as e:
        print(f"❌ Error leyendo archivo: {e}")
        return False
    
    # 1. Verificar whitespace (regla principal)
    print("1️⃣ VERIFICANDO WHITESPACE:")
    has_newlines = b'\n' in xml_bytes
    has_carriage = b'\r' in xml_bytes
    has_tabs = b'\t' in xml_bytes
    
    print(f"   - Contiene \\n: {has_newlines}")
    print(f"   - Contiene \\r: {has_carriage}")
    print(f"   - Contiene \\t: {has_tabs}")
    
    if has_newlines or has_carriage or has_tabs:
        print("   ❌ ERROR: XML contiene whitespace prohibido")
        print("   Regla SIFEN: 'NO incorporar: line-feed, carriage return, tab, espacios entre etiquetas'")
    else:
        print("   ✅ OK: Sin whitespace prohibido")
    
    # 2. Verificar XML declaration
    print("\n2️⃣ VERIFICANDO XML DECLARATION:")
    has_xml_decl = xml_bytes.startswith(b'<?xml')
    print(f"   - Tiene XML declaration: {has_xml_decl}")
    
    if has_xml_decl:
        print("   ❌ ERROR: XML no debe tener declaration (agrega \\n)")
    else:
        print("   ✅ OK: Sin XML declaration")
    
    # 3. Parsear XML
    try:
        root = ET.fromstring(xml_bytes)
        print("\n3️⃣ XML BIEN FORMADO: ✅")
    except Exception as e:
        print(f"\n3️⃣ XML BIEN FORMADO: ❌ {e}")
        return False
    
    # 4. Verificar estructura
    print("\n4️⃣ VERIFICANDO ESTRUCTURA:")
    NS = {'s': 'http://ekuatia.set.gov.py/sifen/xsd', 'ds': 'http://www.w3.org/2000/09/xmldsig#'}
    
    # Verificar root
    if root.tag.endswith('rLoteDE'):
        print("   - Root es rLoteDE: ✅")
    else:
        print(f"   - Root es {root.tag}: ❌")
    
    # Verificar rDE
    rde = root.find('.//s:rDE', NS)
    if rde is not None:
        print("   - Tiene rDE: ✅")
        
        # Verificar hijos de rDE en orden correcto
        children = list(rde)
        child_names = [c.tag.split('}')[-1] for c in children]
        print(f"   - Hijos de rDE: {child_names}")
        
        # Verificar dVerFor primero
        if child_names and child_names[0] == 'dVerFor':
            print("   - dVerFor es primero: ✅")
        else:
            print("   - dVerFor no es primero: ❌")
        
        # Verificar orden: dVerFor, DE, Signature, gCamFuFD
        expected_order = ['dVerFor', 'DE', 'Signature', 'gCamFuFD']
        if child_names == expected_order:
            print("   - Orden correcto: ✅")
        else:
            print(f"   - Orden incorrecto: ❌ (esperado: {expected_order})")
        
        # Verificar DE
        de = rde.find('.//s:DE', NS)
        if de is not None:
            de_id = de.get('Id')
            print(f"   - DE tiene Id: {de_id} ✅")
        else:
            print("   - No tiene DE: ❌")
        
        # Verificar Signature
        sig = rde.find('.//ds:Signature', NS)
        if sig is not None:
            print("   - Tiene Signature: ✅")
            
            # Verificar que Signature no tenga prefijo ds:
            sig_str = ET.tostring(sig, encoding='unicode')
            if '<ds:' in sig_str:
                print("   - Signature tiene prefijo ds: ❌")
            else:
                print("   - Signature sin prefijo ds: ✅")
        else:
            print("   - No tiene Signature: ❌")
        
        # Verificar gCamFuFD
        gcam = rde.find('.//s:gCamFuFD', NS)
        if gcam is not None:
            print("   - Tiene gCamFuFD: ✅")
        else:
            print("   - No tiene gCamFuFD: ❌")
    
    # 5. Verificar comentarios
    print("\n5️⃣ VERIFICANDO COMENTARIOS:")
    if b'<!--' in xml_bytes:
        print("   ❌ ERROR: XML contiene comentarios")
    else:
        print("   ✅ OK: Sin comentarios")
    
    # 6. Verificar xsi:
    print("\n6️⃣ VERIFICANDO ATRIBUTOS XSI:")
    if b'xsi:' in xml_bytes or b'schemaLocation' in xml_bytes:
        print("   ❌ ERROR: XML contiene atributos xsi:")
    else:
        print("   ✅ OK: Sin atributos xsi:")
    
    # 7. Verificar espacios en valores numéricos
    print("\n7️⃣ VERIFICANDO ESPACIOS EN VALORES:")
    xml_str = xml_bytes.decode('utf-8')
    import re
    
    # Buscar valores numéricos con espacios
    numeric_with_spaces = re.findall(r'<[^>]*>[^<]*\s+\d[^<]*</[^>]*>', xml_str)
    if numeric_with_spaces:
        print(f"   ❌ ERROR: {len(numeric_with_spaces)} valores numéricos con espacios")
    else:
        print("   ✅ OK: Valores numéricos sin espacios")
    
    # 8. Verificar firma con xmlsec1
    print("\n8️⃣ VERIFICANDO FIRMA XML:")
    import subprocess
    try:
        result = subprocess.run(
            ['xmlsec1', '--verify', '--insecure', '--id-attr:Id', 'DE', xml_file],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("   ✅ Firma válida")
        else:
            print(f"   ❌ Firma inválida: {result.stderr.strip()}")
    except Exception as e:
        print(f"   ❌ Error verificando firma: {e}")
    
    # Resumen
    print("\n=== RESUMEN ===")
    print("Si todo está en ✅ excepto la firma, el problema puede ser:")
    print("1. SIFEN requiere un formato específico no documentado")
    print("2. El certificado no está habilitado para facturación electrónica")
    print("3. Problema de configuración en el ambiente de prueba")
    
    return True

def main():
    if len(sys.argv) != 2:
        print("Uso: python diagnose_sifen_0160.py <archivo.xml>")
        sys.exit(1)
    
    xml_file = sys.argv[1]
    if not Path(xml_file).exists():
        print(f"❌ Archivo no encontrado: {xml_file}")
        sys.exit(1)
    
    diagnose_xml_0160(xml_file)

if __name__ == "__main__":
    main()
