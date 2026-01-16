#!/usr/bin/env python3
"""
Crea XML SIFEN con tus datos preservando la estructura validada
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.xml_generator_v150 import generate_cdc

def crear_xml_nuestro(xml_validado, ruc, dv, timbrado, establecimiento, punto_exp, num_doc, output_path):
    """
    Crea XML con tus datos preservando 100% la estructura del XML validado
    """
    
    print("📝 Creando XML con tus datos...")
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
    
    # === DATOS DEL EMISOR ===
    gEmis = rde.find(f".//{SIFEN_NS}gEmis")
    gEmis.find(f"{SIFEN_NS}dRucEm").text = ruc
    gEmis.find(f"{SIFEN_NS}dDVEmi").text = dv
    gEmis.find(f"{SIFEN_NS}dNomEmi").text = "EMPRESA DE PRUEBA S.A."
    gEmis.find(f"{SIFEN_NS}dNomFanEmi").text = "EMPRESA DE PRUEBA"
    gEmis.find(f"{SIFEN_NS}dDirEmi").text = "AVDA. ESPAÑA 123"
    gEmis.find(f"{SIFEN_NS}dNumCas").text = "123"
    gEmis.find(f"{SIFEN_NS}dCompDir1").text = "ENTRE CALLE A Y B"
    gEmis.find(f"{SIFEN_NS}dCompDir2").text = "ESQUINA NORTE"
    gEmis.find(f"{SIFEN_NS}cDepEmi").text = "12"
    gEmis.find(f"{SIFEN_NS}dDesDepEmi").text = "CENTRAL"
    gEmis.find(f"{SIFEN_NS}cDisEmi").text = "169"
    gEmis.find(f"{SIFEN_NS}dDesDisEmi").text = "LAMBARE"
    gEmis.find(f"{SIFEN_NS}cCiuEmi").text = "6106"
    gEmis.find(f"{SIFEN_NS}dDesCiuEmi").text = "LAMBARE"
    gEmis.find(f"{SIFEN_NS}dTelEmi").text = "0971 123456"
    gEmis.find(f"{SIFEN_NS}dEmailE").text = "info@empresa.com.py"
    gEmis.find(f"{SIFEN_NS}dDenSuc").text = "MATRIZ"
    
    # === TIMBRADO ===
    gTimb = rde.find(f".//{SIFEN_NS}gTimb")
    gTimb.find(f"{SIFEN_NS}dNumTim").text = timbrado
    gTimb.find(f"{SIFEN_NS}dEst").text = establecimiento
    gTimb.find(f"{SIFEN_NS}dPunExp").text = punto_exp
    gTimb.find(f"{SIFEN_NS}dNumDoc").text = num_doc
    
    # === FECHA DE EMISION ===
    gDatGralOpe = rde.find(f".//{SIFEN_NS}gDatGralOpe")
    gDatGralOpe.find(f"{SIFEN_NS}dFeEmiDE").text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    # dHorProDE puede no existir, no lo modificamos
    
    # === RECEPTOR (CONSUMIDOR FINAL) ===
    gDatRec = rde.find(f".//{SIFEN_NS}gDatRec")
    gDatRec.find(f"{SIFEN_NS}dRucRec").text = "80012345"
    gDatRec.find(f"{SIFEN_NS}dDVRec").text = "7"
    gDatRec.find(f"{SIFEN_NS}dNomRec").text = "CONSUMIDOR FINAL"
    gDatRec.find(f"{SIFEN_NS}dDirRec").text = "CIUDAD DEL ESTE"
    gDatRec.find(f"{SIFEN_NS}dNumCasRec").text = "SN"
    gDatRec.find(f"{SIFEN_NS}dTelRec").text = "0981 765432"
    gDatRec.find(f"{SIFEN_NS}dEmailRec").text = "cliente@email.com"
    
    # === ITEMS ===
    items = rde.findall(f".//{SIFEN_NS}gCamItem")
    
    # Item 1 - Producto
    items[0].find(f"{SIFEN_NS}dCodInt").text = "PROD001"
    items[0].find(f"{SIFEN_NS}dDesProSer").text = "PRODUCTO DE VENTA - COMPUTADORA"
    items[0].find(f"{SIFEN_NS}dCantProSer").text = "1.0000"
    item1_val = items[0].find(f".//{SIFEN_NS}gValItem")
    item1_val.find(f"{SIFEN_NS}dPUniProSer").text = "500000.00000000"
    item1_val.find(f"{SIFEN_NS}dTotOpeItem").text = "500000.00000000"
    item1_iva = item1_val.find(f".//{SIFEN_NS}gCamIVA")
    item1_iva.find(f"{SIFEN_NS}dBaseGravIVA").text = "454545.45000000"
    item1_iva.find(f"{SIFEN_NS}dLiqIVAItem").text = "45454.55000000"
    
    # Item 2 - Servicio
    items[1].find(f"{SIFEN_NS}dCodInt").text = "SERV001"
    items[1].find(f"{SIFEN_NS}dDesProSer").text = "SERVICIO DE INSTALACION Y CONFIGURACION"
    items[1].find(f"{SIFEN_NS}dCantProSer").text = "1.0000"
    item2_val = items[1].find(f".//{SIFEN_NS}gValItem")
    item2_val.find(f"{SIFEN_NS}dPUniProSer").text = "500000.00000000"
    item2_val.find(f"{SIFEN_NS}dTotOpeItem").text = "500000.00000000"
    item2_iva = item2_val.find(f".//{SIFEN_NS}gCamIVA")
    item2_iva.find(f"{SIFEN_NS}dBaseGravIVA").text = "454545.45000000"
    item2_iva.find(f"{SIFEN_NS}dLiqIVAItem").text = "45454.55000000"
    
    # === TOTALES ===
    gTotSub = rde.find(f".//{SIFEN_NS}gTotSub")
    gTotSub.find(f"{SIFEN_NS}dSubExe").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dSub5").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dSub10").text = "1000000.00000000"
    gTotSub.find(f"{SIFEN_NS}dTotOpe").text = "1000000.00000000"
    gTotSub.find(f"{SIFEN_NS}dTotDesc").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dTotDescGlotem").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dTotAntItem").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dTotAnt").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dPorcDescTotal").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dDescTotal").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dAnticipo").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dRedon").text = "0.0000"
    gTotSub.find(f"{SIFEN_NS}dTotGralOpe").text = "1000000.00000000"
    gTotSub.find(f"{SIFEN_NS}dTotIVA5").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dTotIVA10").text = "90909.00000000"
    gTotSub.find(f"{SIFEN_NS}dTotIVA").text = "90909.00000000"
    gTotSub.find(f"{SIFEN_NS}dBaseGrav5").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dBaseGrav10").text = "909091.00000000"
    gTotSub.find(f"{SIFEN_NS}dTBasGraIVA").text = "909091.00000000"
    
    # === GENERAR NUEVO CDC ===
    fe_ini_t = gTimb.find(f"{SIFEN_NS}dFeIniT").text
    fecha_cdc = fe_ini_t.split('T')[0].replace('-', '')
    
    nuevo_cdc, dv_cdc = generate_cdc(
        ruc, dv, timbrado, establecimiento, punto_exp,
        num_doc, "1", fecha_cdc
    )
    nuevo_cdc_completo = nuevo_cdc + dv_cdc
    
    print(f"\n📊 CDC generado: {nuevo_cdc_completo}")
    
    # Actualizar CDC en DE
    de = rde.find(f"{SIFEN_NS}DE")
    de.set('Id', nuevo_cdc_completo)
    de.find(f"{SIFEN_NS}dDVId").text = dv_cdc
    de.find(f"{SIFEN_NS}dFecFirma").text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    
    # Eliminar firma y QR existentes para regenerar
    for sig in rde.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
        sig.getparent().remove(sig)
    
    gCamFuFD = rde.find(f"{SIFEN_NS}gCamFuFD")
    if gCamFuFD is not None:
        gCamFuFD.getparent().remove(gCamFuFD)
    
    # Guardar XML sin firma
    xml_bytes = etree.tostring(rde, encoding='utf-8', xml_declaration=True, standalone=False)
    Path(output_path.replace('.xml', '_sin_firma.xml')).write_bytes(xml_bytes)
    
    print(f"\n✅ XML creado: {output_path}")
    print("   Con estructura 100% preservada")
    print("   Solo cambiados los datos necesarios")
    
    return output_path, nuevo_cdc_completo

def main():
    parser = argparse.ArgumentParser(description="Crear XML SIFEN con tus datos")
    parser.add_argument('--validado', required=True, help='XML validado original')
    parser.add_argument('--ruc', required=True, help='RUC (sin DV)')
    parser.add_argument('--dv', required=True, help='DV del RUC')
    parser.add_argument('--timbrado', required=True, help='Número de timbrado')
    parser.add_argument('--establecimiento', default='001', help='Establecimiento')
    parser.add_argument('--punto-exp', default='001', help='Punto de expedición')
    parser.add_argument('--num-doc', required=True, help='Número documento (7 dígitos)')
    parser.add_argument('--output', required=True, help='XML de salida')
    
    args = parser.parse_args()
    
    # Formatear número de documento
    num_doc = str(args.num_doc).zfill(7)
    
    if not Path(args.validado).exists():
        print(f"❌ Archivo no encontrado: {args.validado}")
        sys.exit(1)
    
    try:
        xml_path, cdc = crear_xml_nuestro(
            args.validado, args.ruc, args.dv, args.timbrado,
            args.establecimiento, args.punto_exp,
            num_doc, args.output
        )
        
        print(f"\n🎯 XML listo para firmar:")
        print(f"   Archivo: {xml_path}")
        print(f"   CDC: {cdc}")
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
