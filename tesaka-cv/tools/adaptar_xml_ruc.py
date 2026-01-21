#!/usr/bin/env python3
"""
Adapta XML SIFEN real para usar con tu RUC
Mantiene la estructura válida pero cambia los datos del emisor
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree

def adaptar_xml(input_xml, output_xml, nuevo_ruc, nuevo_dv, timbrado=None):
    """Adapta XML para nuevo RUC manteniendo estructura válida"""
    
    # Parsear XML
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(input_xml, parser)
    root = tree.getroot()
    
    # Namespaces
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    
    # Encontrar DE
    de = root.find(f".//{SIFEN_NS}DE")
    
    # Actualizar RUC del emisor
    gEmis = de.find(f".//{SIFEN_NS}gEmis")
    gEmis.find(f"{SIFEN_NS}dRucEm").text = nuevo_ruc
    gEmis.find(f"{SIFEN_NS}dDVEmi").text = nuevo_dv
    
    # Actualizar nombre (opcional)
    gEmis.find(f"{SIFEN_NS}dNomEmi").text = "EMPRESA DE PRUEBA S.A."
    gEmis.find(f"{SIFEN_NS}dNomFanEmi").text = "EMPRESA DE PRUEBA S.A."
    gEmis.find(f"{SIFEN_NS}dDirEmi").text = "DIRECCION DE PRUEBA"
    gEmis.find(f"{SIFEN_NS}dDenSuc").text = "MATRIZ"
    
    # Actualizar timbrado si se especifica
    if timbrado:
        gTimb = de.find(f".//{SIFEN_NS}gTimb")
        gTimb.find(f"{SIFEN_NS}dNumTim").text = timbrado
    
    # Actualizar fecha y hora
    now = datetime.now(timezone.utc)
    de.find(f"{SIFEN_NS}dFecFirma").text = now.strftime('%Y-%m-%dT%H:%M:%S')
    gDatGralOpe = de.find(f".//{SIFEN_NS}gDatGralOpe")
    gDatGralOpe.find(f"{SIFEN_NS}dFeEmiDE").text = now.strftime('%Y-%m-%dT%H:%M:%S')
    
    # Eliminar firma existente
    for sig in root.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
        sig.getparent().remove(sig)
    
    # Eliminar QR existente
    gCamFuFD = root.find(f".//{SIFEN_NS}gCamFuFD")
    if gCamFuFD is not None:
        gCamFuFD.getparent().remove(gCamFuFD)
    
    # Guardar XML adaptado (sin firmar)
    xml_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    Path(output_xml).write_bytes(xml_bytes)
    
    print(f"✅ XML adaptado guardado en: {output_xml}")
    print(f"   RUC: {nuevo_ruc}-{nuevo_dv}")
    if timbrado:
        print(f"   Timbrado: {timbrado}")
    
    return output_xml

def main():
    parser = argparse.ArgumentParser(description="Adaptar XML SIFEN para nuevo RUC")
    parser.add_argument('--input', required=True, help='XML original')
    parser.add_argument('--output', required=True, help='XML adaptado de salida')
    parser.add_argument('--ruc', required=True, help='Nuevo RUC (sin DV)')
    parser.add_argument('--dv', required=True, help='DV del RUC')
    parser.add_argument('--timbrado', help='Nuevo timbrado')
    
    args = parser.parse_args()
    
    if not Path(args.input).exists():
        print(f"❌ Archivo no encontrado: {args.input}")
        sys.exit(1)
    
    try:
        adaptar_xml(args.input, args.output, args.ruc, args.dv, args.timbrado)
        print("\n📋 El XML está listo para firmar con:")
        print(f"   .venv/bin/python tools/send_sirecepde.py --xml {args.output} --env test --artifacts-dir artifacts/adaptados")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
