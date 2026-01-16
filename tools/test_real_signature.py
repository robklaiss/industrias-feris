#!/usr/bin/env python3
"""
Test de firma real SIFEN v150
Intenta firmar con certificado real y hace hard fail si no puede
"""

import os
import sys
from pathlib import Path

# Agregar paths
sys.path.insert(0, str(Path(__file__).parent.parent / "tesaka-cv" / "app"))

def main():
    print("=== TEST DE FIRMA REAL SIFEN v150 ===")
    
    # Verificar variables de entorno
    cert_path = os.getenv("SIFEN_CERT_PATH")
    cert_pass = os.getenv("SIFEN_CERT_PASS")
    
    if not cert_path:
        print("❌ ERROR: SIFEN_CERT_PATH no configurado")
        print("   Ejemplo: export SIFEN_CERT_PATH=\"/path/to/cert.p12\"")
        sys.exit(2)
    
    if not cert_pass:
        print("❌ ERROR: SIFEN_CERT_PASS no configurado")
        print("   Ejemplo: export SIFEN_CERT_PASS=\"password\"")
        sys.exit(2)
    
    print(f"📋 Certificado: {cert_path}")
    
    # Verificar que existe el certificado
    if not Path(cert_path).exists():
        print(f"❌ ERROR: No existe el certificado {cert_path}")
        sys.exit(2)
    
    # Intentar firmar
    try:
        from sifen_client.xmldsig_signer import sign_de_xml
        from sifen_signature_crypto_verify import main as verify_main
        
        # XML de prueba mínimo
        test_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<ns0:rDE xmlns:ns0="http://ekuatia.set.gov.py/sifen/xsd">
  <ns0:dVerFor>150</ns0:dVerFor>
  <ns0:DE Id="TEST12345678901234567890" iTimbrado="100" cDC="1234567890123456789012345678901234567890123456789">
    <ns0:dSuc>0</ns0:dSuc>
    <ns0:dFC>001</ns0:dFC>
    <ns0:iNatOp>1</ns0:iNatOp>
    <ns0:iTipTra>1</ns0:iTipTra>
    <ns0:cCond>1</ns0:cCond>
    <ns0:cFormPago>1</ns0:cFormPago>
    <ns0:dNumDoc>1234567</ns0:dNumDoc>
    <ns0:dFechaEmi>2026-01-12</ns0:dFechaEmi>
    <ns0:hHoraGen>12:00:00</ns0:hHoraGen>
    <ns0:gOpeDE>
      <ns0:dRucEmi>800123456</ns0:dRucEmi>
      <ns0:dDVEmi>2</ns0:dDVEmi>
      <ns0:dNomEmi>EMPRESA TEST</ns0:dNomEmi>
      <ns0:dRucRec>800654321</ns0:dRucRec>
      <ns0:dDVRec>1</ns0:dDVRec>
      <ns0:dNomRec>CLIENTE TEST</ns0:dNomRec>
    </ns0:gOpeDE>
    <ns0:gTotSubDE>100000</ns0:gTotSubDE>
    <ns0:gTotIVA>10000</ns0:gTotIVA>
    <ns0:gTotOpe>110000</ns0:gTotOpe>
    <ns0:gVenTot>110000</ns0:gVenTot>
  </ns0:DE>
</ns0:rDE>'''
        
        print("\n🔐 Intentando firmar XML de prueba...")
        
        # Firmar
        signed_xml = sign_de_xml(
            xml_str=test_xml,
            p12_path=cert_path,
            p12_password=cert_pass
        )
        
        # Guardar temporal
        temp_path = Path("/tmp/test_signed.xml")
        temp_path.write_text(signed_xml, encoding='utf-8')
        print(f"✅ XML firmado guardado: {temp_path}")
        
        # Verificar que sea firma real
        print("\n🔍 Verificando firma...")
        
        # Guardar sys.argv para el verificador
        original_argv = sys.argv
        sys.argv = ["sifen_signature_crypto_verify.py", str(temp_path)]
        
        try:
            # Ejecutar verificador
            verify_main()
            print("\n✅ FIRMA REAL EXITOSA")
            print("   El certificado y clave son válidos")
            
            # Copiar al Desktop
            desktop_path = Path.home() / "Desktop" / "sifen_de_firmado_test.xml"
            desktop_path.write_text(signed_xml, encoding='utf-8')
            print(f"✅ Copiado a: {desktop_path}")
            
        except SystemExit as e:
            if e.code != 0:
                print("\n❌ ERROR: La firma generada no es válida")
                print("   Puede ser problema del certificado o la clave")
                sys.exit(2)
        finally:
            sys.argv = original_argv
        
        # Limpiar
        temp_path.unlink(missing_ok=True)
        
    except ImportError as e:
        print(f"❌ ERROR: No se pudo importar módulos: {e}")
        sys.exit(2)
    except Exception as e:
        print(f"❌ ERROR: No se pudo firmar el XML")
        print(f"   Detalles: {e}")
        print("\n🔧 Posibles soluciones:")
        print("   1. Verificar que el certificado P12 sea válido")
        print("   2. Verificar la contraseña del certificado")
        print("   3. Verificar que el certificado tenga clave privada")
        sys.exit(2)

if __name__ == "__main__":
    main()
