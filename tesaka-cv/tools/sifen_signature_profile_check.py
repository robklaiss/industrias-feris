#!/usr/bin/env python3
"""
Inspector de perfil de firma SIFEN v150
Verifica que la firma cumpla con el perfil esperado por SIFEN
"""

import sys
from pathlib import Path
from lxml import etree

# Perfil esperado según NT16/MT v150
EXPECTED_PROFILE = {
    'signature_parent': 'rDE',
    'canonicalization_method': 'http://www.w3.org/2001/10/xml-exc-c14n#',
    'signature_method': 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
    'digest_method': 'http://www.w3.org/2001/04/xmlenc#sha256',
    'transforms': [
        'http://www.w3.org/2000/09/xmldsig#enveloped-signature'
        # NOTA: xml-exc-c14n# NO va en Transforms según NT16/MT v150
    ]
}

def check_signature_profile(xml_path: Path) -> dict:
    """Analiza el perfil de firma y devuelve resultados"""
    if not xml_path.exists():
        print(f"ERROR: Archivo no encontrado: {xml_path}")
        sys.exit(1)
    
    try:
        with open(xml_path, 'rb') as f:
            root = etree.parse(f).getroot()
    except Exception as e:
        print(f"ERROR: No se pudo parsear XML: {e}")
        sys.exit(1)
    
    # Namespaces
    ns = {
        'ds': 'http://www.w3.org/2000/09/xmldsig#',
        'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'
    }
    
    # Buscar Signature
    signatures = root.xpath('//ds:Signature', namespaces=ns)
    if not signatures:
        print("ERROR: No se encontró ds:Signature")
        sys.exit(1)
    
    signature = signatures[0]
    
    # 1. Verificar parent de Signature
    parent = signature.getparent()
    signature_parent = etree.QName(parent).localname if parent else None
    print(f"Signature parent tag: {signature_parent}")
    
    # 2. Extraer SignedInfo
    signed_info = signature.find('.//ds:SignedInfo', namespaces=ns)
    if signed_info is None:
        print("ERROR: No se encontró SignedInfo")
        sys.exit(1)
    
    # 3. CanonicalizationMethod
    canon_method = signed_info.find('.//ds:CanonicalizationMethod', namespaces=ns)
    canon_algorithm = canon_method.get('Algorithm') if canon_method is not None else None
    print(f"CanonicalizationMethod Algorithm: {canon_algorithm}")
    
    # 4. SignatureMethod
    sig_method = signed_info.find('.//ds:SignatureMethod', namespaces=ns)
    sig_algorithm = sig_method.get('Algorithm') if sig_method is not None else None
    print(f"SignatureMethod Algorithm: {sig_algorithm}")
    
    # 5. Reference y sus componentes
    reference = signed_info.find('.//ds:Reference', namespaces=ns)
    if reference is None:
        print("ERROR: No se encontró Reference")
        sys.exit(1)
    
    ref_uri = reference.get('URI')
    print(f"Reference URI: {ref_uri}")
    
    # 6. DigestMethod
    digest_method = reference.find('.//ds:DigestMethod', namespaces=ns)
    digest_algorithm = digest_method.get('Algorithm') if digest_method is not None else None
    print(f"DigestMethod Algorithm: {digest_algorithm}")
    
    # 7. Transforms
    transforms = reference.find('.//ds:Transforms', namespaces=ns)
    transform_algorithms = []
    if transforms is not None:
        for transform in transforms.findall('.//ds:Transform', namespaces=ns):
            algo = transform.get('Algorithm')
            if algo:
                transform_algorithms.append(algo)
    print(f"Transforms list: {transform_algorithms}")
    
    # 7.1 Verificación NT16/MT v150: SOLO enveloped-signature en Transforms
    if len(transform_algorithms) != 1:
        print(f"❌ ERROR NT16/MT v150: Se espera exactamente 1 Transform, hay {len(transform_algorithms)}")
    elif transform_algorithms[0] != 'http://www.w3.org/2000/09/xmldsig#enveloped-signature':
        print(f"❌ ERROR NT16/MT v150: Transform debe ser enveloped-signature, es {transform_algorithms[0]}")
    else:
        print(f"✅ NT16/MT v150: Transforms correcto (solo enveloped-signature)")
    
    # 8. Orden de hijos de rDE
    rde_elements = root.xpath('//sifen:rDE', namespaces=ns)
    if rde_elements:
        rde = rde_elements[0]
        rde_children = [etree.QName(child).localname for child in rde]
        print(f"rDE children order: {rde_children}")
    else:
        rde_children = []
        print("rDE children order: [] (no rDE found)")
    
    # 9. Verificar DE/@Id para Reference URI
    de_elements = root.xpath('//sifen:DE', namespaces=ns)
    if de_elements:
        de = de_elements[0]
        de_id = de.get('Id')
        expected_ref_uri = f"#{de_id}"
        print(f"DE/@Id: {de_id}")
        print(f"Expected Reference URI: {expected_ref_uri}")
    else:
        de_id = None
        expected_ref_uri = None
        print("DE/@Id: None (no DE found)")
    
    # Resultados
    results = {
        'signature_parent': signature_parent,
        'canonicalization_method': canon_algorithm,
        'signature_method': sig_algorithm,
        'digest_method': digest_algorithm,
        'transforms': transform_algorithms,
        'reference_uri': ref_uri,
        'expected_ref_uri': expected_ref_uri,
        'rde_children': rde_children,
        'de_id': de_id
    }
    
    return results

def main():
    if len(sys.argv) != 2:
        print("USAGE: .venv/bin/python tools/sifen_signature_profile_check.py <archivo.xml>")
        sys.exit(1)
    
    xml_path = Path(sys.argv[1])
    results = check_signature_profile(xml_path)
    
    print("\n" + "="*60)
    print("VERIFICACIÓN CONTRA PERFIL ESPERADO:")
    print("="*60)
    
    # Verificaciones
    all_ok = True
    
    # 1. Parent
    parent_ok = results['signature_parent'] == EXPECTED_PROFILE['signature_parent']
    print(f"✅ Signature parent: {'OK' if parent_ok else 'FAIL'}")
    if not parent_ok:
        print(f"   Expected: {EXPECTED_PROFILE['signature_parent']}")
        print(f"   Got: {results['signature_parent']}")
        all_ok = False
    
    # 2. Canonicalization
    canon_ok = results['canonicalization_method'] == EXPECTED_PROFILE['canonicalization_method']
    print(f"✅ CanonicalizationMethod: {'OK' if canon_ok else 'FAIL'}")
    if not canon_ok:
        print(f"   Expected: {EXPECTED_PROFILE['canonicalization_method']}")
        print(f"   Got: {results['canonicalization_method']}")
        all_ok = False
    
    # 3. SignatureMethod
    sig_ok = results['signature_method'] == EXPECTED_PROFILE['signature_method']
    print(f"✅ SignatureMethod: {'OK' if sig_ok else 'FAIL'}")
    if not sig_ok:
        print(f"   Expected: {EXPECTED_PROFILE['signature_method']}")
        print(f"   Got: {results['signature_method']}")
        all_ok = False
    
    # 4. DigestMethod
    digest_ok = results['digest_method'] == EXPECTED_PROFILE['digest_method']
    print(f"✅ DigestMethod: {'OK' if digest_ok else 'FAIL'}")
    if not digest_ok:
        print(f"   Expected: {EXPECTED_PROFILE['digest_method']}")
        print(f"   Got: {results['digest_method']}")
        all_ok = False
    
    # 5. Transforms
    transforms_ok = results['transforms'] == EXPECTED_PROFILE['transforms']
    print(f"✅ Transforms: {'OK' if transforms_ok else 'FAIL'}")
    if not transforms_ok:
        print(f"   Expected: {EXPECTED_PROFILE['transforms']}")
        print(f"   Got: {results['transforms']}")
        all_ok = False
    
    # 6. Reference URI
    ref_ok = results['reference_uri'] == results['expected_ref_uri']
    print(f"✅ Reference URI: {'OK' if ref_ok else 'FAIL'}")
    if not ref_ok:
        print(f"   Expected: {results['expected_ref_uri']}")
        print(f"   Got: {results['reference_uri']}")
        all_ok = False
    
    print("="*60)
    if all_ok:
        print("🎯 PERFIL CORRECTO - Compatible con SIFEN v150")
        sys.exit(0)
    else:
        print("❌ PERFIL INCORRECTO - No compatible con SIFEN")
        sys.exit(2)

if __name__ == '__main__':
    main()
