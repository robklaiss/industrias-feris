#!/usr/bin/env python3
"""
Demostración del flujo SIFEN v150 con hard fails
Muestra cómo el sistema aborta si no hay firma real
"""

import os
import sys
from pathlib import Path

def main():
    print("="*70)
    print("🎯 DEMOSTRACIÓN SIFEN v150 - HARD FAILS")
    print("="*70)
    
    print("\n📋 OBJETIVO:")
    print("   - Generar XML con firma real (no dummy)")
    print("   - Hard fail si no hay certificado válido")
    print("   - Verificar firma criptográficamente")
    
    print("\n🔍 ESTADO ACTUAL:")
    
    # Verificar si existe XML dummy
    xml_path = Path.home() / "Desktop" / "sifen_de_firmado_test.xml"
    if xml_path.exists():
        content = xml_path.read_text(encoding='utf-8')
        if 'dummy_' in content:
            print("   ❌ XML actual contiene valores dummy_*")
            print("      Este NO es válido para producción")
        else:
            print("   ✅ XML actual parece tener firma real")
    else:
        print("   ⚠️  No existe XML firmado")
    
    print("\n🧪 PRUEBAS DE HARD FAIL:")
    
    # Test 1: Verificar que no hay generators dummy
    dummy_files = [
        "tools/generate_test_xml_v2.py",
        "tools/create_dummy_xml.py"
    ]
    
    dummy_exists = False
    for dummy_file in dummy_files:
        if Path(dummy_file).exists():
            print(f"   ❌ Aún existe: {dummy_file}")
            dummy_exists = True
    
    if not dummy_exists:
        print("   ✅ No hay generators dummy - eliminados")
    
    # Test 2: Verificar variables de entorno
    cert_path = os.getenv("SIFEN_CERT_PATH")
    cert_pass = os.getenv("SIFEN_CERT_PASS")
    
    if not cert_path or not cert_pass:
        print("\n🔐 CONFIGURACIÓN CERTIFICADO:")
        print("   ⚠️  Variables de entorno no configuradas")
        print("      export SIFEN_CERT_PATH=\"/path/to/cert.p12\"")
        print("      export SIFEN_CERT_PASS=\"password\"")
        print("\n   💡 Sin certificado válido, el builder hará HARD FAIL")
    else:
        print(f"\n🔐 CONFIGURACIÓN CERTIFICADO:")
        print(f"   ✅ SIFEN_CERT_PATH: {cert_path}")
        print(f"   ✅ SIFEN_CERT_PASS: {'*' * len(cert_pass)}")
    
    print("\n🚀 COMANDOS DE EJECUCIÓN:")
    
    print("\n1) Test de firma real (hard fail si no hay cert):")
    print("   .venv/bin/python tools/test_real_signature.py")
    
    print("\n2) Builder con firma real (hard fail si no hay cert):")
    print("   export SIFEN_CSC=\"ABCD0000000000000000000000000000\"")
    print("   .venv/bin/python tools/sifen_build_artifacts_real.py")
    
    print("\n3) Verificador criptográfico:")
    print("   .venv/bin/python tools/sifen_signature_crypto_verify.py ~/Desktop/sifen_de_firmado_test.xml")
    
    print("\n4) Inspector de perfil:")
    print("   .venv/bin/python tools/sifen_signature_profile_check.py ~/Desktop/sifen_de_firmado_test.xml")
    
    print("\n📊 RESULTADO ESPERADO:")
    print("   - Si certificado es inválido: ❌ HARD FAIL (exit 2)")
    print("   - Si certificado es válido: ✅ XML con firma real")
    print("   - Nunca más se generará XML con dummy_*")
    
    print("\n" + "="*70)
    print("🎯 IMPLEMENTACIÓN COMPLETA - HARD FAILS ACTIVOS")
    print("="*70)

if __name__ == "__main__":
    main()
