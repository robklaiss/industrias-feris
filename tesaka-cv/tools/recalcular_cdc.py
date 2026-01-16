#!/usr/bin/env python3
"""
Recalcula el CDC para un XML SIFEN
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.cdc_builder import build_cdc_from_de_xml
from app.sifen_client.xmlsec_signer import sign_de_with_p12

def recalcular_cdc(xml_path, output_path):
    """Recalcula el CDC del XML"""
    
    # Parsear XML
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(xml_path, parser)
    root = tree.getroot()
    
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    
    # Extraer DE
    de = root.find(f".//{SIFEN_NS}DE")
    
    print("🔍 Extrayendo datos para CDC...")
    
    # Extraer datos del DE
    gTimb = de.find(f".//{SIFEN_NS}gTimb")
    ruc_em = de.find(f".//{SIFEN_NS}gEmis/{SIFEN_NS}dRucEm").text
    dv_em = de.find(f".//{SIFEN_NS}gEmis/{SIFEN_NS}dDVEmi").text
    timbrado = gTimb.find(f"{SIFEN_NS}dNumTim").text
    est = gTimb.find(f"{SIFEN_NS}dEst").text
    pun_exp = gTimb.find(f"{SIFEN_NS}dPunExp").text
    num_doc = gTimb.find(f"{SIFEN_NS}dNumDoc").text
    tipo_doc = "1"
    
    # Fecha del timbrado (no fecha actual)
    fe_ini_t = gTimb.find(f"{SIFEN_NS}dFeIniT").text
    fecha = fe_ini_t.split('T')[0] if 'T' in fe_ini_t else fe_ini_t
    
    print(f"   RUC: {ruc_em}-{dv_em}")
    print(f"   Timbrado: {timbrado}")
    print(f"   Establecimiento: {est}")
    print(f"   Punto Expedición: {pun_exp}")
    print(f"   N° Documento: {num_doc}")
    print(f"   Fecha: {fecha}")
    
    # Generar nuevo CDC
    from app.sifen_client.xml_generator_v150 import generate_cdc
    
    nuevo_cdc, dv = generate_cdc(
        ruc_em, dv_em, timbrado, est, pun_exp, 
        num_doc, tipo_doc, fecha
    )
    
    nuevo_cdc_completo = nuevo_cdc + dv
    
    print(f"\n📊 CDC Original: {de.get('Id')}")
    print(f"📊 CDC Nuevo:    {nuevo_cdc_completo}")
    
    # Actualizar CDC en el DE
    de.set('Id', nuevo_cdc_completo)
    de.find(f"{SIFEN_NS}dDVId").text = dv
    
    # Eliminar firma y QR para regenerar
    for sig in root.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
        sig.getparent().remove(sig)
    
    gCamFuFD = root.find(f".//{SIFEN_NS}gCamFuFD")
    if gCamFuFD is not None:
        gCamFuFD.getparent().remove(gCamFuFD)
    
    # Guardar XML sin firma
    xml_sin_firma = output_path.replace('.xml', '_sin_firma.xml')
    xml_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True, standalone=False)
    Path(xml_sin_firma).write_bytes(xml_bytes)
    
    print(f"\n✅ XML sin firma guardado: {xml_sin_firma}")
    
    # Firmar el XML
    print("\n🔐 Firmando XML con nuevo CDC...")
    cert_path = os.getenv("SIFEN_SIGN_P12_PATH", "/Users/robinklaiss/.sifen/certs/F1T_65478.p12")
    cert_pass = os.getenv("SIFEN_SIGN_P12_PASSWORD", "bH1%T7EP")
    
    # Usar el sistema de firma completo
    from tools.send_sirecepde import sign_and_normalize_rde_inside_xml
    
    signed_bytes = sign_and_normalize_rde_inside_xml(
        xml_bytes, cert_path, cert_pass
    )
    
    # Guardar XML firmado
    Path(output_path).write_bytes(signed_bytes)
    
    print(f"✅ XML firmado guardado: {output_path}")
    
    # Verificar CDC final
    parser_final = etree.XMLParser(remove_blank_text=False)
    root_final = etree.fromstring(signed_bytes, parser_final)
    de_final = root_final.find(f".//{SIFEN_NS}DE")
    cdc_final = de_final.get('Id')
    
    print(f"\n📋 CDC Final: {cdc_final}")
    
    if cdc_final == nuevo_cdc_completo:
        print("✅ CDC coincide correctamente")
    else:
        print("❌ CDC no coincide")
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Recalcular CDC de XML SIFEN")
    parser.add_argument('--xml', required=True, help='XML a procesar')
    parser.add_argument('--output', required=True, help='XML de salida')
    
    args = parser.parse_args()
    
    if not Path(args.xml).exists():
        print(f"❌ Archivo no encontrado: {args.xml}")
        sys.exit(1)
    
    try:
        recalcular_cdc(args.xml, args.output)
        print("\n🎯 XML listo para SIFEN con CDC correcto")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
