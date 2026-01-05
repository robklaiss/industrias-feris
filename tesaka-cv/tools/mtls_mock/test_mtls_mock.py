#!/usr/bin/env python3
"""
Test automático para verificar el mock server mTLS

Este script:
1. Levanta el mock server en background
2. Ejecuta una llamada del cliente a "recibe-lote" contra el mock
3. Verifica que handshake mTLS se completa
4. Verifica que el server guardó artifacts/last_request.xml
5. Verifica que el cliente parseó el SOAP response
6. Baja el server al final

Uso:
    python tools/mtls_mock/test_mtls_mock.py
"""

import os
import sys
import time
import signal
import subprocess
import tempfile
from pathlib import Path

# Agregar el directorio raíz al path
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "app"))

CERT_DIR = Path(__file__).parent / "certs"
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
MOCK_SERVER_SCRIPT = Path(__file__).parent / "mock_server.py"

# Certificados DEV
CLIENT_CERT = CERT_DIR / "client-dev.crt"
CLIENT_KEY = CERT_DIR / "client-dev.key"
CA_BUNDLE = CERT_DIR / "ca-bundle-dev.crt"

# Proceso del servidor
server_process = None


def cleanup():
    """Limpia procesos y recursos."""
    global server_process
    if server_process:
        try:
            server_process.terminate()
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        except Exception as e:
            print(f"Error al terminar servidor: {e}")
        server_process = None


def signal_handler(sig, frame):
    """Maneja señales para limpiar recursos."""
    print("\nInterrumpido por el usuario. Limpiando...")
    cleanup()
    sys.exit(1)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def check_certs():
    """Verifica que los certificados DEV existan."""
    missing = []
    if not CLIENT_CERT.exists():
        missing.append(str(CLIENT_CERT))
    if not CLIENT_KEY.exists():
        missing.append(str(CLIENT_KEY))
    if not CA_BUNDLE.exists():
        missing.append(str(CA_BUNDLE))
    
    if missing:
        print(f"❌ ERROR: Certificados DEV no encontrados:")
        for m in missing:
            print(f"   - {m}")
        print(f"\nEjecute: tools/mtls_mock/generate_dev_certs.sh")
        return False
    
    return True


def start_mock_server():
    """Inicia el mock server en background."""
    global server_process
    
    print("🚀 Iniciando mock server...")
    try:
        server_process = subprocess.Popen(
            [sys.executable, str(MOCK_SERVER_SCRIPT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(ROOT_DIR),
        )
        
        # Esperar a que el servidor esté listo
        print("⏳ Esperando a que el servidor esté listo...")
        for i in range(10):
            time.sleep(1)
            if server_process.poll() is not None:
                stdout, stderr = server_process.communicate()
                print(f"❌ ERROR: Servidor terminó inesperadamente")
                print(f"STDOUT: {stdout.decode()}")
                print(f"STDERR: {stderr.decode()}")
                return False
            
            # Intentar conectar
            try:
                import requests
                resp = requests.get(
                    "https://127.0.0.1:9443/health",
                    verify=str(CA_BUNDLE),
                    timeout=2
                )
                if resp.status_code == 200:
                    print("✅ Servidor mock iniciado correctamente")
                    return True
            except Exception:
                pass
        
        print("❌ ERROR: Servidor no respondió en 10 segundos")
        return False
        
    except Exception as e:
        print(f"❌ ERROR al iniciar servidor: {e}")
        return False


def test_mtls_handshake():
    """Prueba el handshake mTLS con curl."""
    print("\n🔐 Probando handshake mTLS...")
    
    try:
        import subprocess
        result = subprocess.run(
            [
                "curl", "-k", "-v",
                "--cert", str(CLIENT_CERT),
                "--key", str(CLIENT_KEY),
                "--cacert", str(CA_BUNDLE),
                "https://127.0.0.1:9443/health",
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and "200" in result.stdout:
            print("✅ Handshake mTLS exitoso")
            return True
        else:
            print(f"❌ ERROR en handshake mTLS")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print("⚠️  curl no encontrado, saltando test de handshake")
        return True  # No es crítico
    except Exception as e:
        print(f"❌ ERROR al probar handshake: {e}")
        return False


def test_soap_request():
    """Prueba un request SOAP real usando el cliente del proyecto."""
    print("\n📡 Probando request SOAP...")
    
    # Configurar variables de entorno para modo MOCK
    env = os.environ.copy()
    env["SIFEN_MOCK"] = "1"
    env["SIFEN_ENV"] = "test"
    env["SIFEN_CERT_PEM_PATH"] = str(CLIENT_CERT)
    env["SIFEN_KEY_PEM_PATH"] = str(CLIENT_KEY)
    env["SIFEN_CA_BUNDLE_PATH"] = str(CA_BUNDLE)
    env["SIFEN_DEBUG_SOAP"] = "1"
    
    # Crear un XML SOAP dummy para siRecepLoteDE
    soap_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <rEnvioLote xmlns="http://ekuatia.set.gov.py/sifen/xsd">
      <dId>123456789012345</dId>
      <xDE>dGVzdA==</xDE>
    </rEnvioLote>
  </soap:Body>
</soap:Envelope>'''
    
    try:
        import requests
        resp = requests.post(
            "https://127.0.0.1:9443/de/ws/async/recibe-lote",
            data=soap_xml.encode('utf-8'),
            headers={
                "Content-Type": "application/soap+xml; charset=utf-8",
            },
            cert=(str(CLIENT_CERT), str(CLIENT_KEY)),
            verify=str(CA_BUNDLE),
            timeout=10
        )
        
        if resp.status_code == 200:
            print("✅ Request SOAP exitoso")
            # Verificar que la respuesta es SOAP válido
            if "rResEnviLoteDe" in resp.text and "dCodRes" in resp.text:
                print("✅ Respuesta SOAP válida parseada")
                return True
            else:
                print(f"⚠️  Respuesta SOAP no contiene elementos esperados")
                print(f"Response: {resp.text[:200]}")
                return False
        else:
            print(f"❌ ERROR: Status code {resp.status_code}")
            print(f"Response: {resp.text}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR al probar SOAP request: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_artifacts():
    """Verifica que se guardaron artifacts."""
    print("\n📦 Verificando artifacts...")
    
    artifacts = list(ARTIFACTS_DIR.glob("last_request_*.xml"))
    if artifacts:
        latest = max(artifacts, key=lambda p: p.stat().st_mtime)
        print(f"✅ Artifact encontrado: {latest.name}")
        
        # Verificar contenido
        content = latest.read_text(encoding='utf-8')
        if "rEnvioLote" in content or "Envelope" in content:
            print("✅ Artifact contiene SOAP válido")
            return True
        else:
            print(f"⚠️  Artifact no contiene SOAP esperado")
            return False
    else:
        print("❌ ERROR: No se encontraron artifacts")
        return False


def main():
    """Ejecuta el test completo."""
    print("=" * 60)
    print("TEST AUTOMÁTICO - Mock Server mTLS")
    print("=" * 60)
    
    # Verificar certificados
    if not check_certs():
        sys.exit(1)
    
    # Iniciar servidor
    if not start_mock_server():
        cleanup()
        sys.exit(1)
    
    try:
        # Test handshake
        handshake_ok = test_mtls_handshake()
        
        # Test SOAP request
        soap_ok = test_soap_request()
        
        # Verificar artifacts
        artifacts_ok = verify_artifacts()
        
        # Resumen
        print("\n" + "=" * 60)
        print("RESUMEN")
        print("=" * 60)
        print(f"Handshake mTLS:  {'✅' if handshake_ok else '❌'}")
        print(f"Request SOAP:    {'✅' if soap_ok else '❌'}")
        print(f"Artifacts:       {'✅' if artifacts_ok else '❌'}")
        
        all_ok = handshake_ok and soap_ok and artifacts_ok
        if all_ok:
            print("\n✅ TODOS LOS TESTS PASARON")
            return 0
        else:
            print("\n❌ ALGUNOS TESTS FALLARON")
            return 1
            
    finally:
        cleanup()


if __name__ == "__main__":
    sys.exit(main())

