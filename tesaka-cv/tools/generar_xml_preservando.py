#!/usr/bin/env python3
"""
Genera XML SIFEN preservando TODA la estructura del XML original
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.xml_generator_v150 import generate_cdc

def generar_xml_preservando(xml_original, ruc, dv, output_path):
    """
    Genera XML preservando estructura completa:
    - Mantiene gCamFuFD
    - Mantiene todos los campos
    - Solo cambia datos del emisor
    """
    
    print("📝 Generando XML preservando estructura completa...")
    
    # Parsear XML original
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(xml_original, parser)
    root = tree.getroot()
    
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    
    # Extraer rDE (el XML original ya es rDE, no está en rLoteDE)
    rde = root
    if root.tag == '{http://ekuatia.set.gov.py/sifen/xsd}rLoteDE':
        rde = root.find(f".//{SIFEN_NS}rDE")
    
    if rde is None:
        print("❌ No se encontró rDE en el XML")
        return None, None
    
    # Extraer datos originales del timbrado
    gTimb = rde.find(f".//{SIFEN_NS}gTimb")
    timbrado = gTimb.find(f"{SIFEN_NS}dNumTim").text
    est = gTimb.find(f"{SIFEN_NS}dEst").text
    pun_exp = gTimb.find(f"{SIFEN_NS}dPunExp").text
    num_doc = gTimb.find(f"{SIFEN_NS}dNumDoc").text
    fe_ini_t = gTimb.find(f"{SIFEN_NS}dFeIniT").text
    
    # Actualizar SOLO los datos del emisor
    gEmis = rde.find(f".//{SIFEN_NS}gEmis")
    gEmis.find(f"{SIFEN_NS}dRucEm").text = ruc
    gEmis.find(f"{SIFEN_NS}dDVEmi").text = dv
    gEmis.find(f"{SIFEN_NS}dNomEmi").text = "EMPRESA DE PRUEBA S.A."
    gEmis.find(f"{SIFEN_NS}dNomFanEmi").text = "EMPRESA DE PRUEBA"
    gEmis.find(f"{SIFEN_NS}dDirEmi").text = "DIRECCION DE PRUEBA 123"
    
    # Mantener todos los demás datos intactos
    # - gDatRec (receptor)
    # - gCamItem (items)
    # - gTotSub (totales)
    # - gCamFuFD (se mantiene)
    
    # Eliminar firma existente para regenerar
    for sig in rde.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
        sig.getparent().remove(sig)
    
    # Generar nuevo CDC
    fecha_cdc = fe_ini_t.split('T')[0].replace('-', '')
    nuevo_cdc, dv_cdc = generate_cdc(
        ruc, dv, timbrado, est, pun_exp,
        num_doc, "1", fecha_cdc
    )
    nuevo_cdc_completo = nuevo_cdc + dv_cdc
    
    print(f"\n📊 CDC Original: 01800140664029010018945612026010915677380320")
    print(f"📊 CDC Nuevo:    {nuevo_cdc_completo}")
    
    # Actualizar CDC en DE
    de = rde.find(f"{SIFEN_NS}DE")
    de.set('Id', nuevo_cdc_completo)
    de.find(f"{SIFEN_NS}dDVId").text = dv_cdc
    de.find(f"{SIFEN_NS}dFecFirma").text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    
    # Actualizar QR en gCamFuFD con nuevo CDC
    gCamFuFD = rde.find(f"{SIFEN_NS}gCamFuFD")
    if gCamFuFD is not None:
        # Extraer QR original y actualizar CDC
        qr_original = gCamFuFD.find(f"{SIFEN_NS}dCarQR").text
        # Reemplazar CDC en el QR
        qr_nuevo = qr_original.replace(
            "01800140664029010018945612026010915677380320",
            nuevo_cdc_completo
        )
        gCamFuFD.find(f"{SIFEN_NS}dCarQR").text = qr_nuevo
        print("✅ QR actualizado con nuevo CDC")
    
    # Guardar XML sin firma
    xml_bytes = etree.tostring(rde, encoding='utf-8', xml_declaration=True, standalone=False)
    Path(output_path.replace('.xml', '_sin_firma.xml')).write_bytes(xml_bytes)
    
    print(f"\n✅ XML generado (sin firma): {output_path}")
    print("   Estructura completa preservada")
    print("   gCamFuFD mantenido")
    print("   Todos los campos intactos")
    
    return output_path, nuevo_cdc_completo

def main():
    parser = argparse.ArgumentParser(description="Generar XML SIFEN preservando estructura")
    parser.add_argument('--original', required=True, help='XML original validado')
    parser.add_argument('--ruc', required=True, help='RUC (sin DV)')
    parser.add_argument('--dv', required=True, help='DV del RUC')
    parser.add_argument('--output', required=True, help='XML de salida')
    
    args = parser.parse_args()
    
    if not Path(args.original).exists():
        print(f"❌ Archivo no encontrado: {args.original}")
        sys.exit(1)
    
    try:
        xml_path, cdc = generar_xml_preservando(
            args.original, args.ruc, args.dv, args.output
        )
        
        print(f"\n🎯 XML listo para firmar:")
        print(f"   Archivo: {xml_path}")
        print(f"   CDC: {cdc}")
        print(f"\n📋 Para firmar:")
        print(f"   export SIFEN_CERT_PATH=/path/to/cert.p12")
        print(f"   export SIFEN_SIGN_P12_PATH=/path/to/cert.p12")
        print(f"   export SIFEN_SIGN_P12_PASSWORD=password")
        print(f"   .venv/bin/python tools/send_sirecepde.py --xml {xml_path}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
