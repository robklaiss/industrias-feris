#!/usr/bin/env python3
"""
Inspector exacto de perfil SIFEN v150
Valida estructura y perfil de firma con tolerancia cero
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Tuple

# Namespaces
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
XMLDSIG_NS = "http://www.w3.org/2000/09/xmldsig#"

def check_xml_structure(xml_path: Path) -> Tuple[bool, List[str]]:
    """Valida estructura exacta del XML"""
    errors = []
    
    try:
        # Parsear XML sin pretty print
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # 1. Validar root
        if root.tag != f"{{{SIFEN_NS}}}rDE":
            errors.append(f"Root debe ser rDE en namespace {SIFEN_NS}, got: {root.tag}")
            return False, errors
        
        # 2. Validar children exactos y orden
        children = list(root)
        expected_order = ["dVerFor", "DE", "Signature", "gCamFuFD"]
        
        if len(children) != 4:
            errors.append(f"rDE debe tener exactamente 4 hijos, got: {len(children)}")
            return False, errors
        
        for i, (expected_tag, child) in enumerate(zip(expected_order, children)):
            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            
            if child_tag != expected_tag:
                errors.append(f"Hijo {i}: esperado '{expected_tag}', got '{child_tag}'")
                return False, errors
        
        # 3. Validar DE/@Id
        de_elem = children[1]  # DE
        de_id = de_elem.get("Id")
        if not de_id:
            errors.append("DE debe tener atributo @Id")
            return False, errors
        
        # 4. Validar Signature namespace
        sig_elem = children[2]  # Signature
        sig_ns = sig_elem.tag.split('}')[0] + '}' if '}' in sig_elem.tag else ''
        if sig_ns != f"{{{XMLDSIG_NS}}}":
            errors.append(f"Signature debe usar namespace {XMLDSIG_NS}, got: {sig_ns}")
            return False, errors
        
        # 5. Validar gCamFuFD existe
        gcam_elem = children[3]  # gCamFuFD
        gcam_tag = gcam_elem.tag.split('}')[-1] if '}' in gcam_elem.tag else gcam_elem.tag
        if gcam_tag != "gCamFuFD":
            errors.append("El cuarto hijo debe ser gCamFuFD")
            return False, errors
        
        return True, errors
        
    except ET.ParseError as e:
        errors.append(f"Error parseando XML: {e}")
        return False, errors

def check_signature_profile(xml_path: Path, de_id: str) -> Tuple[bool, List[str]]:
    """Valida perfil exacto de la firma"""
    errors = []
    
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Encontrar Signature
        sig_elem = root.find(f"{{{XMLDSIG_NS}}}Signature")
        if sig_elem is None:
            errors.append("No se encontró elemento Signature")
            return False, errors
        
        # Validar SignedInfo
        signed_info = sig_elem.find(f"{{{XMLDSIG_NS}}}SignedInfo")
        if signed_info is None:
            errors.append("No se encontró SignedInfo")
            return False, errors
        
        # CanonicalizationMethod
        canon = signed_info.find(f"{{{XMLDSIG_NS}}}CanonicalizationMethod")
        if canon is None:
            errors.append("No se encontró CanonicalizationMethod")
            return False, errors
        
        canon_algo = canon.get("Algorithm")
        expected_canon = "http://www.w3.org/2001/10/xml-exc-c14n#"
        if canon_algo != expected_canon:
            errors.append(f"CanonicalizationMethod incorrecto: esperado {expected_canon}, got {canon_algo}")
            return False, errors
        
        # SignatureMethod
        sig_method = signed_info.find(f"{{{XMLDSIG_NS}}}SignatureMethod")
        if sig_method is None:
            errors.append("No se encontró SignatureMethod")
            return False, errors
        
        sig_algo = sig_method.get("Algorithm")
        expected_sig = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
        if sig_algo != expected_sig:
            errors.append(f"SignatureMethod incorrecto: esperado {expected_sig}, got {sig_algo}")
            return False, errors
        
        # Reference
        reference = signed_info.find(f"{{{XMLDSIG_NS}}}Reference")
        if reference is None:
            errors.append("No se encontró Reference")
            return False, errors
        
        ref_uri = reference.get("URI")
        expected_uri = f"#{de_id}"
        if ref_uri != expected_uri:
            errors.append(f"Reference URI incorrecto: esperado {expected_uri}, got {ref_uri}")
            return False, errors
        
        # Transforms
        transforms = reference.find(f"{{{XMLDSIG_NS}}}Transforms")
        if transforms is None:
            errors.append("No se encontró Transforms")
            return False, errors
        
        transform_list = list(transforms.findall(f"{{{XMLDSIG_NS}}}Transform"))
        if len(transform_list) != 2:
            errors.append(f"Transforms debe tener exactamente 2 elementos, got {len(transform_list)}")
            return False, errors
        
        # Validar orden y algoritmos de transforms
        expected_transforms = [
            "http://www.w3.org/2000/09/xmldsig#enveloped-signature",
            "http://www.w3.org/2001/10/xml-exc-c14n#"
        ]
        
        for i, (expected_algo, transform) in enumerate(zip(expected_transforms, transform_list)):
            algo = transform.get("Algorithm")
            if algo != expected_algo:
                errors.append(f"Transform {i}: esperado {expected_algo}, got {algo}")
                return False, errors
        
        # DigestMethod
        digest_method = reference.find(f"{{{XMLDSIG_NS}}}DigestMethod")
        if digest_method is None:
            errors.append("No se encontró DigestMethod")
            return False, errors
        
        digest_algo = digest_method.get("Algorithm")
        expected_digest = "http://www.w3.org/2001/04/xmlenc#sha256"
        if digest_algo != expected_digest:
            errors.append(f"DigestMethod incorrecto: esperado {expected_digest}, got {digest_algo}")
            return False, errors
        
        # KeyInfo - SOLO 1 X509Certificate (leaf)
        key_info = sig_elem.find(f"{{{XMLDSIG_NS}}}KeyInfo")
        if key_info is None:
            errors.append("No se encontró KeyInfo")
            return False, errors
        
        x509_data = key_info.find(f"{{{XMLDSIG_NS}}}X509Data")
        if x509_data is None:
            errors.append("No se encontró X509Data")
            return False, errors
        
        x509_certs = list(x509_data.findall(f"{{{XMLDSIG_NS}}}X509Certificate"))
        if len(x509_certs) != 1:
            errors.append(f"KeyInfo debe tener exactamente 1 X509Certificate, got {len(x509_certs)}")
            return False, errors
        
        return True, errors
        
    except Exception as e:
        errors.append(f"Error validando perfil: {e}")
        return False, errors

def main():
    if len(sys.argv) != 2:
        print("USAGE: .venv/bin/python tools/sifen_signature_profile_check.py <xml_file>")
        sys.exit(1)
    
    xml_path = Path(sys.argv[1])
    if not xml_path.exists():
        print(f"ERROR: No existe {xml_path}")
        sys.exit(1)
    
    print("=== INSPECTOR EXACTO SIFEN v150 ===")
    print(f"📂 Analizando: {xml_path}")
    
    # 1. Validar estructura
    print("\n🔍 Validando estructura...")
    structure_ok, structure_errors = check_xml_structure(xml_path)
    
    if not structure_ok:
        print("❌ ESTRUCTURA INCORRECTA:")
        for error in structure_errors:
            print(f"   - {error}")
        sys.exit(2)
    
    print("✅ Estructura correcta")
    
    # 2. Obtener DE/@Id para validar perfil
    tree = ET.parse(xml_path)
    root = tree.getroot()
    de_elem = root.find(f"{{{SIFEN_NS}}}DE")
    de_id = de_elem.get("Id")
    
    print(f"📋 DE/@Id: {de_id}")
    
    # 3. Validar perfil de firma
    print("\n🔍 Validando perfil de firma...")
    profile_ok, profile_errors = check_signature_profile(xml_path, de_id)
    
    if not profile_ok:
        print("❌ PERFIL INCORRECTO:")
        for error in profile_errors:
            print(f"   - {error}")
        sys.exit(2)
    
    print("✅ Perfil correcto")
    
    # 4. Resumen final
    print("\n" + "="*60)
    print("🎯 VALIDACIÓN EXITOSA - XML 100% COMPATIBLE")
    print("="*60)
    print("✅ Root: rDE")
    print("✅ Children order: dVerFor, DE, Signature, gCamFuFD")
    print("✅ Signature parent: rDE")
    print("✅ CanonicalizationMethod: xml-exc-c14n#")
    print("✅ SignatureMethod: rsa-sha256")
    print("✅ DigestMethod: sha256")
    print("✅ Transforms: [enveloped-signature, xml-exc-c14n]")
    print("✅ Reference URI: #<DE/@Id>")
    print("✅ KeyInfo: 1 X509Certificate (leaf)")
    print("✅ gCamFuFD presente")
    
    print("\n🚀 XML listo para enviar a SIFEN v150")
    sys.exit(0)

if __name__ == "__main__":
    main()
