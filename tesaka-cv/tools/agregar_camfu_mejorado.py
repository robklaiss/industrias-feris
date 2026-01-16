#!/usr/bin/env python3
"""
Agrega gCamFuFD con QR generado correctamente según código de Roshka
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

def bytes_to_hex(data):
    """Convierte bytes a hexadecimal"""
    return data.hex()

def sha256_hex(text):
    """Genera SHA256 hash en hexadecimal"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def generar_qr_correcto(cdc, fecha_emision, ruc_rec, total_gral, total_iva, c_items, digest_value, id_csc, csc):
    """
    Genera QR según el código de Roshka jsifenlib
    Ver: DocumentoElectronico.java línea 380
    """
    
    # Formatear fecha como hex
    fecha_str = fecha_emision.replace(':', '')  # Formato: yyyy-MM-ddTHHmmss
    fecha_hex = bytes_to_hex(fecha_str.encode('utf-8'))
    
    # Construir parámetros en orden
    params = []
    params.append(f"nVersion=150")
    params.append(f"Id={cdc}")
    params.append(f"dFeEmiDE={fecha_hex}")
    params.append(f"dRucRec={ruc_rec}")
    params.append(f"dTotGralOpe={total_gral}")
    params.append(f"dTotIVA={total_iva}")
    params.append(f"cItems={c_items}")
    params.append(f"DigestValue={digest_value}")
    params.append(f"IdCSC={id_csc}")
    
    # Unir parámetros
    url_params = "&".join(params)
    
    # Calcular hash con CSC
    hash_input = url_params + csc
    c_hash_qr = sha256_hex(hash_input)
    
    # URL completa
    base_url = "https://ekuatia.set.gov.py/consultas/qr?"
    qr_url = base_url + url_params + f"&cHashQR={c_hash_qr}"
    
    return qr_url

def agregar_camfu_mejorado(xml_path, output_path, csc=None, id_csc="0001"):
    """Agrega gCamFuFD con QR generado correctamente"""
    
    # Parsear XML
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(xml_path, parser)
    root = tree.getroot()
    
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    DS_NS = "{http://www.w3.org/2000/09/xmldsig#}"
    
    # Extraer datos del XML
    de = root.find(f".//{SIFEN_NS}DE")
    cdc = de.get('Id')
    
    # Fecha de emisión
    gDatGralOpe = root.find(f".//{SIFEN_NS}gDatGralOpe")
    fecha_emision = gDatGralOpe.find(f"{SIFEN_NS}dFeEmiDE").text
    
    # Receptor
    gDatRec = gDatGralOpe.find(f"{SIFEN_NS}gDatRec")
    ruc_rec_elem = gDatRec.find(f"{SIFEN_NS}dRucRec")
    ruc_rec = ruc_rec_elem.text if ruc_rec_elem is not None else "0"
    
    # Totales
    gTotSub = root.find(f".//{SIFEN_NS}gTotSub")
    total_gral = gTotSub.find(f"{SIFEN_NS}dTotGralOpe").text
    total_iva = gTotSub.find(f"{SIFEN_NS}dTotIVA").text
    
    # Items
    items = root.findall(f".//{SIFEN_NS}gCamItem")
    c_items = str(len(items))
    
    # DigestValue de la firma
    signature = root.find(f".//{DS_NS}Signature")
    digest_elem = signature.find(f".//{DS_NS}DigestValue")
    digest_value_b64 = digest_elem.text
    
    # Convertir DigestValue a hex (como hace Roshka)
    digest_bytes = base64.b64decode(digest_value_b64)
    digest_value_hex = bytes_to_hex(base64.b64encode(digest_bytes))
    
    # Generar QR
    if csc:
        qr_url = generar_qr_correcto(
            cdc, fecha_emision, ruc_rec, total_gral, total_iva,
            c_items, digest_value_hex, id_csc, csc
        )
        print(f"✅ QR generado con CSC")
    else:
        # Fallback: QR sin hash (para testing)
        fecha_hex = bytes_to_hex(fecha_emision.replace(':', '').encode('utf-8'))
        qr_url = (f"https://ekuatia.set.gov.py/consultas/qr?"
                  f"nVersion=150&Id={cdc}&"
                  f"dFeEmiDE={fecha_hex}&"
                  f"dRucRec={ruc_rec}&"
                  f"dTotGralOpe={total_gral}&"
                  f"dTotIVA={total_iva}&"
                  f"cItems={c_items}&"
                  f"DigestValue={digest_value_hex}&"
                  f"IdCSC={id_csc}&"
                  f"cHashQR=TESTING")
        print(f"⚠️  QR generado SIN CSC (testing)")
    
    # Crear gCamFuFD
    gCamFuFD = etree.Element(f"{SIFEN_NS}gCamFuFD")
    dCarQR = etree.SubElement(gCamFuFD, f"{SIFEN_NS}dCarQR")
    dCarQR.text = qr_url
    
    # Eliminar gCamFuFD existente
    existing_camfu = root.find(f"{SIFEN_NS}gCamFuFD")
    if existing_camfu is not None:
        root.remove(existing_camfu)
    
    # Reorganizar: Signature debe estar antes de gCamFuFD
    signature = root.find(f".//{DS_NS}Signature")
    if signature is not None:
        root.remove(signature)
        root.append(signature)
    
    # Agregar gCamFuFD al final
    root.append(gCamFuFD)
    
    # Guardar XML
    xml_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True, standalone=False)
    Path(output_path).write_bytes(xml_bytes)
    
    print(f"✅ gCamFuFD agregado: {output_path}")
    print(f"   CDC: {cdc}")
    print(f"   Orden: Signature → gCamFuFD")
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Agregar gCamFuFD mejorado a XML SIFEN")
    parser.add_argument('--xml', required=True, help='XML firmado')
    parser.add_argument('--output', required=True, help='XML de salida')
    parser.add_argument('--csc', help='Código de Seguridad CSC (opcional)')
    parser.add_argument('--id-csc', default='0001', help='ID del CSC')
    
    args = parser.parse_args()
    
    if not Path(args.xml).exists():
        print(f"❌ Archivo no encontrado: {args.xml}")
        sys.exit(1)
    
    try:
        agregar_camfu_mejorado(args.xml, args.output, args.csc, args.id_csc)
        print("\n📋 XML completo para SIFEN")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
