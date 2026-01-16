#!/usr/bin/env python3
"""
Builder de artifacts SIFEN v150 con firma corregida
Genera XML firmado, versión para prevalidador y SOAP 1.2
"""

import os
import sys
import random
import time
from pathlib import Path
from lxml import etree

# Agregar paths para importar módulos
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tesaka-cv" / "tools"))

try:
    from sifen_client.xmldsig_signer import sign_de_xml
    from sifen_client.exceptions import SifenClientError
    from sifen_signature_profile_check import check_signature_profile
except ImportError as e:
    print(f"ERROR: No se pudieron importar módulos necesarios: {e}")
    sys.exit(1)

def generate_did() -> str:
    """Genera un dId válido (entero <= 15 dígitos)"""
    # Usar timestamp + random para evitar colisiones
    timestamp = int(time.time())
    random_suffix = random.randint(100, 999)
    return str(timestamp)[:12] + str(random_suffix)[:3]

def validate_dnum_doc(rde_element: etree._Element) -> None:
    """Valida que dNumDoc tenga maxLength 7"""
    ns = {"sifen": "http://ekuatia.set.gov.py/sifen/xsd"}
    
    # Buscar dNumDoc en cualquier parte del rDE
    dnumdoc_elements = rde_element.xpath(".//sifen:dNumDoc", namespaces=ns)
    
    for dnumdoc in dnumdoc_elements:
        if dnumdoc.text and len(dnumdoc.text) > 7:
            raise ValueError(f"dNumDoc demasiado largo: {dnumdoc.text} (maxLength: 7)")

def build_soap_envelope(rde_element: etree._Element, d_id: str) -> bytes:
    """Construye envelope SOAP 1.2 con rDE como nodo XML real"""
    # Namespaces
    SOAP12_NS = "http://www.w3.org/2003/05/soap-envelope"
    SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
    
    # Crear envelope
    envelope = etree.Element(etree.QName(SOAP12_NS, "Envelope"))
    etree.SubElement(envelope, etree.QName(SOAP12_NS, "Header"))
    
    # Body con rEnviDe
    body = etree.SubElement(envelope, etree.QName(SOAP12_NS, "Body"))
    r_envi_de = etree.SubElement(body, etree.QName(SIFEN_NS, "rEnviDe"))
    
    # dId
    d_id_elem = etree.SubElement(r_envi_de, etree.QName(SIFEN_NS, "dId"))
    d_id_elem.text = d_id
    
    # xDE conteniendo rDE como nodo XML real
    xde_elem = etree.SubElement(r_envi_de, etree.QName(SIFEN_NS, "xDE"))
    xde_elem.append(rde_element)
    
    # Serializar
    return etree.tostring(envelope, encoding='UTF-8', xml_declaration=True, pretty_print=False)

def remove_g_cam_fu_fd(rde_element: etree._Element) -> None:
    """Elimina solo gCamFuFD si existe"""
    ns = {"sifen": "http://ekuatia.set.gov.py/sifen/xsd"}
    
    g_cam_elements = rde_element.xpath(".//sifen:gCamFuFD", namespaces=ns)
    for g_cam in g_cam_elements:
        parent = g_cam.getparent()
        if parent is not None:
            parent.remove(g_cam)

def main():
    print("=== BUILDER DE ARTIFACTS SIFEN v150 ===")
    
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
        
        # Importar generador DE desde smoketest
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from smoketest import generate_de_python
            
            # Datos de ejemplo para generar DE
            input_data = {
                "tiDE": 1,
                "dVerFor": 150,
                "iTimbrado": 100,
                "cDC": "1234567890123456789012345678901234567890123456789",
                "dSuc": 0,
                "cFC": "001",
                "iNatOp": 1,
                "iTipTra": 1,
                "cCond": 1,
                "cFormPago": 1,
                "dNumDoc": "1234567",
                "dFechaEmi": "2026-01-12",
                "hHoraGen": "12:00:00",
                "gOpeDE": {
                    "dRucEmi": "800123456",
                    "dDVEmi": "2",
                    "dNomEmi": "EMPRESA TEST",
                    "dNomComEmi": "EMPRESA TEST S.A.",
                    "dDirEmi": "DIRECCION TEST",
                    "cDepEmi": "1",
                    "cDisEmi": "1",
                    "cCiuEmi": "1",
                    "cPaisEmi": "PRY",
                    "cTelEmi": "521123456",
                    "cEmailEmi": "test@test.com",
                    "dRucRec": "800654321",
                    "dDVRec": "1",
                    "dNomRec": "CLIENTE TEST",
                    "dNomComRec": "CLIENTE TEST S.A.",
                    "dDirRec": "DIRECCION CLIENTE",
                    "cDepRec": "1",
                    "cDisRec": "1",
                    "cCiuRec": "1",
                    "cPaisRec": "PRY",
                    "cTelRec": "521987654",
                    "cEmailRec": "cliente@test.com"
                },
                "gValorRefeDE": {
                    "dMonRef": "PYG",
                    "dValRef": 100000,
                    "dValRefOpe": 100000
                },
                "gCamDE": {
                    "dCamFE": 1,
                    "dCamIVA": 10,
                    "dCamInc": 1
                },
                "gTotSubDE": 100000,
                "gTotIVA": 10000,
                "gTotInc": 1000,
                "gTotOpe": 111000,
                "gTotGralOpe": 111000,
                "gTotDesc": 0,
                "gTotDescGral": 0,
                "gTotAnt": 0,
                "gTotAntGral": 0,
                "gTolOpe": 0,
                "gTolOpeGral": 0,
                "gVenTot": 111000,
                "gVenTotGral": 111000,
                "gComPE": 0,
                "gComPEM": 0,
                "gComPETot": 0,
                "gComPETotM": 0,
                "gCamItem": [
                    {
                        "iSecItem": 1,
                        "dDesItem": "ITEM DE PRUEBA",
                        "cCodItem": "TEST001",
                        "dCantPro": 1,
                        "dUPro": 100000,
                        "dPUniPro": 100000,
                        "dTotItem": 100000,
                        "dTasaIVA": 10,
                        "dIVAItem": 10000,
                        "dTasaInc": 1,
                        "dIncItem": 1000,
                        "dTotOpeItem": 111000
                    }
                ]
            }
            
            # Generar DE temporal
            temp_de_path = Path("/tmp/temp_de.xml")
            generate_de_python(input_data, temp_de_path)
            
            # Leer y parsear DE
            de_content = temp_de_path.read_text(encoding='utf-8')
            
            # Construir rDE manualmente
            SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
            rde_root = etree.Element(f"{{{SIFEN_NS}}}rDE")
            
            # Parsear DE y agregar a rDE
            de_element = etree.fromstring(de_content.encode('utf-8'))
            rde_root.append(de_element)
            
            # Agregar dVerFor si no existe
            dverfor = etree.SubElement(rde_root, f"{{{SIFEN_NS}}}dVerFor")
            dverfor.text = "150"
            
            print("✅ rDE base generado")
            
        except Exception as e:
            print(f"❌ ERROR generando rDE: {e}")
            sys.exit(1)
        
        # Validar dNumDoc
        print("🔍 Validando dNumDoc...")
        validate_dnum_doc(rde_root)
        
        # 2. Firmar rDE con perfil correcto
        print("🔐 Firmando rDE con perfil SIFEN...")
        
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
        
        # 3. Validar perfil de firma
        print("\n🔍 Validando perfil de firma...")
        profile_results = check_signature_profile(xml_firmado_path)
        
        # 4. Generar versión para prevalidador (sin gCamFuFD)
        print("📋 Generando versión para prevalidador...")
        
        # Parsear XML firmado
        rde_element = etree.fromstring(signed_xml.encode('utf-8'))
        
        # Eliminar gCamFuFD si existe
        remove_g_cam_fu_fd(rde_element)
        
        # Serializar y guardar
        prevalidador_xml = etree.tostring(rde_element, encoding='UTF-8', xml_declaration=True, pretty_print=True).decode('utf-8')
        xml_prevalidador_path.write_text(prevalidador_xml, encoding='utf-8')
        print(f"✅ XML prevalidador guardado: {xml_prevalidador_path}")
        
        # 5. Generar SOAP 1.2
        print("📦 Generando SOAP 1.2...")
        
        d_id = generate_did()
        print(f"   dId: {d_id}")
        
        soap_bytes = build_soap_envelope(rde_element, d_id)
        soap_path.write_bytes(soap_bytes)
        print(f"✅ SOAP guardado: {soap_path}")
        
        # 6. Resumen final
        print("\n" + "="*60)
        print("🎯 ARTIFACTS GENERADOS EXITOSAMENTE:")
        print("="*60)
        print(f"📄 XML firmado:      {xml_firmado_path}")
        print(f"📄 XML prevalidador: {xml_prevalidador_path}")
        print(f"📋 SOAP 1.2:        {soap_path}")
        print(f"🔑 dId generado:    {d_id}")
        
        # Verificación final del perfil
        print(f"\n🔍 Perfil de firma:")
        print(f"   - Signature parent: {profile_results['signature_parent']}")
        print(f"   - Canonicalization: {profile_results['canonicalization_method']}")
        print(f"   - SignatureMethod: {profile_results['signature_method']}")
        print(f"   - DigestMethod: {profile_results['digest_method']}")
        print(f"   - Transforms: {profile_results['transforms']}")
        print(f"   - Reference URI: {profile_results['reference_uri']}")
        
        print("\n✅ Listo para enviar a SIFEN")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
