#!/usr/bin/env python3
"""
Generar un XML DE con todos los requisitos para evitar error 0160:
- rDE con Id único
- dVerFor como primer hijo
- gCamFuFD después de Signature
- Signature con xmlns SIFEN
"""

from lxml import etree
import uuid
import sys
from datetime import datetime

# Namespace
SIFEN_NS = 'http://ekuatia.set.gov.py/sifen/xsd'

def generar_de_con_requisitos():
    # Generar IDs únicos
    de_id = f"018004554737010010000001{datetime.now().strftime('%Y%m%d%H%M%S')}1234567891"
    rde_id = f"rDE{de_id}"
    
    # Crear rDE con Id
    rde = etree.Element(f'{{{SIFEN_NS}}}rDE', Id=rde_id)
    
    # dVerFor primero (obligatorio)
    dver = etree.SubElement(rde, f'{{{SIFEN_NS}}}dVerFor')
    dver.text = '150'
    
    # DE con Id diferente
    de = etree.SubElement(rde, f'{{{SIFEN_NS}}}DE', Id=de_id)
    
    # Contenido mínimo del DE
    etree.SubElement(de, f'{{{SIFEN_NS}}}dDVId').text = '1'
    etree.SubElement(de, f'{{{SIFEN_NS}}}dFecFirma').text = datetime.now().isoformat()
    etree.SubElement(de, f'{{{SIFEN_NS}}}dSisFact').text = '1'
    
    # gOpeDE
    gOpeDE = etree.SubElement(de, f'{{{SIFEN_NS}}}gOpeDE')
    etree.SubElement(gOpeDE, f'{{{SIFEN_NS}}}iTipEmi').text = '1'
    etree.SubElement(gOpeDE, f'{{{SIFEN_NS}}}dDesTipEmi').text = 'Normal'
    etree.SubElement(gOpeDE, f'{{{SIFEN_NS}}}dCodSeg').text = '123456789'
    
    # gTimb
    gTimb = etree.SubElement(de, f'{{{SIFEN_NS}}}gTimb')
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}iTiDE').text = '01'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dDesTiDE').text = 'Factura electrónica'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dNumTim').text = '12345678'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dEst').text = '001'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dPunExp').text = '001'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dNumDoc').text = '0000001'
    etree.SubElement(gTimb, f'{{{SIFEN_NS}}}dFeIniT').text = datetime.now().strftime('%Y-%m-%d')
    
    # gDatGralOpe
    gDatGralOpe = etree.SubElement(de, f'{{{SIFEN_NS}}}gDatGralOpe')
    etree.SubElement(gDatGralOpe, f'{{{SIFEN_NS}}}dFeEmiDE').text = datetime.now().isoformat()
    
    gEmis = etree.SubElement(gDatGralOpe, f'{{{SIFEN_NS}}}gEmis')
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dRucEm').text = '4554737'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dDVEmi').text = '8'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}iTipCont').text = '1'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dNomEmi').text = 'EMPRESA DE PRUEBA'
    etree.SubElement(gEmis, f'{{{SIFEN_NS}}}dDirEmi').text = 'Asunción, Paraguay'
    
    gDatRec = etree.SubElement(gDatGralOpe, f'{{{SIFEN_NS}}}gDatRec')
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dRucRec').text = '4567890'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dDVRec').text = '1'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}iTipCont').text = '1'
    etree.SubElement(gDatRec, f'{{{SIFEN_NS}}}dNomRec').text = 'CLIENTE DE PRUEBA'
    
    # gDtipDE
    gDtipDE = etree.SubElement(de, f'{{{SIFEN_NS}}}gDtipDE')
    
    gCamDE = etree.SubElement(gDtipDE, f'{{{SIFEN_NS}}}gCamDE')
    etree.SubElement(gCamDE, f'{{{SIFEN_NS}}}iIndPres').text = '1'
    etree.SubElement(gCamDE, f'{{{SIFEN_NS}}}dDesIndPres').text = 'Operación presencial'
    etree.SubElement(gCamDE, f'{{{SIFEN_NS}}}iCondOpe').text = '1'
    etree.SubElement(gCamDE, f'{{{SIFEN_NS}}}dDesCondOpe').text = 'Contado'
    etree.SubElement(gCamDE, f'{{{SIFEN_NS}}}iTiOpe').text = '1'
    etree.SubElement(gCamDE, f'{{{SIFEN_NS}}}dDesTiOpe').text = 'Exportación'
    
    gCamItem = etree.SubElement(gDtipDE, f'{{{SIFEN_NS}}}gCamItem')
    etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}iItem').text = '1'
    etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}dCodItem').text = '001'
    etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}dDesItem').text = 'ITEM DE PRUEBA CON REQUISITOS'
    etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}dCantPro').text = '1'
    
    gUnidadMed = etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}gUnidadMed')
    etree.SubElement(gUnidadMed, f'{{{SIFEN_NS}}}dCodUnMed').text = 'UN'
    etree.SubElement(gUnidadMed, f'{{{SIFEN_NS}}}dDesUnMed').text = 'Unidad'
    
    gValItem = etree.SubElement(gCamItem, f'{{{SIFEN_NS}}}gValItem')
    etree.SubElement(gValItem, f'{{{SIFEN_NS}}}dPItem').text = '100000'
    etree.SubElement(gValItem, f'{{{SIFEN_NS}}}dTotItem').text = '100000'
    
    gTotSub = etree.SubElement(de, f'{{{SIFEN_NS}}}gTotSub')
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dTotGralOp').text = '100000'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dTotGralOpe').text = '100000'
    etree.SubElement(gTotSub, f'{{{SIFEN_NS}}}dTotIVA').text = '10000'
    
    # Signature con xmlns SIFEN (requerido según memoria)
    sig = etree.SubElement(rde, 'Signature', xmlns='http://ekuatia.set.gov.py/sifen/xsd')
    
    # gCamFuFD después de Signature (requerido)
    gCamFuFD = etree.SubElement(rde, f'{{{SIFEN_NS}}}gCamFuFD')
    etree.SubElement(gCamFuFD, f'{{{SIFEN_NS}}}dDesTrib').text = '10'
    
    # Serializar
    xml_bytes = etree.tostring(rde, xml_declaration=True, encoding='utf-8')
    
    return xml_bytes

if __name__ == '__main__':
    xml_bytes = generar_de_con_requisitos()
    
    # Guardar
    output_file = sys.argv[1] if len(sys.argv) > 1 else '../test_rde_con_requisitos.xml'
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
    print(f"- gCamFuFD presente: {'gCamFuFD' in [c.tag.split('}')[-1] for c in rde]}")
    
    sig = rde.find('.//Signature')
    if sig is not None:
        print(f"- Signature xmlns: {sig.get('xmlns')}")
