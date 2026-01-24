#!/usr/bin/env python3
"""
Construye un DE XML mínimo válido para testing (alineado al XSD v150)
"""
from datetime import datetime, timezone
from uuid import uuid4
import xml.etree.ElementTree as ET
import os

def build_minimal_de_v150(allow_placeholder: bool = False) -> bytes:
    """
    Construye un Documento Electrónico (DE) mínimo válido según SIFEN v150
    
    Args:
        allow_placeholder: Si True, permite usar placeholders genéricos.
                          Si False (default), exige datos reales del emisor.
    
    Estructura basada en el XSD oficial:
    - tDE contiene: dDVId, dFecFirma, dSisFact, gOpeDE, gTimb, gDatGralOpe, gDtipDE
    - gDatGralOpe contiene: dFeEmiDE, gOpeCom (opcional), gEmis, gDatRec
    - gEmis contiene: dRucEm, dDVEmi, iTipCont, dNomEmi, dDirEmi, dNumCas, cDepEmi, dDesDepEmi, cCiuEmi, dDesCiuEmi, dTelEmi, dEmailE, gActEco
    - gDtipDE contiene: gCamFE (para facturas), gCamItem
    
    Returns:
        XML del DE en bytes
    """
    # Namespace SIFEN
    SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
    
    # Generar IDs únicos
    timbrado_id = str(uuid4())
    de_id = f"DE{timbrado_id[:36]}"  # Asegurar que no exceda 36 chars
    
    # Obtener parámetros de environment variables
    ruc = os.getenv("SIFEN_RUC")
    dv = os.getenv("SIFEN_DV")
    timbrado = os.getenv("SIFEN_TIMBRADO")
    est = os.getenv("SIFEN_EST")
    pun_exp = os.getenv("SIFEN_PUN_EXP")
    num_doc = os.getenv("SIFEN_NUM_DOC")
    timb_fe_ini = os.getenv("SIFEN_TIMBRADO_FE_INI")
    timb_fe_fin = os.getenv("SIFEN_TIMBRADO_FE_FIN")
    
    # Validar datos del emisor
    if not allow_placeholder:
        missing = []
        if not ruc:
            missing.append("SIFEN_RUC")
        if not dv:
            missing.append("SIFEN_DV")
        if not timbrado:
            missing.append("SIFEN_TIMBRADO")
        if not est:
            missing.append("SIFEN_EST")
        if not pun_exp:
            missing.append("SIFEN_PUN_EXP")
        if not num_doc:
            missing.append("SIFEN_NUM_DOC")
        
        if missing:
            raise ValueError(
                f"Faltan datos del emisor (obligatorios para envío real): {', '.join(missing)}. "
                f"Exportá las variables de entorno o usá --allow-placeholder solo para testing."
            )
    
    # Usar placeholders solo si se permite o si faltan datos (fallback)
    ruc = ruc or "12345678"
    dv = dv or "9"
    timbrado = timbrado or "12345678"
    est = est or "1"
    pun_exp = pun_exp or "001"
    num_doc = num_doc or "1"
    
    # Crear root con namespace
    DE = ET.Element(f"{{{SIFEN_NS}}}DE")
    DE.set("Id", de_id)
    
    # dDVId (dígito verificador del CDC)
    dDVId = ET.SubElement(DE, f"{{{SIFEN_NS}}}dDVId")
    dDVId.text = dv
    
    # dFecFirma (fecha y hora de firma)
    dFecFirma = ET.SubElement(DE, f"{{{SIFEN_NS}}}dFecFirma")
    now = datetime.now(timezone.utc)
    dFecFirma.text = now.strftime("%Y-%m-%dT%H:%M:%S")
    
    # dSisFact (sistema de facturación)
    dSisFact = ET.SubElement(DE, f"{{{SIFEN_NS}}}dSisFact")
    dSisFact.text = "1"
    
    # gOpeDE (datos de la operación)
    gOpeDE = ET.SubElement(DE, f"{{{SIFEN_NS}}}gOpeDE")
    
    # iTipEmi (tipo de emisión)
    iTipEmi = ET.SubElement(gOpeDE, f"{{{SIFEN_NS}}}iTipEmi")
    iTipEmi.text = "1"  # Normal
    
    # dDesTipEmi (descripción tipo emisión)
    dDesTipEmi = ET.SubElement(gOpeDE, f"{{{SIFEN_NS}}}dDesTipEmi")
    dDesTipEmi.text = "Normal"
    
    # dCodSeg (código de seguridad)
    dCodSeg = ET.SubElement(gOpeDE, f"{{{SIFEN_NS}}}dCodSeg")
    import re
    digits = re.sub(r"\D", "", str(timbrado_id))
    dCodSeg.text = digits[-9:].zfill(9)
    
    # gTimb (datos del timbrado)
    gTimb = ET.SubElement(DE, f"{{{SIFEN_NS}}}gTimb")
    
    # iTiDE (tipo de documento electrónico)
    iTiDE = ET.SubElement(gTimb, f"{{{SIFEN_NS}}}iTiDE")
    iTiDE.text = "1"  # Factura electrónica
    
    # dDesTiDE (descripción tipo DE)
    dDesTiDE = ET.SubElement(gTimb, f"{{{SIFEN_NS}}}dDesTiDE")
    dDesTiDE.text = "Factura electrónica"
    
    # dNumTim (número de timbrado)
    dNumTim = ET.SubElement(gTimb, f"{{{SIFEN_NS}}}dNumTim")
    dNumTim.text = timbrado
    
    # dEst (establecimiento)
    dEst = ET.SubElement(gTimb, f"{{{SIFEN_NS}}}dEst")
    dEst.text = est
    
    # dPunExp (punto de expedición)
    dPunExp = ET.SubElement(gTimb, f"{{{SIFEN_NS}}}dPunExp")
    dPunExp.text = pun_exp
    
    # dNumDoc (número de documento)
    dNumDoc = ET.SubElement(gTimb, f"{{{SIFEN_NS}}}dNumDoc")
    dNumDoc.text = num_doc
    
    # dFeIniT (fecha de inicio de vigencia del timbrado)
    dFeIniT = ET.SubElement(gTimb, f"{{{SIFEN_NS}}}dFeIniT")
    if timb_fe_ini:
        dFeIniT.text = timb_fe_ini
    else:
        dFeIniT.text = now.strftime("%Y-%m-%d")
    
    # dFeFinT (fecha de fin de vigencia del timbrado) - opcional
    if timb_fe_fin:
        dFeFinT = ET.SubElement(gTimb, f"{{{SIFEN_NS}}}dFeFinT")
        dFeFinT.text = timb_fe_fin
    
    # gDatGralOpe (datos generales de la operación)
    gDatGralOpe = ET.SubElement(DE, f"{{{SIFEN_NS}}}gDatGralOpe")
    
    # dFeEmiDE (fecha y hora de emisión del DE)
    dFeEmiDE = ET.SubElement(gDatGralOpe, f"{{{SIFEN_NS}}}dFeEmiDE")
    dFeEmiDE.text = now.strftime("%Y-%m-%dT%H:%M:%S")
    
    # gOpeCom (datos de la operación comercial)
    gOpeCom = ET.SubElement(gDatGralOpe, f"{{{SIFEN_NS}}}gOpeCom")
    
    # iTImp (tipo de impuesto)
    iTImp = ET.SubElement(gOpeCom, f"{{{SIFEN_NS}}}iTImp")
    iTImp.text = "1"  # IVA
    
    # dDesTImp (descripción tipo impuesto)
    dDesTImp = ET.SubElement(gOpeCom, f"{{{SIFEN_NS}}}dDesTImp")
    dDesTImp.text = "IVA"
    
    # cMoneOpe (moneda de la operación)
    cMoneOpe = ET.SubElement(gOpeCom, f"{{{SIFEN_NS}}}cMoneOpe")
    cMoneOpe.text = "PYG"
    
    # dDesMoneOpe (descripción moneda)
    dDesMoneOpe = ET.SubElement(gOpeCom, f"{{{SIFEN_NS}}}dDesMoneOpe")
    dDesMoneOpe.text = "Guaraní"
    
    # gEmis (datos del emisor)
    gEmis = ET.SubElement(gDatGralOpe, f"{{{SIFEN_NS}}}gEmis")
    
    # dRucEm (RUC del emisor)
    dRucEm = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}dRucEm")
    dRucEm.text = ruc
    
    # dDVEmi (dígito verificador del emisor)
    dDVEmi = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}dDVEmi")
    dDVEmi.text = dv
    
    # iTipCont (tipo de contribuyente)
    iTipCont = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}iTipCont")
    iTipCont.text = "1"  # Contribuyente IVA
    
    # dNomEmi (nombre del emisor)
    dNomEmi = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}dNomEmi")
    dNomEmi.text = "EMPRESA DE PRUEBA S.A."
    
    # dDirEmi (dirección del emisor)
    dDirEmi = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}dDirEmi")
    dDirEmi.text = "DIRECCION DE PRUEBA"
    
    # dNumCas (número de casa)
    dNumCas = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}dNumCas")
    dNumCas.text = "123"
    
    # cDepEmi (código departamento)
    cDepEmi = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}cDepEmi")
    cDepEmi.text = "1"  # Asunción
    
    # dDesDepEmi (descripción departamento)
    dDesDepEmi = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}dDesDepEmi")
    dDesDepEmi.text = "ASUNCION"
    
    # cCiuEmi (código ciudad)
    cCiuEmi = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}cCiuEmi")
    cCiuEmi.text = "1"  # Asunción
    
    # dDesCiuEmi (descripción ciudad)
    dDesCiuEmi = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}dDesCiuEmi")
    dDesCiuEmi.text = "ASUNCION"
    
    # dTelEmi (teléfono del emisor)
    dTelEmi = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}dTelEmi")
    dTelEmi.text = "(021) 123456"
    
    # dEmailE (email del emisor)
    dEmailE = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}dEmailE")
    dEmailE.text = "email@prueba.com"
    
    # gActEco (actividad económica)
    gActEco = ET.SubElement(gEmis, f"{{{SIFEN_NS}}}gActEco")
    
    # cActEco (código actividad económica)
    cActEco = ET.SubElement(gActEco, f"{{{SIFEN_NS}}}cActEco")
    cActEco.text = "123456"
    
    # dDesActEco (descripción actividad económica)
    dDesActEco = ET.SubElement(gActEco, f"{{{SIFEN_NS}}}dDesActEco")
    dDesActEco.text = "ACTIVIDAD DE PRUEBA"
    
    # gDatRec (datos del receptor)
    gDatRec = ET.SubElement(gDatGralOpe, f"{{{SIFEN_NS}}}gDatRec")
    
    # iNatRec (naturaleza del receptor)
    iNatRec = ET.SubElement(gDatRec, f"{{{SIFEN_NS}}}iNatRec")
    iNatRec.text = "1"  # Contribuyente
    
    # iTiOpe (tipo de operación)
    iTiOpe = ET.SubElement(gDatRec, f"{{{SIFEN_NS}}}iTiOpe")
    iTiOpe.text = "1"  # Exportación
    
    # cPaisRec (código país del receptor)
    cPaisRec = ET.SubElement(gDatRec, f"{{{SIFEN_NS}}}cPaisRec")
    cPaisRec.text = "PRY"
    
    # dDesPaisRe (descripción país)
    dDesPaisRe = ET.SubElement(gDatRec, f"{{{SIFEN_NS}}}dDesPaisRe")
    dDesPaisRe.text = "PARAGUAY"
    
    # dRucRec (RUC del receptor)
    dRucRec = ET.SubElement(gDatRec, f"{{{SIFEN_NS}}}dRucRec")
    dRucRec.text = "80000000"
    
    # dDVRec (dígito verificador del receptor)
    dDVRec = ET.SubElement(gDatRec, f"{{{SIFEN_NS}}}dDVRec")
    dDVRec.text = "0"
    
    # dNomRec (nombre del receptor)
    dNomRec = ET.SubElement(gDatRec, f"{{{SIFEN_NS}}}dNomRec")
    dNomRec.text = "CLIENTE DE PRUEBA"
    
    # gDtipDE (campos específicos del tipo de DE)
    gDtipDE = ET.SubElement(DE, f"{{{SIFEN_NS}}}gDtipDE")
    
    # gCamFE (campos de factura electrónica)
    gCamFE = ET.SubElement(gDtipDE, f"{{{SIFEN_NS}}}gCamFE")
    
    # iIndPres (tipo de presentación)
    iIndPres = ET.SubElement(gCamFE, f"{{{SIFEN_NS}}}iIndPres")
    iIndPres.text = "1"  # Normal
    
    # dDesIndPres (descripción tipo presentación)
    dDesIndPres = ET.SubElement(gCamFE, f"{{{SIFEN_NS}}}dDesIndPres")
    dDesIndPres.text = "Normal"
    
    # gCamItem (ítems)
    gCamItem = ET.SubElement(gDtipDE, f"{{{SIFEN_NS}}}gCamItem")
    
    # Un solo ítem mínimo
    gItem = ET.SubElement(gCamItem, f"{{{SIFEN_NS}}}gItem")
    
    # dCodInt (código interno)
    dCodInt = ET.SubElement(gItem, f"{{{SIFEN_NS}}}dCodInt")
    dCodInt.text = "001"
    
    # dDesProSer (descripción del producto o servicio)
    dDesProSer = ET.SubElement(gItem, f"{{{SIFEN_NS}}}dDesProSer")
    dDesProSer.text = "ITEM DE PRUEBA"
    
    # cUniMed (código unidad de medida)
    cUniMed = ET.SubElement(gItem, f"{{{SIFEN_NS}}}cUniMed")
    cUniMed.text = "77"  # Unidad
    
    # dDesUniMed (descripción unidad de medida)
    dDesUniMed = ET.SubElement(gItem, f"{{{SIFEN_NS}}}dDesUniMed")
    dDesUniMed.text = "UNI"
    
    # dCantProSer (cantidad)
    dCantProSer = ET.SubElement(gItem, f"{{{SIFEN_NS}}}dCantProSer")
    dCantProSer.text = "1"
    
    # gValorItem (valores del ítem)
    gValorItem = ET.SubElement(gItem, f"{{{SIFEN_NS}}}gValorItem")
    
    # dPUniProSer (precio unitario)
    dPUniProSer = ET.SubElement(gValorItem, f"{{{SIFEN_NS}}}dPUniProSer")
    dPUniProSer.text = "1000000"  # 1.000.000 Guaraníes
    
    # dTotBruOpeItem (total bruto del ítem)
    dTotBruOpeItem = ET.SubElement(gValorItem, f"{{{SIFEN_NS}}}dTotBruOpeItem")
    dTotBruOpeItem.text = "1000000"
    
    # gValorRestaItem (descuentos y total del ítem)
    gValorRestaItem = ET.SubElement(gValorItem, f"{{{SIFEN_NS}}}gValorRestaItem")
    
    # dDescItem (descuento del ítem)
    dDescItem = ET.SubElement(gValorRestaItem, f"{{{SIFEN_NS}}}dDescItem")
    dDescItem.text = "0"
    
    # dTotOpeItem (total operación del ítem)
    dTotOpeItem = ET.SubElement(gValorRestaItem, f"{{{SIFEN_NS}}}dTotOpeItem")
    dTotOpeItem.text = "1000000"
    
    # gTotSub (totales del subtotal)
    gTotSub = ET.SubElement(DE, f"{{{SIFEN_NS}}}gTotSub")
    
    # dTotGralOp (total general de la operación)
    dTotGralOp = ET.SubElement(gTotSub, f"{{{SIFEN_NS}}}dTotGralOp")
    dTotGralOp.text = "1000000"
    
    # dTotIVA (total IVA)
    dTotIVA = ET.SubElement(gTotSub, f"{{{SIFEN_NS}}}dTotIVA")
    dTotIVA.text = "0"  # Exento para simplicidad
    
    # dTotGrav (total gravado)
    dTotGrav = ET.SubElement(gTotSub, f"{{{SIFEN_NS}}}dTotGrav")
    dTotGrav.text = "0"
    
    # dTotExe (total exento)
    dTotExe = ET.SubElement(gTotSub, f"{{{SIFEN_NS}}}dTotExe")
    dTotExe.text = "1000000"
    
    # Serializar XML
    xml_str = ET.tostring(DE, encoding='unicode', method='xml')
    
    # Agregar declaración XML
    xml_bytes = f'<?xml version="1.0" encoding="UTF-8"?>{xml_str}'.encode('utf-8')
    
    return xml_bytes

if __name__ == "__main__":
    import sys
    import argparse
    from pathlib import Path
    
    parser = argparse.ArgumentParser(description='Construir DE mínimo v150')
    parser.add_argument('--allow-placeholder', action='store_true',
                       help='Permite usar placeholders genéricos (solo para testing)')
    args = parser.parse_args()
    
    # Guardar DE generado
    output_path = Path("artifacts/de_minimo_v150.xml")
    output_path.parent.mkdir(exist_ok=True)
    
    try:
        xml_bytes = build_minimal_de_v150(allow_placeholder=args.allow_placeholder)
        output_path.write_bytes(xml_bytes)
        
        print(f"DE mínimo v150 guardado en: {output_path}")
        print(f"Tamaño: {len(xml_bytes)} bytes")
        
        # Mostrar parámetros usados
        print("\nParámetros usados:")
        print(f"  RUC: {os.getenv('SIFEN_RUC', '12345678')}")
        print(f"  DV: {os.getenv('SIFEN_DV', '9')}")
        print(f"  Timbrado: {os.getenv('SIFEN_TIMBRADO', '12345678')}")
        print(f"  Establecimiento: {os.getenv('SIFEN_EST', '1')}")
        print(f"  Punto Expedición: {os.getenv('SIFEN_PUN_EXP', '001')}")
        print(f"  Número Documento: {os.getenv('SIFEN_NUM_DOC', '1')}")
        if os.getenv('SIFEN_TIMBRADO_FE_INI'):
            print(f"  Fe. Ini. Timbrado: {os.getenv('SIFEN_TIMBRADO_FE_INI')}")
        if os.getenv('SIFEN_TIMBRADO_FE_FIN'):
            print(f"  Fe. Fin. Timbrado: {os.getenv('SIFEN_TIMBRADO_FE_FIN')}")
        
        if args.allow_placeholder:
            print("\n⚠️  Modo placeholder activado (solo para testing)")
    
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
