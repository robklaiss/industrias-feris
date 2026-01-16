#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIFEN Smoketest - Prueba END-TO-END completa
Ejecuta todo el flujo: generar → firmar → verificar → SOAP → enviar
"""

import sys
import os
import subprocess
from pathlib import Path


def run_step(step_name: str, cmd: list, cwd: str = None) -> subprocess.CompletedProcess:
    """Ejecuta un paso del smoketest y reporta resultado"""
    print(f"\n{'='*60}")
    print(f"🧪 {step_name}")
    print(f"{'='*60}")
    print(f"Comando: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    
    if result.stdout:
        print(result.stdout)
    
    if result.returncode != 0:
        print(f"\n❌ FAIL: {step_name}")
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        return result
    
    print(f"✅ OK: {step_name}")
    return result


def main():
    print("="*60)
    print("🚀 SIFEN SMOKETEST - Flujo END-TO-END")
    print("="*60)
    
    # Verificar variables de entorno
    cert_path = os.getenv("SIFEN_CERT_PATH")
    cert_pass = os.getenv("SIFEN_CERT_PASS")
    
    if not cert_path:
        print("❌ ERROR: SIFEN_CERT_PATH no configurado")
        print("   export SIFEN_CERT_PATH='/path/to/cert.p12'")
        sys.exit(1)
    
    if not cert_pass:
        print("❌ ERROR: SIFEN_CERT_PASS no configurado")
        print("   export SIFEN_CERT_PASS='password'")
        sys.exit(1)
    
    if not Path(cert_path).exists():
        print(f"❌ ERROR: Certificado no existe: {cert_path}")
        sys.exit(1)
    
    print(f"\n📋 Configuración:")
    print(f"   SIFEN_CERT_PATH: {cert_path}")
    print(f"   SIFEN_CERT_PASS: {'*' * len(cert_pass)}")
    
    # Paths
    repo_root = Path(__file__).parent.parent
    tools_dir = repo_root / "tools"
    venv_python = repo_root / ".venv" / "bin" / "python"
    
    xml_firmado = Path.home() / "Desktop" / "sifen_de_firmado_test.xml"
    soap_file = Path("/tmp/sifen_rEnviDe_soap12.xml")
    response_file = Path("/tmp/sifen_rEnviDe_response.xml")
    
    # PASO 1: Generar y firmar XML
    result = run_step(
        "PASO 1: Generar XML firmado con certificado real",
        [str(venv_python), str(tools_dir / "sifen_build_artifacts_real.py")],
        cwd=str(repo_root)
    )
    
    if result.returncode != 0:
        print("\n❌ SMOKETEST FAIL: No se pudo generar XML firmado")
        sys.exit(1)
    
    if not xml_firmado.exists():
        print(f"\n❌ SMOKETEST FAIL: No se generó {xml_firmado}")
        sys.exit(1)
    
    # PASO 2: Verificar firma criptográfica
    result = run_step(
        "PASO 2: Verificar firma criptográfica del XML",
        [str(venv_python), str(tools_dir / "sifen_signature_crypto_verify.py"), str(xml_firmado)],
        cwd=str(repo_root)
    )
    
    if result.returncode != 0:
        print("\n❌ SMOKETEST FAIL: Firma criptográfica inválida")
        sys.exit(1)
    
    # PASO 3: Construir SOAP con selftest
    result = run_step(
        "PASO 3: Construir SOAP (con selftest para verificar que no se altera la firma)",
        [str(venv_python), str(tools_dir / "sifen_build_soap12_envelope.py"), 
         str(xml_firmado), str(soap_file), "--selftest"],
        cwd=str(repo_root)
    )
    
    if result.returncode != 0:
        print("\n❌ SMOKETEST FAIL: SOAP builder falló o alteró la firma")
        sys.exit(1)
    
    if not soap_file.exists():
        print(f"\n❌ SMOKETEST FAIL: No se generó {soap_file}")
        sys.exit(1)
    
    # PASO 4: Enviar a SIFEN TEST con mTLS
    result = run_step(
        "PASO 4: Enviar SOAP a SIFEN TEST (mTLS)",
        [str(venv_python), str(tools_dir / "sifen_send_soap12_mtls.py"), 
         str(soap_file), "--debug"],
        cwd=str(repo_root)
    )
    
    # El sender puede retornar 0 incluso si SIFEN rechaza por negocio
    # Lo importante es que HTTP 200 y response parseable
    
    if not response_file.exists():
        print(f"\n❌ SMOKETEST FAIL: No se guardó respuesta en {response_file}")
        sys.exit(1)
    
    # PASO 5: Parsear respuesta
    print(f"\n{'='*60}")
    print("📊 RESULTADO FINAL")
    print(f"{'='*60}")
    
    try:
        response_content = response_file.read_text(encoding='utf-8')
        
        # Buscar dCodRes y dMsgRes
        if '<dCodRes>' in response_content or '<ns2:dCodRes>' in response_content:
            # Extraer valores
            import re
            cod_match = re.search(r'<(?:ns2:)?dCodRes>(.*?)</(?:ns2:)?dCodRes>', response_content)
            msg_match = re.search(r'<(?:ns2:)?dMsgRes>(.*?)</(?:ns2:)?dMsgRes>', response_content)
            
            cod_res = cod_match.group(1) if cod_match else "N/A"
            msg_res = msg_match.group(1) if msg_match else "N/A"
            
            print(f"✅ Respuesta SIFEN recibida:")
            print(f"   dCodRes: {cod_res}")
            print(f"   dMsgRes: {msg_res}")
            print(f"\n💾 Respuesta completa guardada en: {response_file}")
            
            # Éxito si recibimos respuesta parseable
            print(f"\n{'='*60}")
            print("✅ SMOKETEST COMPLETO - Flujo END-TO-END funcionando")
            print(f"{'='*60}")
            print("\n📋 Archivos generados:")
            print(f"   - XML firmado: {xml_firmado}")
            print(f"   - SOAP envelope: {soap_file}")
            print(f"   - Respuesta SIFEN: {response_file}")
            
            sys.exit(0)
        else:
            print("⚠️  Respuesta no contiene dCodRes/dMsgRes esperados")
            print(f"   Revisar: {response_file}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ ERROR parseando respuesta: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
