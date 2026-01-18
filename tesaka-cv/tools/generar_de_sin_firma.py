#!/usr/bin/env python3
"""
Generar un XML DE con todos los requisitos segun ejemplo oficial SIFEN
pero SIN firma para que el sistema la agregue.
"""

from lxml import etree
import uuid
import sys
from datetime import datetime

# Namespace
SIFEN_NS = 'http://ekuatia.set.gov.py/sifen/xsd'
XSI_NS = 'http://www.w3.org/2001/XMLSchema-instance'

def generar_de_sin_firma():
    # Generar IDs únicos
    de_id = f"018004554737010010000001{datetime.now().strftime('%Y%m%d%H%M%S')}123456789"  # Usando RUC real
    rde_id = f"rDE{de_id}"
    
    # Crear rDE con Id y xsi:schemaLocation (como en el ejemplo)
    rde = etree.Element(f'{{{SIFEN_NS}}}rDE', 
                       Id=rde_id,
                       nsmap={None: SIFEN_NS, 'xsi': XSI_NS})
    rde.set(f'{{{XSI_NS}}}schemaLocation', 
            'http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd')
    
    # dVerFor primero (obligatorio)
    dver = etree.SubElement(rde, f'{{{SIFEN_NS}}}dVerFor')
    dver.text = '150'
    
    # DE con Id diferente
    de = etree.SubElement(rde, f'{{{SIFEN_NS}}}DE', Id=de_id)
    
    # Contenido básico del DE
    etree.SubElement(de, f'{{{SIFEN_NS}}}dDVId').text = '1'
    etree.SubElement(de, f'{{{SIFEN_NS}}}dFecFirma').text = datetime.now().isoformat()
    etree.SubElement(de, f'{{{SIFEN_NS}}}dSisFact').text = '1'
    
    # gOpeDE
    gOpeDE = etree.SubElement(de, f'{{{SIFEN_NS}}}gOpeDE')
    etree.SubElement(gOpeDE, f'{{{SIFEN_NS}}}iTipEmi').text = '1'
    etree.SubElement(gOpeDE, f'{{{SIFEN_NS}}}dDesTipEmi').text = 'Normal'
    etree.SubElement(gOpeDE, f'{{{SIFEN_NS}}}dCodSeg').text = '000000023'
    etree.SubElement(gOpeDE, f'{{{SIFEN_NS}}}dInfoEmi').text = '1'
    etree.SubElement(gOpeDE, f'{{{SIFEN_NS}}}dInfoFisc').text = 'Información de interés del Fisco respecto al DE'
    
    # gTimb
    gTimb = etree.SubElement(de, f'{{{SIFEN_NS}}}gTimb')
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}iTiDE').text = '1'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dDesTiDE').text = 'Factura electrónica'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dNumTim').text = '12345678'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dEst').text = '001'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dPunExp').text = '001'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dNumDoc').text = '1000050'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dSerieNum').text = 'AB'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dFeIniT').text = '2019-08-13'
    
    # gDatGralOpe con gOpeCom
    gDatGralOpe = etree.SubElement(de, f'{{{SIFEN_NS}}}gDatGralOpe')
    etree.SubElement(gDatGralOpe, f'{{{SIFEN_NS}}}dFeEmiDE').text = datetime.now().isoformat()
    
    # gOpeCom - ESTE FALTABA!
    gOpeCom = etree.SubElement(gDatGralOpe, f'{{{SIFEN_NS}}}gOpeCom')
    etree.SubElement(gOpeCom, f'{{{SIFEN_NS}}}iTipTra').text = '1'
    etree.SubElement(gOpeCom, f'{{{SIFEN_NS}}}dDesTipTra').text = 'Venta de mercadería'
    etree.SubElement(gOpeCom, f'{{{SIFEN_NS}}}iTImp').text = '1'
    etree.SubElement(gOpeCom, f'{{{SIFEN_NS}}}dDesTImp').text = 'IVA'
    etree.SubElement(gOpeCom, f'{{{SIFEN_NS}}}cMoneOpe').text = 'PYG'
    etree.SubElement(gOpeCom, f'{{{SIFEN_NS}}}dDesMoneOpe').text = 'Guarani'
    
    # gEmis
    gEmis = etree.SubElement(gDatGralOpe, f'{{{SIFEN_NS}}}gEmis')
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dRucEm').text = '4554737'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dDVEmi').text = '8'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}iTipCont').text = '2'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}cTipReg').text = '3'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dNomEmi').text = 'Industrias Feris S.A.'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dDirEmi').text = 'CALLE 1 CASI CALLE 2'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dNumCas').text = '0'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}cDepEmi').text = '1'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dDesDepEmi').text = 'CAPITAL'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}cCiuEmi').text = '1'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dDesCiuEmi').text = 'ASUNCION (DISTRITO)'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dTelEmi').text = '012123456'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dEmailE').text = 'correo@correo.com'
    
    gActEco = etree.SubElement(gEmis, f'{{{SIFEN_NS}}}gActEco')
    etree.SubElement(gActEco, f'{{{SIFEN_NS}}}cActEco').text = '46510'
    etree.SubElement(gActEco, f'{{{SIFEN_NS}}}dDesActEco').text = 'COMERCIO AL POR MAYOR DE EQUIPOS INFORMÁTICOS Y SOFTWARE'
    
    # gDatRec
    gDatRec = etree.SubElement(gDatGralOpe, f'{{{SIFEN_NS}}}gDatRec')
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}iNatRec').text = '1'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}iTiOpe').text = '1'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}cPaisRec').text = 'PRY'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dDesPaisRe').text = 'Paraguay'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}iTiContRec').text = '2'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dRucRec').text = '4567890'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dDVRec').text = '1'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dNomRec').text = 'RECEPTOR DEL DOCUMENTO'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dDirRec').text = 'CALLE 1 ENTRE CALLE 2 Y CALLE 3'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dNumCasRec').text = '123'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}cDepRec').text = '1'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dDesDepRec').text = 'CAPITAL'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}cDisRec').text = '1'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dDesDisRec').text = 'ASUNCION (DISTRITO)'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}cCiuRec').text = '1'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dDesCiuRec').text = 'ASUNCION (DISTRITO)'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dTelRec').text = '012123456'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dCodCliente').text = 'AAA'
    
    # gDtipDE con gCamFE y gCamCond
    gDtipDE = etree.SubElement(de, f'{{{SIFEN_NS}}}gDtipDE')
    
    # gCamFE
    gCamFE = etree.SubElement(gDtipDE, f'{{{SIFEN_NS}}}gCamFE')
    etree.SubElement(gCamFE, f'{{{SIFEN_NS}}}iIndPres').text = '1'
    etree.SubElement(gCamFE, f'{{{SIFEN_NS}}}dDesIndPres').text = 'Operación presencial'
    
    # gCamCond
    gCamCond = etree.SubElement(gDtipDE, f'{{{SIFEN_NS}}}gCamCond')
    etree.SubElement(gCamCond, f'{{{SIFEN_NS}}}iCondOpe').text = '2'
    etree.SubElement(gCamCond, f'{{{SIFEN_NS}}}dDCondOpe').text = 'Crédito'
    
    gPagCred = etree.SubElement(gCamCond, f'{{{SIFEN_NS}}}gPagCred')
    etree.SubElement(gPagCred, f'{{{SIFEN_NS}}}iCondCred').text = '1'
    etree.SubElement(gPagCred, f'{{{SIFEN_NS}}}dDCondCred').text = 'Plazo'
    etree.SubElement(gPagCred, f'{{{SIFEN_NS}}}dPlazoCre').text = '28'
    
    # gCamItem
    gCamItem = etree.SubElement(gDtipDE, f'{{{SIFEN_NS}}}gCamItem')
    etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}dCodInt').text = 'CAC/CTAC'
    etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}dDesProSer').text = 'CUENTAS ACTIVAS'
    etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}cUniMed').text = '77'
    etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}dDesUniMed').text = 'UNI'
    etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}dCantProSer').text = '1'
    etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}dInfItem').text = '21'
    
    gValorItem = etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}gValorItem')
    etree.SubElement(gValorItem, f'{{{SIFEN_NS}}}dPUniProSer').text = '1100000'
    etree.SubElement(gValorItem, f'{{{SIFEN_NS}}}dTotBruOpeItem').text = '1100000'
    
    gValorRestaItem = etree.SubElement(gValorItem, f'{{{SIFEN_NS}}}gValorRestaItem')
    etree.SubElement(gValorRestaItem, f'{{{SIFEN_NS}}}dDescItem').text = '0'
    etree.SubElement(gValorRestaItem, f'{{{SIFEN_NS}}}dPorcDesIt').text = '0'
    etree.SubElement(gValorRestaItem, f'{{{SIFEN_NS}}}dDescGloItem').text = '0'
    etree.SubElement(gValorRestaItem, f'{{{SIFEN_NS}}}dTotOpeItem').text = '1100000'
    
    gCamIVA = etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}gCamIVA')
    etree.SubElement(gCamIVA, f'{{{SIFEN_NS}}}iAfecIVA').text = '1'
    etree.SubElement(gCamIVA, f'{{{SIFEN_NS}}}dDesAfecIVA').text = 'Gravado IVA'
    etree.SubElement(gCamIVA, f'{{{SIFEN_NS}}}dPropIVA').text = '100'
    etree.SubElement(gCamIVA, f'{{{SIFEN_NS}}}dTasaIVA').text = '10'
    etree.SubElement(gCamIVA, f'{{{SIFEN_NS}}}dBasGravIVA').text = '1000000'
    etree.SubElement(gCamIVA, f'{{{SIFEN_NS}}}dLiqIVAItem').text = '100000'
    
    # gTotSub
    gTotSub = etree.SubElement(de, f'{{{SIFEN_NS}}}gTotSub')
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dSubExe').text = '0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dSubExo').text = '0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dSub5').text = '0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dSub10').text = '2200000'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dTotOpe').text = '2200000'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dTotDesc').text = '0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dTotDescGlotem').text = '0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dTotAntItem').text = '0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dTotAnt').text = '0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dPorcDescTotal').text = '0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dDescTotal').text = '0.0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dAnticipo').text = '0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dRedon').text = '0.0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dTotGralOpe').text = '2200000'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dIVA5').text = '0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dIVA10').text = '200000'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dTotIVA').text = '200000'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dBaseGrav5').text = '0'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dBaseGrav10').text = '2000000'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dTBasGraIVA').text = '2000000'
    
    # NO agregamos Signature ni gCamFuFD - que el sistema lo haga
    
    # Serializar
    xml_bytes = etree.tostring(rde, xml_declaration=True, encoding='utf-8')
    
    return xml_bytes

if __name__ == '__main__':
    xml_bytes = generar_de_sin_firma()
    
    # Guardar
    output_file = sys.argv[1] if len(sys.argv) > 1 else 'test_rde_sin_firma.xml'
    with open(output_file, 'wb') as f:
        f.write(xml_bytes)
    
    print(f"XML generado: {output_file}")
    print(f"Tamaño: {len(xml_bytes)} bytes")
    
    # Verificar estructura
    from lxml import etree as ET
    root = ET.fromstring(xml_bytes)
    ns = {'s': SIFEN_NS}
    rde = root if root.tag.endswith('rDE') else root.find('.//s:rDE', ns)
    
    print("\nVerificación de estructura:")
    print(f"- rDE Id: {rde.get('Id')}")
    print(f"- Hijos de rDE: {[c.tag.split('}')[-1] for c in rde]}")
    print(f"- dVerFor primero: {rde[0].tag.split('}')[-1] == 'dVerFor'}")
    
    # Verificar secciones críticas
    de = rde.find('.//s:DE', ns)
    gDatGralOpe = de.find('.//s:gDatGralOpe', ns)
    gOpeCom = gDatGralOpe.find('.//s:gOpeCom', ns)
    gDtipDE = de.find('.//s:gDtipDE', ns)
    gCamFE = gDtipDE.find('.//s:gCamFE', ns)
    gCamCond = gDtipDE.find('.//s:gCamCond', ns)
    
    print(f"- gOpeCom presente: {'YES' if gOpeCom is not None else 'NO'}")
    print(f"- gCamFE presente: {'YES' if gCamFE is not None else 'NO'}")
    print(f"- gCamCond presente: {'YES' if gCamCond is not None else 'NO'}")
    print(f"- Signature NO agregado: {'OK' if rde.find('.//Signature') is None else 'ERROR'}")
