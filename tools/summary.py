#!/usr/bin/env python3
"""
Resumen final del fix SIFEN v150
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """Ejecuta comando y muestra resultado"""
    print(f"\n🔍 {description}")
    print(f"   $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("   ✅ OK")
        if result.stdout.strip():
            for line in result.stdout.strip().split('\n')[:5]:
                print(f"   {line}")
    else:
        print(f"   ❌ FAIL (exit {result.returncode})")
        if result.stderr:
            for line in result.stderr.strip().split('\n')[:3]:
                print(f"   {line}")
    
    return result.returncode == 0

def main():
    print("="*70)
    print("🎯 FIX PERMANENTE SIFEN v150 - RESUMEN FINAL")
    print("="*70)
    
    # Paths
    xml_path = Path.home() / "Desktop" / "sifen_de_firmado_test.xml"
    soap_path = Path("/tmp/sifen_rEnviDe_soap12.xml")
    
    print("\n📁 ARTIFACTS GENERADOS:")
    print(f"   • XML firmado: {xml_path}")
    print(f"   • SOAP 1.2: {soap_path}")
    
    # Pruebas de aceptación
    print("\n" + "="*70)
    print("🧪 PRUEBAS DE ACEPTACIÓN")
    print("="*70)
    
    # Test 1: Inspector
    test1_ok = run_command(
        f".venv/bin/python tools/sifen_signature_profile_check.py {xml_path}",
        "Test 1: Inspector de perfil exacto"
    )
    
    # Test 2: Verificar orden
    print(f"\n🔍 Test 2: Verificar orden de elementos")
    print(f"   $ grep -o \"</.*DE><.*Signature.*></.*Signature><.*gCamFuFD\" {xml_path}")
    result = subprocess.run(f"grep -o \"</.*DE><.*Signature.*></.*Signature><.*gCamFuFD\" {xml_path}", 
                          shell=True, capture_output=True, text=True)
    if result.stdout.strip():
        print("   ✅ Orden correcto: </DE> <Signature> ... </Signature> <gCamFuFD>")
        test2_ok = True
    else:
        print("   ❌ Orden incorrecto")
        test2_ok = False
    
    # Test 3: Estructura SOAP
    print(f"\n🔍 Test 3: Verificar estructura SOAP")
    if soap_path.exists():
        soap_content = soap_path.read_text(encoding='utf-8')
        if "<ns1:rDE>" in soap_content and "<ns1:Signature" in soap_content:
            print("   ✅ SOAP contiene rDE con Signature como nodo XML")
            test3_ok = True
        else:
            print("   ❌ SOAP no contiene estructura correcta")
            test3_ok = False
    else:
        print("   ❌ No existe SOAP")
        test3_ok = False
    
    # Resumen
    print("\n" + "="*70)
    print("📊 RESULTADOS")
    print("="*70)
    
    all_tests = test1_ok and test2_ok and test3_ok
    
    if all_tests:
        print("✅ TODAS LAS PRUEBAS PASARON")
        print("\n🎯 FIX IMPLEMENTADO:")
        print("   • Inspector exacto creado")
        print("   • Firmador ajustado (Signature como hijo de rDE)")
        print("   • Orden correcto: dVerFor, DE, Signature, gCamFuFD")
        print("   • Perfil correcto: exc-c14n, rsa-sha256, sha256")
        print("   • KeyInfo: solo certificado leaf")
        print("   • SOAP builder que no rompe la firma")
        
        print("\n🚀 COMANDOS DE ENVÍO:")
        print(f"   .venv/bin/python tools/sifen_send_soap12_mtls.py {soap_path} $SIFEN_CERT_PATH $SIFEN_CERT_PASS")
        
        print("\n📊 RESULTADO ESPERADO:")
        print("   • SIFEN NO debe decir 'El documento XML no tiene firma'")
        print("   • Si hay error, debe ser diferente (negocio/campos)")
        print("   • La firma será reconocida correctamente")
        
    else:
        print("❌ ALGUNAS PRUEBAS FALLARON")
        print("\n🔧 REVISAR:")
        if not test1_ok:
            print("   • Inspector - verificar perfil de firma")
        if not test2_ok:
            print("   • Orden de elementos - debe ser </DE> <Signature> <gCamFuFD>")
        if not test3_ok:
            print("   • SOAP builder - debe insertar XML como nodo")
    
    print("\n" + "="*70)
    
    # Exit code según resultado
    sys.exit(0 if all_tests else 1)

if __name__ == "__main__":
    main()
