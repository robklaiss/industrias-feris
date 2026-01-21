#!/usr/bin/env python3
"""
Crea XML SIFEN con tus datos - versión simple
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.xml_generator_v150 import generate_cdc

def crear_xml_simple(xml_validado, ruc, dv, timbrado, num_doc, output_path):
    """
    Crea XML con tus datos - solo modifica lo esencial
    """
    
    print("📝 Creando XML con tus datos (versión simple)...")
    print(f"   RUC: {ruc}-{dv}")
    print(f"   Timbrado: {timbrado}")
    print(f"   Documento: {num_doc}")
    
    # Parsear XML validado
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(xml_validado, parser)
    root = tree.getroot()
    
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    
    # Extraer rDE
    rde = root
    if root.tag == f'{SIFEN_NS}rLoteDE':
        rde = root.find(f".//{SIFEN_NS}rDE")
    
    # === CAMBIAR SOLO LO ESENCIAL ===
    
    # 1. Datos del emisor
    gEmis = rde.find(f".//{SIFEN_NS}gEmis")
    gEmis.find(f"{SIFEN_NS}dRucEm").text = ruc
    gEmis.find(f"{SIFEN_NS}dDVEmi").text = dv
    gEmis.find(f"{SIFEN_NS}dNomEmi").text = "EMPRESA DE PRUEBA S.A."
    gEmis.find(f"{SIFEN_NS}dNomFanEmi").text = "EMPRESA DE PRUEBA"
    gEmis.find(f"{SIFEN_NS}dDirEmi").text = "AVDA. ESPAÑA 123"
    gEmis.find(f"{SIFEN_NS}dTelEmi").text = "0971 123456"
    gEmis.find(f"{SIFEN_NS}dEmailE").text = "info@empresa.com.py"
    
    # 2. Timbrado
    gTimb = rde.find(f".//{SIFEN_NS}gTimb")
    gTimb.find(f"{SIFEN_NS}dNumTim").text = timbrado
    gTimb.find(f"{SIFEN_NS}dNumDoc").text = num_doc
    
    # 3. Fecha de emisión
    gDatGralOpe = rde.find(f".//{SIFEN_NS}gDatGralOpe")
    gDatGralOpe.find(f"{SIFEN_NS}dFeEmiDE").text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    
    # 4. Receptor (mantener consumidor final)
    gDatRec = rde.find(f".//{SIFEN_NS}gDatRec")
    gDatRec.find(f"{SIFEN_NS}dNomRec").text = "CONSUMIDOR FINAL"
    
    # 5. Items (mantener estructura, cambiar descripción)
    items = rde.findall(f".//{SIFEN_NS}gCamItem")
    
    # Item 1
    items[0].find(f"{SIFEN_NS}dDesProSer").text = "PRODUCTO DE VENTA"
    
    # Item 2  
    items[1].find(f"{SIFEN_NS}dDesProSer").text = "SERVICIO PROFESIONAL"
    
    # 6. Eliminar firma existente
    for sig in rde.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
        sig.getparent().remove(sig)
    
    # 7. Eliminar QR si existe
    gCamFuFD = rde.find(f"{SIFEN_NS}gCamFuFD")
    if gCamFuFD is not None:
        gCamFuFD.getparent().remove(gCamFuFD)
    
    # Guardar XML sin firma
    xml_bytes = etree.tostring(rde, encoding='utf-8', xml_declaration=True)
    Path(output_path).write_bytes(xml_bytes)
    
    print(f"\n✅ XML creado: {output_path}")
    print("   Estructura 100% preservada")
    print("   Solo modificados datos esenciales")
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Crear XML SIFEN simple")
    parser.add_argument('--validado', required=True, help='XML validado original')
    parser.add_argument('--ruc', required=True, help='RUC (sin DV)')
    parser.add_argument('--dv', required=True, help='DV del RUC')
    parser.add_argument('--timbrado', required=True, help='Número de timbrado')
    parser.add_argument('--num-doc', required=True, help='Número documento (7 dígitos)')
    parser.add_argument('--output', required=True, help='XML de salida')
    
    args = parser.parse_args()
    
    # Formatear número de documento
    num_doc = str(args.num_doc).zfill(7)
    
    if not Path(args.validado).exists():
        print(f"❌ Archivo no encontrado: {args.validado}")
        sys.exit(1)
    
    try:
        xml_path = crear_xml_simple(
            args.validado, args.ruc, args.dv, args.timbrado,
            num_doc, args.output
        )
        
        print(f"\n🎯 XML listo para firmar:")
        print(f"   Archivo: {xml_path}")
        print(f"\n📋 Próximos pasos:")
        print(f"   1. Firmar con: .venv/bin/python tools/send_sirecepde.py --xml {xml_path}")
        print(f"   2. Validar en Prevalidador SIFEN")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
