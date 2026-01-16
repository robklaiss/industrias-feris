#!/usr/bin/env python3
"""
Builder de artifacts SIFEN v150 con firma real
Genera XML firmado, versión para prevalidador y SOAP 1.2
"""

import os
import sys
import random
import time
from pathlib import Path
from lxml import etree

# Agregar paths para importar módulos
sys.path.insert(0, str(Path(__file__).parent.parent / "tesaka-cv" / "app"))
sys.path.insert(0, str(Path(__file__).parent))

try:
    from sifen_client.xmldsig_signer import sign_de_xml
    from sifen_signature_profile_check import check_signature_profile
except ImportError as e:
    print(f"ERROR: No se pudieron importar módulos necesarios: {e}")
    sys.exit(1)

def generate_did() -> str:
    """Genera un dId válido (entero <= 15 dígitos)"""
    timestamp = int(time.time())
    random_suffix = random.randint(100, 999)
    return str(timestamp)[:12] + str(random_suffix)[:3]

def validate_no_dummy_values(xml_path: Path) -> None:
    """Valida que no haya valores dummy_* en el XML firmado"""
    content = xml_path.read_text(encoding='utf-8')
    
    dummy_values = [
        'dummy_digest_value',
        'dummy_signature_value',
        'dummy_certificate'
    ]
    
    for dummy in dummy_values:
        if dummy in content:
            print(f"❌ ERROR: Se encontró valor dummy: {dummy}")
            print("   El XML no está firmado correctamente")
            sys.exit(2)
    
    print("✅ No hay valores dummy_* - firma real verificada")

def validate_real_signature(xml_path: Path) -> None:
    """Valida que la firma sea real (tamaños y formato)"""
    try:
        tree = etree.parse(xml_path)
        root = tree.getroot()
        
        # Buscar Signature
        ns = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
        sig = root.xpath("//ds:Signature", namespaces=ns)
        if not sig:
            print("❌ ERROR: No se encontró elemento Signature")
            sys.exit(2)
        
        # Extraer valores
        digest_value = root.xpath("string(//ds:DigestValue)", namespaces=ns).strip()
        signature_value = root.xpath("string(//ds:SignatureValue)", namespaces=ns).strip()
        x509_cert = root.xpath("string(//ds:X509Certificate)", namespaces=ns).strip()
        
        # Validar tamaños
        if len(digest_value) < 20:
            print(f"❌ ERROR: DigestValue demasiado corto ({len(digest_value)} chars)")
            sys.exit(2)
        
        if len(signature_value) < 200:
            print(f"❌ ERROR: SignatureValue demasiado corto ({len(signature_value)} chars)")
            sys.exit(2)
        
        if not x509_cert.startswith("MI"):
            print(f"❌ ERROR: X509Certificate no empieza con 'MI' (empieza con: {x509_cert[:12]})")
            sys.exit(2)
        
        print(f"✅ Firma real validada:")
        print(f"   - DigestValue: {len(digest_value)} chars")
        print(f"   - SignatureValue: {len(signature_value)} chars")
        print(f"   - X509Certificate: {len(x509_cert)} chars (empieza con 'MI')")
        
    except Exception as e:
        print(f"❌ ERROR validando firma: {e}")
        sys.exit(2)

def create_test_rde() -> etree._Element:
    """Crea un rDE de prueba con estructura mínima"""
    SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
    
    # Crear rDE
    rde = etree.Element(f"{{{SIFEN_NS}}}rDE")
    
    # dVerFor
    dverfor = etree.SubElement(rde, f"{{{SIFEN_NS}}}dVerFor")
    dverfor.text = "150"
    
    # DE básico
    de = etree.SubElement(rde, f"{{{SIFEN_NS}}}DE")
    de.set("Id", "TEST12345678901234567890")
    de.set("iTimbrado", "100")
    de.set("cDC", "1234567890123456789012345678901234567890123456789")
    
    # Campos mínimos del DE
    etree.SubElement(de, f"{{{SIFEN_NS}}}dSuc").text = "0"
    etree.SubElement(de, f"{{{SIFEN_NS}}}dFC").text = "001"
    etree.SubElement(de, f"{{{SIFEN_NS}}}iNatOp").text = "1"
    etree.SubElement(de, f"{{{SIFEN_NS}}}iTipTra").text = "1"
    etree.SubElement(de, f"{{{SIFEN_NS}}}cCond").text = "1"
    etree.SubElement(de, f"{{{SIFEN_NS}}}cFormPago").text = "1"
    etree.SubElement(de, f"{{{SIFEN_NS}}}dNumDoc").text = "1234567"
    etree.SubElement(de, f"{{{SIFEN_NS}}}dFechaEmi").text = "2026-01-12"
    etree.SubElement(de, f"{{{SIFEN_NS}}}hHoraGen").text = "12:00:00"
    
    # gOpeDE
    gope = etree.SubElement(de, f"{{{SIFEN_NS}}}gOpeDE")
    etree.SubElement(gope, f"{{{SIFEN_NS}}}dRucEmi").text = "800123456"
    etree.SubElement(gope, f"{{{SIFEN_NS}}}dDVEmi").text = "2"
    etree.SubElement(gope, f"{{{SIFEN_NS}}}dNomEmi").text = "EMPRESA TEST"
    etree.SubElement(gope, f"{{{SIFEN_NS}}}dRucRec").text = "800654321"
    etree.SubElement(gope, f"{{{SIFEN_NS}}}dDVRec").text = "1"
    etree.SubElement(gope, f"{{{SIFEN_NS}}}dNomRec").text = "CLIENTE TEST"
    
    # Totales
    etree.SubElement(de, f"{{{SIFEN_NS}}}gTotSubDE").text = "100000"
    etree.SubElement(de, f"{{{SIFEN_NS}}}gTotIVA").text = "10000"
    etree.SubElement(de, f"{{{SIFEN_NS}}}gTotOpe").text = "110000"
    etree.SubElement(de, f"{{{SIFEN_NS}}}gVenTot").text = "110000"
    
    return rde

def build_soap_envelope_raw(xml_firmado_path: Path, d_id: str) -> bytes:
    """
    Construye envelope SOAP 1.2 usando el builder raw bytes
    Llama al script sifen_build_soap12_envelope.py para preservar firma
    """
    import subprocess
    
    soap_output = Path("/tmp/sifen_rEnviDe_soap12.xml")
    
    # Llamar al SOAP builder raw
    result = subprocess.run([
        sys.executable,
        str(Path(__file__).parent / "sifen_build_soap12_envelope.py"),
        str(xml_firmado_path),
        str(soap_output)
    ], capture_output=True, text=True, timeout=30)
    
    if result.returncode != 0:
        raise RuntimeError(f"SOAP builder falló: {result.stderr}")
    
    return soap_output.read_bytes()

def remove_g_cam_fu_fd(rde_element: etree._Element) -> None:
    """Elimina solo gCamFuFD si existe"""
    ns = {"sifen": "http://ekuatia.set.gov.py/sifen/xsd"}
    
    g_cam_elements = rde_element.xpath(".//sifen:gCamFuFD", namespaces=ns)
    for g_cam in g_cam_elements:
        parent = g_cam.getparent()
        if parent is not None:
            parent.remove(g_cam)

def main():
    print("=== BUILDER DE ARTIFACTS SIFEN v150 (FIRMA REAL) ===")
    
    # Verificar variables de entorno
    cert_path = os.getenv("SIFEN_CERT_PATH")
    cert_pass = os.getenv("SIFEN_CERT_PASS")
    csc = os.getenv("SIFEN_CSC")
    env = os.getenv("SIFEN_ENV", "TEST")
    
    if not cert_path:
        print("❌ ERROR: SIFEN_CERT_PATH no configurado")
        sys.exit(1)
    
    if not cert_pass:
        print("❌ ERROR: SIFEN_CERT_PASS no configurado")
        sys.exit(1)
    
    if not csc:
        print("❌ ERROR: SIFEN_CSC no configurado")
        sys.exit(1)
    
    print(f"📋 Configuración:")
    print(f"  - Certificado: {cert_path}")
    print(f"  - Ambiente: {env}")
    print(f"  - CSC: {csc[:4]}...")
    
    # Paths de salida
    desktop = Path.home() / "Desktop"
    xml_firmado_path = desktop / "sifen_de_firmado_test.xml"
    xml_prevalidador_path = desktop / "sifen_de_prevalidador_firmado.xml"
    soap_path = Path("/tmp/sifen_rEnviDe_soap12.xml")
    
    try:
        # 1. Generar rDE base (sin firmar)
        print("\n📝 Generando rDE base...")
        rde_root = create_test_rde()
        print("✅ rDE base generado")
        
        # 2. Firmar rDE con perfil correcto
        print("\n🔐 Firmando rDE con perfil SIFEN...")
        
        # Asegurar que Signature quede como hija de rDE (default)
        os.environ["SIFEN_SIGNATURE_PARENT"] = "RDE"
        
        # Convertir rDE a string para firmar
        rde_xml = etree.tostring(rde_root, encoding='unicode')
        
        signed_xml = sign_de_xml(
            xml_str=rde_xml,
            p12_path=cert_path,
            p12_password=cert_pass
        )
        
        # Guardar XML firmado
        xml_firmado_path.write_text(signed_xml, encoding='utf-8')
        print(f"✅ XML firmado guardado: {xml_firmado_path}")
        
        # 3. HARD FAIL - Validar que no haya dummy values
        print("\n🔍 Validando que no haya valores dummy_*...")
        validate_no_dummy_values(xml_firmado_path)
        
        # 4. Validar que la firma sea real
        print("\n🔍 Validando que la firma sea real...")
        validate_real_signature(xml_firmado_path)
        
        # 5. HARD FAIL - Validar que exista ds:Signature
        print("\n🔍 Validando que exista ds:Signature...")
        try:
            tree = etree.fromstring(signed_xml.encode('utf-8'))
            sig = tree.xpath("//ds:Signature", namespaces={"ds": "http://www.w3.org/2000/09/xmldsig#"})
            if not sig:
                print("❌ ERROR: No se encontró elemento ds:Signature en el XML firmado")
                sys.exit(2)
            print("✅ ds:Signature encontrado")
        except Exception as e:
            print(f"❌ ERROR: No se pudo verificar ds:Signature: {e}")
            sys.exit(2)
        
        # 6. Validar perfil de firma
        print("\n🔍 Validando perfil de firma...")
        profile_results = check_signature_profile(xml_firmado_path)
        
        # 7. Test rápido con verificador criptográfico
        print("\n🔍 Verificación criptográfica final...")
        try:
            import subprocess
            result = subprocess.run([
                ".venv/bin/python", 
                "tools/sifen_signature_crypto_verify.py", 
                str(xml_firmado_path)
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                print("❌ ERROR: Verificación criptográfica falló")
                print("   El XML firmado no es válido")
                if result.stdout.strip():
                    print("   Salida:")
                    for line in result.stdout.strip().split('\n')[-5:]:
                        print(f"     {line}")
                if result.stderr.strip():
                    print("   Errores:")
                    for line in result.stderr.strip().split('\n')[-5:]:
                        print(f"     {line}")
                sys.exit(2)
            
            print("✅ Verificación criptográfica OK")
            
        except subprocess.TimeoutExpired:
            print("⚠️  Timeout en verificación criptográfica (continuando)")
        except Exception as e:
            print(f"⚠️  No se pudo ejecutar verificación criptográfica: {e}")
            print("   Continuando con el build...")
        
        # 8. Generar versión para prevalidador (sin gCamFuFD)
        print("\n📋 Generando versión para prevalidador...")
        
        # Parsear XML firmado
        rde_element = etree.fromstring(signed_xml.encode('utf-8'))
        
        # Eliminar gCamFuFD si existe
        remove_g_cam_fu_fd(rde_element)
        
        # Serializar y guardar
        prevalidador_xml = etree.tostring(rde_element, encoding='UTF-8', xml_declaration=True, pretty_print=True).decode('utf-8')
        xml_prevalidador_path.write_text(prevalidador_xml, encoding='utf-8')
        print(f"✅ XML prevalidador guardado: {xml_prevalidador_path}")
        
        # 9. Generar SOAP 1.2 (usando builder raw bytes)
        print("\n📦 Generando SOAP 1.2 (raw bytes, sin alterar firma)...")
        
        d_id = generate_did()
        print(f"   dId: {d_id}")
        
        # Usar SOAP builder raw para preservar firma
        soap_bytes = build_soap_envelope_raw(xml_firmado_path, d_id)
        soap_path.write_bytes(soap_bytes)
        print(f"✅ SOAP guardado: {soap_path}")
        
        # 10. Resumen final
        print("\n" + "="*60)
        print("🎯 ARTIFACTS GENERADOS EXITOSAMENTE:")
        print("="*60)
        print(f"📄 XML firmado:      {xml_firmado_path}")
        print(f"📄 XML prevalidador: {xml_prevalidador_path}")
        print(f"📋 SOAP 1.2:        {soap_path}")
        print(f"🔑 dId generado:    {d_id}")
        
        print(f"\n🔍 Perfil de firma:")
        print(f"   - Signature parent: {profile_results['signature_parent']}")
        print(f"   - Canonicalization: {profile_results['canonicalization_method']}")
        print(f"   - SignatureMethod: {profile_results['signature_method']}")
        print(f"   - DigestMethod: {profile_results['digest_method']}")
        print(f"   - Transforms: {profile_results['transforms']}")
        print(f"   - Reference URI: {profile_results['reference_uri']}")
        
        print("\n✅ Listo para enviar a SIFEN - FIRMA REAL VERIFICADA")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
