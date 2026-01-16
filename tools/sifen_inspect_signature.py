#!/usr/bin/env python3
"""
Herramienta de inspección de firma XMLDSig para SIFEN

Analiza un XML firmado y muestra información detallada sobre:
- Ubicación de ds:Signature (parent)
- Reference URI y su relación con DE/@Id
- Estructura del XML
- Validaciones básicas de SIFEN

Uso:
    python tools/sifen_inspect_signature.py <archivo.xml>
"""

import sys
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import lxml.etree as etree
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False
    print("ERROR: lxml no está disponible. Instale con: pip install lxml")
    sys.exit(1)

# Namespaces
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"

def inspect_xml_signature(xml_path: Path) -> Dict[str, Any]:
    """
    Inspecciona la firma XMLDSig en un archivo XML.
    
    Args:
        xml_path: Ruta al archivo XML
        
    Returns:
        Diccionario con información de la inspección
    """
    if not xml_path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {xml_path}")
    
    # Parsear XML
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        
        root = etree.fromstring(xml_content.encode('utf-8'))
    except Exception as e:
        raise ValueError(f"Error al parsear XML: {e}")
    
    result = {
        'xml_path': str(xml_path),
        'root_element': etree.QName(root).localname,
        'signature_found': False,
        'signature_parent': None,
        'signature_location': None,
        'de_found': False,
        'de_id': None,
        'reference_uri': None,
        'reference_matches_de_id': False,
        'signature_structure': {},
        'xml_structure': [],
        'issues': []
    }
    
    # Analizar estructura general del XML
    for child in root:
        qname = etree.QName(child)
        result['xml_structure'].append(qname.localname)
    
    # Buscar elemento DE
    de_elements = root.xpath("//sifen:DE", namespaces={"sifen": SIFEN_NS})
    if not de_elements:
        # Intentar sin namespace
        de_elements = root.xpath("//DE")
    
    if de_elements:
        result['de_found'] = True
        de_elem = de_elements[0]
        result['de_id'] = de_elem.get("Id") or de_elem.get("id")
        
        if not result['de_id']:
            result['issues'].append("Elemento DE no tiene atributo Id")
    else:
        result['issues'].append("No se encontró elemento DE")
    
    # Buscar ds:Signature
    ns = {"ds": DS_NS}
    signatures = root.xpath("//ds:Signature", namespaces=ns)
    
    if signatures:
        result['signature_found'] = True
        signature = signatures[0]
        
        # Determinar parent de Signature
        parent = signature.getparent()
        if parent is not None:
            parent_qname = etree.QName(parent)
            result['signature_parent'] = parent_qname.localname
            
            # Ubicación relativa
            if parent_qname.localname == "rDE":
                result['signature_location'] = "Signature como hijo de rDE (fuera de DE)"
            elif parent_qname.localname == "DE":
                result['signature_location'] = "Signature como hijo de DE (enveloped)"
            else:
                result['signature_location'] = f"Signature como hijo de {parent_qname.localname}"
        
        # Extraer Reference URI
        ref_uris = signature.xpath(".//ds:Reference/@URI", namespaces=ns)
        if ref_uris:
            result['reference_uri'] = ref_uris[0]
            
            # Verificar si coincide con DE/@Id
            if result['de_id'] and result['reference_uri'] == f"#{result['de_id']}":
                result['reference_matches_de_id'] = True
            else:
                result['issues'].append(
                    f"Reference URI '{result['reference_uri']}' no coincide con DE/@Id '#{result['de_id']}'"
                )
        else:
            result['issues'].append("No se encontró Reference/@URI en Signature")
        
        # Analizar estructura interna de Signature
        sig_info = {}
        
        # SignedInfo
        signed_info = signature.xpath(".//ds:SignedInfo", namespaces=ns)
        if signed_info:
            sig_info['signed_info_found'] = True
            
            # CanonicalizationMethod
            c14n_methods = signed_info[0].xpath(".//ds:CanonicalizationMethod/@Algorithm", namespaces=ns)
            if c14n_methods:
                sig_info['canonicalization_method'] = c14n_methods[0]
            
            # SignatureMethod
            sig_methods = signed_info[0].xpath(".//ds:SignatureMethod/@Algorithm", namespaces=ns)
            if sig_methods:
                sig_info['signature_method'] = sig_methods[0]
            
            # Reference
            references = signed_info[0].xpath(".//ds:Reference", namespaces=ns)
            if references:
                ref = references[0]
                sig_info['reference_uri'] = ref.get("URI")
                
                # DigestMethod
                digest_methods = ref.xpath(".//ds:DigestMethod/@Algorithm", namespaces=ns)
                if digest_methods:
                    sig_info['digest_method'] = digest_methods[0]
                
                # Transforms
                transforms = ref.xpath(".//ds:Transforms/ds:Transform/@Algorithm", namespaces=ns)
                if transforms:
                    sig_info['transforms'] = transforms
        
        # SignatureValue
        sig_values = signature.xpath(".//ds:SignatureValue", namespaces=ns)
        if sig_values:
            sig_info['signature_value_found'] = True
            if sig_values[0].text:
                sig_info['signature_value_length'] = len(sig_values[0].text.strip())
        
        # KeyInfo
        key_infos = signature.xpath(".//ds:KeyInfo", namespaces=ns)
        if key_infos:
            sig_info['key_info_found'] = True
            
            # X509Certificate
            x509_certs = key_infos[0].xpath(".//ds:X509Certificate", namespaces=ns)
            if x509_certs:
                sig_info['x509_certificates_count'] = len(x509_certs)
        
        result['signature_structure'] = sig_info
    else:
        result['issues'].append("No se encontró ds:Signature en el XML")
    
    return result

def print_inspection_result(result: Dict[str, Any]) -> None:
    """Imprime el resultado de la inspección en formato legible."""
    print(f"\n📄 INSPECCIÓN DE FIRMA SIFEN")
    print(f"📁 Archivo: {result['xml_path']}")
    print(f"🏗️  Elemento raíz: {result['root_element']}")
    print(f"📋 Estructura XML: {' → '.join(result['xml_structure'])}")
    
    print(f"\n🔍 ELEMENTO DE:")
    print(f"   ✅ Encontrado: {'Sí' if result['de_found'] else 'No'}")
    if result['de_found']:
        print(f"   🆔 ID: {result['de_id'] or 'No tiene'}")
    
    print(f"\n✍️  FIRMA DIGITAL:")
    print(f"   ✅ Encontrada: {'Sí' if result['signature_found'] else 'No'}")
    
    if result['signature_found']:
        print(f"   👆 Parent: {result['signature_parent'] or 'Desconocido'}")
        print(f"   📍 Ubicación: {result['signature_location'] or 'Desconocida'}")
        print(f"   🔗 Reference URI: {result['reference_uri'] or 'No encontrada'}")
        print(f"   ✅ Coincide con DE/@Id: {'Sí' if result['reference_matches_de_id'] else 'No'}")
        
        # Estructura de la firma
        sig_struct = result['signature_structure']
        print(f"\n📊 Estructura de la firma:")
        print(f"   📝 SignedInfo: {'✅' if sig_struct.get('signed_info_found') else '❌'}")
        if sig_struct.get('canonicalization_method'):
            print(f"      🔧 CanonicalizationMethod: {sig_struct['canonicalization_method']}")
        if sig_struct.get('signature_method'):
            print(f"      🔐 SignatureMethod: {sig_struct['signature_method']}")
        if sig_struct.get('digest_method'):
            print(f"      🔑 DigestMethod: {sig_struct['digest_method']}")
        if sig_struct.get('transforms'):
            print(f"      🔄 Transforms: {', '.join(sig_struct['transforms'])}")
        
        print(f"   📝 SignatureValue: {'✅' if sig_struct.get('signature_value_found') else '❌'}")
        if sig_struct.get('signature_value_length'):
            print(f"      📏 Longitud: {sig_struct['signature_value_length']} caracteres")
        
        print(f"   🔑 KeyInfo: {'✅' if sig_struct.get('key_info_found') else '❌'}")
        if sig_struct.get('x509_certificates_count'):
            print(f"      📜 Certificados X509: {sig_struct['x509_certificates_count']}")
    
    # Problemas detectados
    if result['issues']:
        print(f"\n⚠️  PROBLEMAS DETECTADOS:")
        for i, issue in enumerate(result['issues'], 1):
            print(f"   {i}. {issue}")
    else:
        print(f"\n✅ No se detectaron problemas")
    
    # Veredicto SIFEN
    print(f"\n🎯 VEREDICTO SIFEN:")
    if not result['signature_found']:
        print("   ❌ RECHAZADO: No tiene firma digital")
    elif result['signature_parent'] != 'DE':
        print("   ❌ RECHAZADO: La firma está fuera del elemento DE")
        print("   💡 SIFEN espera: Signature como hijo de DE (enveloped signature)")
    elif not result['reference_matches_de_id']:
        print("   ❌ RECHAZADO: Reference URI no apunta al DE/@Id")
    else:
        print("   ✅ APROBADO: Estructura de firma compatible con SIFEN")

def main():
    parser = argparse.ArgumentParser(
        description="Inspeccionar firma XMLDSig en archivos SIFEN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
    python tools/sifen_inspect_signature.py ~/Desktop/sifen_de_firmado_test.xml
    python tools/sifen_inspect_signature.py /tmp/factura_firmada.xml
        """
    )
    
    parser.add_argument(
        "xml_file",
        type=Path,
        help="Archivo XML a inspeccionar"
    )
    
    args = parser.parse_args()
    
    try:
        result = inspect_xml_signature(args.xml_file)
        print_inspection_result(result)
        
        # Exit code según resultado
        if result['issues'] and not result['signature_found']:
            sys.exit(1)
        elif result['signature_parent'] != 'DE':
            sys.exit(2)
        elif not result['reference_matches_de_id']:
            sys.exit(3)
        else:
            sys.exit(0)
            
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
