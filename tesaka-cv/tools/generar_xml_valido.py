#!/usr/bin/env python3
"""
Genera XML SIFEN válido usando la estructura del XML real
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.xml_generator_v150 import generate_cdc
from app.sifen_client.xmlsec_signer import sign_de_with_p12

def generar_xml_valido(ruc, dv, timbrado, establecimiento, punto_exp, num_doc, output_path):
    """Genera un XML SIFEN válido con estructura completa"""
    
    print("📝 Generando XML SIFEN válido...")
    print(f"   RUC: {ruc}-{dv}")
    print(f"   Timbrado: {timbrado}")
    print(f"   Establecimiento: {establecimiento}")
    print(f"   Punto Expedición: {punto_exp}")
    print(f"   N° Documento: {num_doc}")
    
    template_path = Path("../docs/fac_029-010-0189456_533750241.xml_01800140664029010018945612026010915677380320.xml")
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(template_path, parser)
    root = tree.getroot()
    
    # Extraer rDE del template
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    rde = root.find(f".//{SIFEN_NS}rDE")
    
    # Actualizar datos del emisor
    gEmis = rde.find(f".//{SIFEN_NS}gEmis")
    gEmis.find(f"{SIFEN_NS}dRucEm").text = ruc
    gEmis.find(f"{SIFEN_NS}dDVEmi").text = dv
    gEmis.find(f"{SIFEN_NS}dNomEmi").text = "EMPRESA DE PRUEBA S.A."
    gEmis.find(f"{SIFEN_NS}dNomFanEmi").text = "EMPRESA DE PRUEBA S.A."
    gEmis.find(f"{SIFEN_NS}dDirEmi").text = "DIRECCION DE PRUEBA 123"
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
    
    # Actualizar timbrado
    gTimb = rde.find(f".//{SIFEN_NS}gTimb")
    gTimb.find(f"{SIFEN_NS}dNumTim").text = timbrado
    gTimb.find(f"{SIFEN_NS}dEst").text = establecimiento
    gTimb.find(f"{SIFEN_NS}dPunExp").text = punto_exp
    gTimb.find(f"{SIFEN_NS}dNumDoc").text = num_doc
    
    # Actualizar fecha de timbrado (hace 6 meses)
    from datetime import datetime, timedelta
    fecha_timbrado = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    gTimb.find(f"{SIFEN_NS}dFeIniT").text = fecha_timbrado
    
    # Actualizar fecha de emisión (ahora)
    now = datetime.now(timezone.utc)
    gDatGralOpe = rde.find(f".//{SIFEN_NS}gDatGralOpe")
    gDatGralOpe.find(f"{SIFEN_NS}dFeEmiDE").text = now.strftime('%Y-%m-%dT%H:%M:%S')
    
    # Actualizar receptor (consumidor final)
    gDatRec = rde.find(f".//{SIFEN_NS}gDatRec")
    gDatRec.find(f"{SIFEN_NS}dRucRec").text = "80012345"
    gDatRec.find(f"{SIFEN_NS}dDVRec").text = "7"
    gDatRec.find(f"{SIFEN_NS}dNomRec").text = "CLIENTE DE PRUEBA"
    gDatRec.find(f"{SIFEN_NS}dEmailRec").text = "cliente@email.com"
    
    # Actualizar items (ejemplo)
    items = rde.findall(f".//{SIFEN_NS}gCamItem")
    
    # Item 1
    items[0].find(f"{SIFEN_NS}dCodInt").text = "SERV001"
    items[0].find(f"{SIFEN_NS}dDesProSer").text = "SERVICIO DE CONSULTORIA"
    items[0].find(f"{SIFEN_NS}dCantProSer").text = "1.0000"
    items[0].find(f".//{SIFEN_NS}dPUniProSer").text = "500000.00000000"
    items[0].find(f".//{SIFEN_NS}dTotOpeItem").text = "500000.00000000"
    items[0].find(f".//{SIFEN_NS}dBasGravIVA").text = "454545.45000000"
    items[0].find(f".//{SIFEN_NS}dLiqIVAItem").text = "45454.55000000"
    
    # Item 2
    items[1].find(f"{SIFEN_NS}dCodInt").text = "PROD002"
    items[1].find(f"{SIFEN_NS}dDesProSer").text = "PRODUCTO DE VENTA"
    items[1].find(f"{SIFEN_NS}dCantProSer").text = "2.0000"
    items[1].find(f".//{SIFEN_NS}dPUniProSer").text = "250000.00000000"
    items[1].find(f".//{SIFEN_NS}dTotOpeItem").text = "500000.00000000"
    items[1].find(f".//{SIFEN_NS}dBasGravIVA").text = "454545.45000000"
    items[1].find(f".//{SIFEN_NS}dLiqIVAItem").text = "45454.55000000"
    
    # Actualizar totales
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
    gTotSub.find(f"{SIFEN_NS}dIVA5").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dIVA10").text = "90909.00000000"
    gTotSub.find(f"{SIFEN_NS}dTotIVA").text = "90909.00000000"
    gTotSub.find(f"{SIFEN_NS}dBaseGrav5").text = "0.00000000"
    gTotSub.find(f"{SIFEN_NS}dBaseGrav10").text = "909091.00000000"
    gTotSub.find(f"{SIFEN_NS}dTBasGraIVA").text = "909091.00000000"
    
    # Generar nuevo CDC
    fecha_cdc = fecha_timbrado.replace('-', '')
    print(f"   Fecha para CDC: {fecha_cdc}")
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
    de.find(f"{SIFEN_NS}dFecFirma").text = now.strftime('%Y-%m-%dT%H:%M:%S')
    
    # Eliminar firma y QR existentes
    for sig in rde.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
        sig.getparent().remove(sig)
    
    gCamFuFD = rde.find(f"{SIFEN_NS}gCamFuFD")
    if gCamFuFD is not None:
        gCamFuFD.getparent().remove(gCamFuFD)
    
    # Guardar XML sin firma
    xml_bytes = etree.tostring(rde, encoding='utf-8', xml_declaration=True)
    
    # Crear rDE contenedor
    rde_container = etree.Element(f"{SIFEN_NS}rDE", nsmap=rde.nsmap)
    rde_container.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    rde_container.set("xsi:schemaLocation", "http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd")
    
    # Copiar hijos al nuevo rDE
    for child in rde:
        rde_container.append(child)
    
    # Guardar XML final
    xml_final = etree.tostring(rde_container, encoding='utf-8', xml_declaration=True)
    Path(output_path).write_bytes(xml_final)
    
    print(f"\n✅ XML generado: {output_path}")
    print(f"   CDC: {nuevo_cdc_completo}")
    
    return output_path, nuevo_cdc_completo

def main():
    parser = argparse.ArgumentParser(description="Generar XML SIFEN válido")
    parser.add_argument('--ruc', required=True, help='RUC (sin DV)')
    parser.add_argument('--dv', required=True, help='DV del RUC')
    parser.add_argument('--timbrado', required=True, help='Número de timbrado')
    parser.add_argument('--establecimiento', default='001', help='Código establecimiento')
    parser.add_argument('--punto-exp', default='001', help='Punto de expedición')
    parser.add_argument('--num-doc', required=True, help='Número de documento (7 dígitos)')
    parser.add_argument('--output', required=True, help='Archivo de salida')
    
    args = parser.parse_args()
    
    # Formatear número de documento
    num_doc = str(args.num_doc).zfill(7)
    
    try:
        xml_path, cdc = generar_xml_valido(
            args.ruc, args.dv, args.timbrado,
            args.establecimiento, args.punto_exp,
            num_doc, args.output
        )
        
        print(f"\n🎯 XML listo para usar:")
        print(f"   Archivo: {xml_path}")
        print(f"   CDC: {cdc}")
        print(f"\n📋 Próximos pasos:")
        print(f"   1. Validar en Prevalidador SIFEN")
        print(f"   2. Firmar con send_sirecepde.py")
        print(f"   3. Enviar a SIFEN")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
