#!/usr/bin/env python3
"""
Genera XML SIFEN completamente desde cero - sin usar templates existentes
Basado en estructura correcta de Roshka jsifenlib
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone
from lxml import etree
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.xml_generator_v150 import generate_cdc
from tools.catalogos.distritos_py import get_descripcion_distrito, get_descripcion_departamento
from tools.catalogos.ciudades_py import get_descripcion_ciudad

def crear_xml_desde_cero(ruc, dv, timbrado, num_doc, output_path):
    """
    Crea XML SIFEN completamente desde cero con estructura correcta
    """

    print("🏗️  Creando XML SIFEN completamente desde cero...")
    print(f"   RUC: {ruc}-{dv}")
    print(f"   Timbrado: {timbrado}")
    print(f"   Documento: {num_doc}")

    # === CALCULAR CDC PRIMERO ===
    # Usar fecha fija para evitar problemas de timezone
    fecha_cdc = "20260114"  # Fecha fija YYYYMMDD
    tipo_doc = "01"  # Factura electrónica (2 dígitos para CDC)
    establecimiento = "029"
    punto_exp = "010"
    monto = "114500"
    
    cdc = generate_cdc(
        ruc, timbrado, establecimiento, punto_exp,
        num_doc, tipo_doc, fecha_cdc, monto
    )

    print(f"   CDC calculado: {cdc}")

    # === CREAR ESTRUCTURA XML COMPLETA ===
    SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
    XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

    # Crear root con namespace por defecto (sin prefijo)
    nsmap = {None: SIFEN_NS, "xsi": XSI_NS}
    root = etree.Element("rDE", nsmap=nsmap)
    root.set(f"{{{XSI_NS}}}schemaLocation", f"{SIFEN_NS} siRecepDE_v150.xsd")

    # dVerFor
    etree.SubElement(root, "dVerFor").text = "150"

    # DE con CDC
    de = etree.SubElement(root, "DE")
    de.set("Id", cdc)

    # dDVId
    etree.SubElement(de, "dDVId").text = str(int(cdc[-1]))

    # dFecFirma
    etree.SubElement(de, "dFecFirma").text = "2025-01-13T10:00:00"

    # dSisFact
    etree.SubElement(de, "dSisFact").text = "1"

    # gOpeDE
    gOpeDE = etree.SubElement(de, "gOpeDE")
    etree.SubElement(gOpeDE, "iTipEmi").text = "1"
    etree.SubElement(gOpeDE, "dDesTipEmi").text = "Normal"
    etree.SubElement(gOpeDE, "dCodSeg").text = "000000001"

    # gTimb
    gTimb = etree.SubElement(de, "gTimb")
    etree.SubElement(gTimb, "iTiDE").text = "1"
    etree.SubElement(gTimb, "dDesTiDE").text = "Factura electrónica"
    etree.SubElement(gTimb, "dNumTim").text = timbrado
    etree.SubElement(gTimb, "dEst").text = establecimiento
    etree.SubElement(gTimb, "dPunExp").text = punto_exp
    etree.SubElement(gTimb, "dNumDoc").text = num_doc
    etree.SubElement(gTimb, "dFeIniT").text = "2023-03-16"

    # gDatGralOpe
    gDatGralOpe = etree.SubElement(de, "gDatGralOpe")
    etree.SubElement(gDatGralOpe, "dFeEmiDE").text = "2026-01-14T10:00:00"

    # gOpeCom
    gOpeCom = etree.SubElement(gDatGralOpe, "gOpeCom")
    etree.SubElement(gOpeCom, "iTipTra").text = "1"
    etree.SubElement(gOpeCom, "dDesTipTra").text = "Venta de mercadería"
    etree.SubElement(gOpeCom, "iTImp").text = "1"
    etree.SubElement(gOpeCom, "dDesTImp").text = "IVA"
    etree.SubElement(gOpeCom, "cMoneOpe").text = "PYG"
    etree.SubElement(gOpeCom, "dDesMoneOpe").text = "Guarani"

    # gEmis
    gEmis = etree.SubElement(gDatGralOpe, "gEmis")
    etree.SubElement(gEmis, "dRucEm").text = ruc
    etree.SubElement(gEmis, "dDVEmi").text = dv
    etree.SubElement(gEmis, "iTipCont").text = "1"
    etree.SubElement(gEmis, "cTipReg").text = "2"
    etree.SubElement(gEmis, "dNomEmi").text = "EMPRESA DE PRUEBA S.A."
    etree.SubElement(gEmis, "dNomFanEmi").text = "EMPRESA DE PRUEBA"
    etree.SubElement(gEmis, "dDirEmi").text = "AVDA. ESPAÑA 123"
    etree.SubElement(gEmis, "dNumCas").text = "0"
    etree.SubElement(gEmis, "dCompDir1").text = "N/A"
    etree.SubElement(gEmis, "dCompDir2").text = "N/A"
    etree.SubElement(gEmis, "cDepEmi").text = "12"
    etree.SubElement(gEmis, "dDesDepEmi").text = "CENTRAL"
    etree.SubElement(gEmis, "cDisEmi").text = "169"
    etree.SubElement(gEmis, "dDesDisEmi").text = "LAMBARE"
    etree.SubElement(gEmis, "cCiuEmi").text = "6106"
    etree.SubElement(gEmis, "dDesCiuEmi").text = "LAMBARE"
    etree.SubElement(gEmis, "dTelEmi").text = "0971 123456"
    etree.SubElement(gEmis, "dEmailE").text = "info@empresa.com.py"
    etree.SubElement(gEmis, "dDenSuc").text = "LAMBARE"
    # gActEco - Actividad económica
    gActEco = etree.SubElement(gEmis, "gActEco")
    etree.SubElement(gActEco, "cActEco").text = "46103"
    etree.SubElement(gActEco, "dDesActEco").text = "COMERCIO AL POR MAYOR DE ALIMENTOS, BEBIDAS Y TABACO A CAMBIO DE UNA RETRIBUCIÓN O POR CONTRATA"

    # gDatRec
    gDatRec = etree.SubElement(gDatGralOpe, "gDatRec")
    etree.SubElement(gDatRec, "iNatRec").text = "1"
    etree.SubElement(gDatRec, "iTiOpe").text = "1"
    etree.SubElement(gDatRec, "cPaisRec").text = "PRY"
    etree.SubElement(gDatRec, "dDesPaisRe").text = "Paraguay"
    etree.SubElement(gDatRec, "iTiContRec").text = "1"
    etree.SubElement(gDatRec, "dRucRec").text = "7524653"
    etree.SubElement(gDatRec, "dDVRec").text = "8"
    etree.SubElement(gDatRec, "dNomRec").text = "CONSUMIDOR FINAL"
    etree.SubElement(gDatRec, "dDirRec").text = "CIUDAD DEL ESTE"
    etree.SubElement(gDatRec, "dNumCasRec").text = "0"
    
    # Departamento - usar catálogo
    cod_dep_rec = "11"
    etree.SubElement(gDatRec, "cDepRec").text = cod_dep_rec
    desc_dep_rec = get_descripcion_departamento(cod_dep_rec)
    if desc_dep_rec:
        etree.SubElement(gDatRec, "dDesDepRec").text = desc_dep_rec
    else:
        etree.SubElement(gDatRec, "dDesDepRec").text = "ALTO PARANA"
    
    # Distrito - usar catálogo para obtener descripción correcta
    cod_dis_rec = "145"  # Ciudad del Este (código global)
    etree.SubElement(gDatRec, "cDisRec").text = cod_dis_rec
    desc_dis_rec = get_descripcion_distrito(cod_dis_rec)
    if desc_dis_rec:
        etree.SubElement(gDatRec, "dDesDisRec").text = desc_dis_rec
    else:
        # Si no encuentra en catálogo, no genera XML para evitar error
        raise ValueError(f"No se encontró descripción para distrito {cod_dis_rec}")
    
    # Ciudad - usar catálogo para obtener descripción correcta
    cod_ciu_rec = "3428"  # Ciudad del Este (Planta Urbana)
    etree.SubElement(gDatRec, "cCiuRec").text = cod_ciu_rec
    desc_ciu_rec = get_descripcion_ciudad(cod_ciu_rec)
    if desc_ciu_rec:
        etree.SubElement(gDatRec, "dDesCiuRec").text = desc_ciu_rec
    else:
        # Si no encuentra en catálogo, no genera XML para evitar error
        raise ValueError(f"No se encontró descripción para ciudad {cod_ciu_rec}")
    etree.SubElement(gDatRec, "dTelRec").text = "0981 765432"
    etree.SubElement(gDatRec, "dEmailRec").text = "cliente@email.com"

    # gDtipDE
    gDtipDE = etree.SubElement(de, "gDtipDE")
    
    # gCamFE - Campos de Factura Electrónica
    gCamFE = etree.SubElement(gDtipDE, "gCamFE")
    etree.SubElement(gCamFE, "iIndPres").text = "1"
    etree.SubElement(gCamFE, "dDesIndPres").text = "Operación presencial"
    
    # gCamCond - Condiciones de pago
    gCamCond = etree.SubElement(gDtipDE, "gCamCond")
    etree.SubElement(gCamCond, "iCondOpe").text = "1"
    etree.SubElement(gCamCond, "dDCondOpe").text = "Contado"
    gPaConEIni = etree.SubElement(gCamCond, "gPaConEIni")
    etree.SubElement(gPaConEIni, "iTiPago").text = "1"
    etree.SubElement(gPaConEIni, "dDesTiPag").text = "Efectivo"
    etree.SubElement(gPaConEIni, "dMonTiPag").text = "114500.0000"
    etree.SubElement(gPaConEIni, "cMoneTiPag").text = "PYG"
    etree.SubElement(gPaConEIni, "dDMoneTiPag").text = "Guarani"
    
    # Item 1
    gCamItem = etree.SubElement(gDtipDE, "gCamItem")
    etree.SubElement(gCamItem, "dCodInt").text = "001"
    etree.SubElement(gCamItem, "dDesProSer").text = "PRODUCTO DE VENTA"
    etree.SubElement(gCamItem, "cUniMed").text = "77"
    etree.SubElement(gCamItem, "dDesUniMed").text = "UNI"
    etree.SubElement(gCamItem, "dCantProSer").text = "1.0000"
    gValorItem = etree.SubElement(gCamItem, "gValorItem")
    etree.SubElement(gValorItem, "dPUniProSer").text = "100000.00000000"
    etree.SubElement(gValorItem, "dTotBruOpeItem").text = "100000.00000000"
    gValorRestaItem = etree.SubElement(gValorItem, "gValorRestaItem")
    etree.SubElement(gValorRestaItem, "dTotOpeItem").text = "100000.00000000"
    gCamIVA = etree.SubElement(gCamItem, "gCamIVA")
    etree.SubElement(gCamIVA, "iAfecIVA").text = "1"
    etree.SubElement(gCamIVA, "dDesAfecIVA").text = "Gravado IVA"
    etree.SubElement(gCamIVA, "dPropIVA").text = "100.00000000"
    etree.SubElement(gCamIVA, "dTasaIVA").text = "10"
    etree.SubElement(gCamIVA, "dBasGravIVA").text = "90909.09000000"
    etree.SubElement(gCamIVA, "dLiqIVAItem").text = "9090.91000000"
    etree.SubElement(gCamIVA, "dBasExe").text = "0.00000000"

    # Item 2
    gCamItem2 = etree.SubElement(gDtipDE, "gCamItem")
    etree.SubElement(gCamItem2, "dCodInt").text = "002"
    etree.SubElement(gCamItem2, "dDesProSer").text = "SERVICIO PROFESIONAL"
    etree.SubElement(gCamItem2, "cUniMed").text = "77"
    etree.SubElement(gCamItem2, "dDesUniMed").text = "UNI"
    etree.SubElement(gCamItem2, "dCantProSer").text = "1.0000"
    gValorItem2 = etree.SubElement(gCamItem2, "gValorItem")
    etree.SubElement(gValorItem2, "dPUniProSer").text = "14500.00000000"
    etree.SubElement(gValorItem2, "dTotBruOpeItem").text = "14500.00000000"
    gValorRestaItem2 = etree.SubElement(gValorItem2, "gValorRestaItem")
    etree.SubElement(gValorRestaItem2, "dTotOpeItem").text = "14500.00000000"
    gCamIVA2 = etree.SubElement(gCamItem2, "gCamIVA")
    etree.SubElement(gCamIVA2, "iAfecIVA").text = "1"
    etree.SubElement(gCamIVA2, "dDesAfecIVA").text = "Gravado IVA"
    etree.SubElement(gCamIVA2, "dPropIVA").text = "100.00000000"
    etree.SubElement(gCamIVA2, "dTasaIVA").text = "10"
    etree.SubElement(gCamIVA2, "dBasGravIVA").text = "13181.82000000"
    etree.SubElement(gCamIVA2, "dLiqIVAItem").text = "1318.18000000"
    etree.SubElement(gCamIVA2, "dBasExe").text = "0.00000000"

    # gTotSub
    gTotSub = etree.SubElement(de, "gTotSub")
    etree.SubElement(gTotSub, "dSubExe").text = "0.00000000"
    etree.SubElement(gTotSub, "dSub5").text = "0.00000000"
    etree.SubElement(gTotSub, "dSub10").text = "114500.00000000"
    etree.SubElement(gTotSub, "dTotOpe").text = "114500.00000000"
    etree.SubElement(gTotSub, "dTotDesc").text = "0.00000000"
    etree.SubElement(gTotSub, "dTotDescGlotem").text = "0.00000000"
    etree.SubElement(gTotSub, "dTotAntItem").text = "0.00000000"
    etree.SubElement(gTotSub, "dTotAnt").text = "0.00000000"
    etree.SubElement(gTotSub, "dPorcDescTotal").text = "0.00000000"
    etree.SubElement(gTotSub, "dDescTotal").text = "0.00000000"
    etree.SubElement(gTotSub, "dAnticipo").text = "0.00000000"
    etree.SubElement(gTotSub, "dRedon").text = "0.0000"
    etree.SubElement(gTotSub, "dTotGralOpe").text = "114500.00000000"
    etree.SubElement(gTotSub, "dIVA5").text = "0.00000000"
    etree.SubElement(gTotSub, "dIVA10").text = "10409.00000000"
    etree.SubElement(gTotSub, "dTotIVA").text = "10409.00000000"
    etree.SubElement(gTotSub, "dBaseGrav5").text = "0.00000000"
    etree.SubElement(gTotSub, "dBaseGrav10").text = "104091.00000000"
    etree.SubElement(gTotSub, "dTBasGraIVA").text = "104091.00000000"

    # Guardar XML sin firma
    xml_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True, standalone=False)
    Path(output_path).write_bytes(xml_bytes)

    print(f"✅ XML creado desde cero: {output_path}")
    print(f"   Estructura completa generada")
    print(f"   CDC calculado: {cdc}")
    print(f"   Datos del usuario aplicados")

    return output_path, cdc

def main():
    parser = argparse.ArgumentParser(description="Generar XML SIFEN desde cero")
    parser.add_argument('--ruc', required=True, help='RUC (sin DV)')
    parser.add_argument('--dv', required=True, help='DV del RUC')
    parser.add_argument('--timbrado', required=True, help='Número de timbrado')
    parser.add_argument('--num-doc', required=True, help='Número documento (7 dígitos)')
    parser.add_argument('--output', required=True, help='XML de salida')

    args = parser.parse_args()
    num_doc = str(args.num_doc).zfill(7)

    try:
        xml_path, cdc = crear_xml_desde_cero(
            args.ruc, args.dv, args.timbrado, num_doc, args.output
        )
        print(f"\n🎯 XML listo para firmar:")
        print(f"   Archivo: {xml_path}")
        print(f"   CDC: {cdc}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
