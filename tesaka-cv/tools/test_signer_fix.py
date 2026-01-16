#!/usr/bin/env python3
"""
Test simple del firmador modificado usando XML existente
"""

import os
import sys
from pathlib import Path

# Agregar paths
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

try:
    from sifen_client.xmldsig_signer import sign_de_xml
    from sifen_signature_profile_check import check_signature_profile
except ImportError as e:
    print(f"ERROR: No se pudieron importar módulos: {e}")
    sys.exit(1)

def main():
    print("=== TEST DEL FIRMADOR MODIFICADO ===")
    
    # Configurar variables
    cert_path = "/Users/robinklaiss/.sifen/certs/F1T_65478.p12"
    cert_pass = "F1T65478"  # Asumimos esta contraseña
    
    # Usar XML existente como base
    existing_xml_path = Path.home() / "Desktop" / "sifen_de_firmado_test.xml"
    
    if not existing_xml_path.exists():
        print(f"❌ ERROR: No existe {existing_xml_path}")
        sys.exit(1)
    
    print(f"📂 Usando XML existente: {existing_xml_path}")
    
    try:
        # Leer XML existente
        xml_content = existing_xml_path.read_text(encoding='utf-8')
        print("✅ XML leído")
        
        # Firmar con nuevo perfil (default RDE)
        print("🔐 Firmando con nuevo perfil...")
        os.environ["SIFEN_SIGNATURE_PARENT"] = "RDE"
        
        signed_xml = sign_de_xml(
            xml_str=xml_content,
            p12_path=cert_path,
            p12_password=cert_pass
        )
        
        # Guardar nuevo XML
        output_path = Path.home() / "Desktop" / "sifen_de_firmado_test_fixed.xml"
        output_path.write_text(signed_xml, encoding='utf-8')
        print(f"✅ XML firmado guardado: {output_path}")
        
        # Verificar perfil
        print("\n🔍 Verificando perfil...")
        results = check_signature_profile(output_path)
        
        print(f"\n📋 Resultados:")
        print(f"   - Signature parent: {results['signature_parent']}")
        print(f"   - Canonicalization: {results['canonicalization_method']}")
        print(f"   - SignatureMethod: {results['signature_method']}")
        print(f"   - DigestMethod: {results['digest_method']}")
        print(f"   - Transforms: {results['transforms']}")
        print(f"   - Reference URI: {results['reference_uri']}")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
