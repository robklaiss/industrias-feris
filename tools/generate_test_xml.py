#!/usr/bin/env python3
"""
Generador de XML de prueba con estructura exacta SIFEN v150
rDE children: dVerFor, DE, Signature, gCamFuFD
"""

import sys
import os
from pathlib import Path
from lxml import etree

# Agregar path para importar firmador
sys.path.insert(0, str(Path(__file__).parent.parent / "tesaka-cv" / "app"))

def create_test_rde() -> etree._Element:
    """Crea rDE de prueba con estructura mínima"""
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
    
    # gCamFuFD (después de DE, antes de firmar)
    gcam = etree.SubElement(rde, f"{{{SIFEN_NS}}}gCamFuFD")
    etree.SubElement(gcam, f"{{{SIFEN_NS}}}dCodCam").text = "1"
    etree.SubElement(gcam, f"{{{SIFEN_NS}}}dDesCam").text = "CAMPO FIRMA DIGITAL"
    
    return rde

def main():
    print("=== GENERADOR XML PRUEBA SIFEN v150 ===")
    
    try:
        # Crear rDE
        rde_element = create_test_rde()
        print("✅ rDE creado")
        
        # Serializar a string
        rde_xml = etree.tostring(rde_element, encoding='unicode')
        print("✅ rDE serializado")
        
        # Guardar XML base
        base_path = Path("/tmp/test_rde_base.xml")
        base_path.write_text(rde_xml, encoding='utf-8')
        print(f"✅ XML base guardado: {base_path}")
        
        # Intentar firmar
        try:
            from sifen_client.xmldsig_signer import sign_de_xml
            
            print("🔐 Firmando XML...")
            os.environ["SIFEN_SIGNATURE_PARENT"] = "RDE"
            
            # Usar variables de entorno
            cert_path = os.getenv("SIFEN_CERT_PATH")
            cert_pass = os.getenv("SIFEN_CERT_PASS")
            
            if not cert_path or not cert_pass:
                print("❌ ERROR: Setear SIFEN_CERT_PATH y SIFEN_CERT_PASS")
                sys.exit(1)
            
            signed_xml = sign_de_xml(
                xml_str=rde_xml,
                p12_path=cert_path,
                p12_password=cert_pass
            )
            
            # Guardar XML firmado
            signed_path = Path.home() / "Desktop" / "sifen_de_firmado_test.xml"
            signed_path.write_text(signed_xml, encoding='utf-8')
            print(f"✅ XML firmado guardado: {signed_path}")
            
            # Verificar estructura
            print("\n🔍 Verificando estructura...")
            tree = etree.fromstring(signed_xml.encode('utf-8'))
            children = list(tree)
            
            print("📋 rDE children:")
            for i, child in enumerate(children):
                tag = etree.QName(child).localname
                print(f"   {i}: {tag}")
            
            # Verificar orden exacto
            expected = ["dVerFor", "DE", "Signature", "gCamFuFD"]
            actual = [etree.QName(child).localname for child in children]
            
            if actual == expected:
                print("✅ Orden correcto: dVerFor, DE, Signature, gCamFuFD")
            else:
                print(f"❌ Orden incorrecto. Esperado: {expected}")
                print(f"                  Actual: {actual}")
            
            # Verificar con inspector
            print("\n🔍 Ejecutando inspector...")
            inspector_path = Path(__file__).parent / "sifen_signature_profile_check.py"
            result = os.system(f".venv/bin/python {inspector_path} {signed_path}")
            
            if result == 0:
                print("✅ Inspector: OK")
            else:
                print("❌ Inspector: FAIL")
            
        except ImportError as e:
            print(f"❌ No se pudo importar sign_de_xml: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error firmando: {e}")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
