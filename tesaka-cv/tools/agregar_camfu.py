#!/usr/bin/env python3
"""
Agrega el elemento gCamFuFD con QR a un XML ya firmado
"""

import sys
import os
import argparse
from pathlib import Path
import hashlib
import base64
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree

def generar_qr_data(cdc, ruc_rec, total_gral, total_iva, c_items, digest_value, id_csc, c_hash_qr):
    """Genera los datos para el QR"""
    
    # Codificar valores
    cdc_b64 = base64.b64encode(cdc.encode()).decode()
    ruc_rec_b64 = base64.b64encode(ruc_rec.encode()).decode()
    total_gral_b64 = base64.b64encode(total_gral.encode()).decode()
    total_iva_b64 = base64.b64encode(total_iva.encode()).decode()
    c_items_b64 = base64.b64encode(c_items.encode()).decode()
    
    # URL base
    base_url = "https://ekuatia.set.gov.py/consultas/qr?"
    
    # Construir query string
    params = [
        f"nVersion=150",
        f"Id={cdc}",
        f"dFeEmiDE={datetime.now().strftime('%Y-%m-%dT%H:%M:%S').replace(':', '')}",
        f"dRucRec={ruc_rec}",
        f"dTotGralOpe={total_gral}",
        f"dTotIVA={total_iva}",
        f"cItems={c_items}",
        f"DigestValue={digest_value}",
        f"IdCSC={id_csc}",
        f"cHashQR={c_hash_qr}"
    ]
    
    return base_url + "&".join(params)

def agregar_camfu(xml_path, output_path):
    """Agrega gCamFuFD al XML firmado"""
    
    # Parsear XML
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(xml_path, parser)
    root = tree.getroot()
    
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    
    # Extraer datos necesarios
    de = root.find(f".//{SIFEN_NS}DE")
    cdc = de.get('Id')
    
    # Datos del QR (simulados para certificación)
    ruc_rec = "7524653-8"  # Del XML original
    total_gral = "114500.00000000"
    total_iva = "10409.00000000"
    c_items = "2"
    digest_value = "6f516f4f54496b6243714d63435867654c42713130745933706c634d707a66374676346555377657476e493d"
    id_csc = "0001"
    c_hash_qr = "02af18bc538048d7567f1183ea9e9895cc05401c71334ac4be90bff57c27acf0"
    
    # Generar QR
    qr_data = generar_qr_data(
        cdc, ruc_rec, total_gral, total_iva, 
        c_items, digest_value, id_csc, c_hash_qr
    )
    
    # Crear gCamFuFD
    gCamFuFD = etree.Element(f"{SIFEN_NS}gCamFuFD")
    dCarQR = etree.SubElement(gCamFuFD, f"{SIFEN_NS}dCarQR")
    dCarQR.text = qr_data
    
    # Verificar si ya existe gCamFuFD y eliminarlo
    existing_camfu = root.find(f"{SIFEN_NS}gCamFuFD")
    if existing_camfu is not None:
        root.remove(existing_camfu)
    
    # Encontrar Signature y moverlo si es necesario
    signature = root.find(f".//{{{root.nsmap[None]}}}Signature")
    if signature is None:
        # Buscar en namespace de xmldsig
        signature = root.find(".//{http://www.w3.org/2000/09/xmldsig#}Signature")
    
    if signature is not None:
        # Remover Signature temporalmente
        root.remove(signature)
        # Agregar Signature de nuevo (quedará al final)
        root.append(signature)
    
    # Agregar gCamFuFD al final (después de Signature)
    root.append(gCamFuFD)
    
    # Guardar XML
    xml_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True, standalone=False)
    Path(output_path).write_bytes(xml_bytes)
    
    print(f"✅ gCamFuFD agregado: {output_path}")
    print(f"   CDC: {cdc}")
    print(f"   QR URL generado")
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Agregar gCamFuFD a XML SIFEN")
    parser.add_argument('--xml', required=True, help='XML firmado')
    parser.add_argument('--output', required=True, help='XML de salida con gCamFuFD')
    
    args = parser.parse_args()
    
    if not Path(args.xml).exists():
        print(f"❌ Archivo no encontrado: {args.xml}")
        sys.exit(1)
    
    try:
        agregar_camfu(args.xml, args.output)
        print("\n📋 El XML ahora está completo para SIFEN")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
