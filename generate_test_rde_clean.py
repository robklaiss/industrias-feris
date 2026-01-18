#!/usr/bin/env python3
"""
Generar un XML rDE limpio para probar SIFEN
- Sin prefijos en Signature
- gCamFuFD fuera de DE
- Estructura correcta según KB
"""

from lxml import etree
import uuid
from datetime import datetime

# Namespaces
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"

# Crear el elemento rDE con su namespace
rde = etree.Element(f"{{{SIFEN_NS}}}rDE", nsmap={None: SIFEN_NS, 'ds': DS_NS})
rde.set("Id", f"rDE_{uuid.uuid4().hex[:20]}")

# dVerFor como primer hijo
dVerFor = etree.SubElement(rde, f"{{{SIFEN_NS}}}dVerFor")
dVerFor.text = "150"

# DE
de_id = f"018004554737010010000001{datetime.now().strftime('%Y%m%d')}1234567891"
de = etree.SubElement(rde, f"{{{SIFEN_NS}}}DE")
de.set("Id", de_id)

# Datos básicos del DE
etree.SubElement(de, f"{{{SIFEN_NS}}}dDVId").text = "1"
etree.SubElement(de, f"{{{SIFEN_NS}}}dFecFirma").text = datetime.now().strftime('%Y-%m-%dT14:00:00')
etree.SubElement(de, f"{{{SIFEN_NS}}}dSisFact").text = "1"

# gOpeDE
gOpeDE = etree.SubElement(de, f"{{{SIFEN_NS}}}gOpeDE")
etree.SubElement(gOpeDE, f"{{{SIFEN_NS}}}iTipEmi").text = "1"
etree.SubElement(gOpeDE, f"{{{SIFEN_NS}}}dDesTipEmi").text = "Normal"
etree.SubElement(gOpeDE, f"{{{SIFEN_NS}}}dCodSeg").text = "123456789"

# gTimb
gTimb = etree.SubElement(de, f"{{{SIFEN_NS}}}gTimb")
etree.SubElement(gTimb, f"{{{SIFEN_NS}}}iTiDE").text = "01"
etree.SubElement(gTimb, f"{{{SIFEN_NS}}}dDesTiDE").text = "Factura electrónica"
etree.SubElement(gTimb, f"{{{SIFEN_NS}}}dNumTim").text = "12345678"
etree.SubElement(gTimb, f"{{{SIFEN_NS}}}dEst").text = "001"
etree.SubElement(gTimb, f"{{{SIFEN_NS}}}dPunExp").text = "001"
etree.SubElement(gTimb, f"{{{SIFEN_NS}}}dNumDoc").text = "0000001"
etree.SubElement(gTimb, f"{{{SIFEN_NS}}}dFeIniT").text = datetime.now().strftime('%Y-%m-%d')

# gDatGralOpe
gDatGralOpe = etree.SubElement(de, f"{{{SIFEN_NS}}}gDatGralOpe")
etree.SubElement(gDatGralOpe, f"{{{SIFEN_NS}}}dFeEmiDE").text = datetime.now().strftime('%Y-%m-%dT14:00:00')

# gEmis
gEmis = etree.SubElement(gDatGralOpe, f"{{{SIFEN_NS}}}gEmis")
etree.SubElement(gEmis, f"{{{SIFEN_NS}}}dRucEm").text = "4554737"
etree.SubElement(gEmis, f"{{{SIFEN_NS}}}dDVEmi").text = "8"
etree.SubElement(gEmis, f"{{{SIFEN_NS}}}iTipCont").text = "1"
etree.SubElement(gEmis, f"{{{SIFEN_NS}}}dNomEmi").text = "EMPRESA DE PRUEBA"
etree.SubElement(gEmis, f"{{{SIFEN_NS}}}dDirEmi").text = "Asunción, Paraguay"

# gDatRec
gDatRec = etree.SubElement(gDatGralOpe, f"{{{SIFEN_NS}}}gDatRec")
etree.SubElement(gDatRec, f"{{{SIFEN_NS}}}dRucRec").text = "4567890"
etree.SubElement(gDatRec, f"{{{SIFEN_NS}}}dDVRec").text = "1"
etree.SubElement(gDatRec, f"{{{SIFEN_NS}}}iTipCont").text = "1"
etree.SubElement(gDatRec, f"{{{SIFEN_NS}}}dNomRec").text = "CLIENTE DE PRUEBA"

# gDtipDE
gDtipDE = etree.SubElement(de, f"{{{SIFEN_NS}}}gDtipDE")

# gCamDE
gCamDE = etree.SubElement(gDtipDE, f"{{{SIFEN_NS}}}gCamDE")
etree.SubElement(gCamDE, f"{{{SIFEN_NS}}}iIndPres").text = "1"
etree.SubElement(gCamDE, f"{{{SIFEN_NS}}}dDesIndPres").text = "Operación presencial"
etree.SubElement(gCamDE, f"{{{SIFEN_NS}}}iCondOpe").text = "1"
etree.SubElement(gCamDE, f"{{{SIFEN_NS}}}dDesCondOpe").text = "Contado"
etree.SubElement(gCamDE, f"{{{SIFEN_NS}}}iTiOpe").text = "1"
etree.SubElement(gCamDE, f"{{{SIFEN_NS}}}dDesTiOpe").text = "Exportación"

# gCamItem
gCamItem = etree.SubElement(gDtipDE, f"{{{SIFEN_NS}}}gCamItem")
etree.SubElement(gCamItem, f"{{{SIFEN_NS}}}iItem").text = "1"
etree.SubElement(gCamItem, f"{{{SIFEN_NS}}}dCodItem").text = "001"
etree.SubElement(gCamItem, f"{{{SIFEN_NS}}}dDesItem").text = "ITEM DE PRUEBA"
etree.SubElement(gCamItem, f"{{{SIFEN_NS}}}dCantPro").text = "1"

# gUnidadMed
gUnidadMed = etree.SubElement(gCamItem, f"{{{SIFEN_NS}}}gUnidadMed")
etree.SubElement(gUnidadMed, f"{{{SIFEN_NS}}}dCodUnMed").text = "UN"
etree.SubElement(gUnidadMed, f"{{{SIFEN_NS}}}dDesUnMed").text = "Unidad"

# gValItem
gValItem = etree.SubElement(gCamItem, f"{{{SIFEN_NS}}}gValItem")
etree.SubElement(gValItem, f"{{{SIFEN_NS}}}dPItem").text = "100000"
etree.SubElement(gValItem, f"{{{SIFEN_NS}}}dTotItem").text = "100000"

# gTotSub
gTotSub = etree.SubElement(de, f"{{{SIFEN_NS}}}gTotSub")
etree.SubElement(gTotSub, f"{{{SIFEN_NS}}}dTotGralOp").text = "100000"
etree.SubElement(gTotSub, f"{{{SIFEN_NS}}}dTotGralOpe").text = "100000"
etree.SubElement(gTotSub, f"{{{SIFEN_NS}}}dTotIVA").text = "10000"

# gEmis (dentro de DE)
gEmis2 = etree.SubElement(de, f"{{{SIFEN_NS}}}gEmis")
etree.SubElement(gEmis2, f"{{{SIFEN_NS}}}dRucEm").text = "4554737"
etree.SubElement(gEmis2, f"{{{SIFEN_NS}}}dDVEmi").text = "8"

# NO agregar Signature (que el script lo firme)
# signature = etree.SubElement(rde, f"{{{DS_NS}}}Signature")
# signature.set("xmlns", DS_NS)

# gCamFuFD FUERA de DE (como hijo de rDE, después de Signature)
# Lo agregamos como placeholder para que el script lo mantenga
gCamFuFD = etree.SubElement(rde, f"{{{SIFEN_NS}}}gCamFuFD")
etree.SubElement(gCamFuFD, f"{{{SIFEN_NS}}}dDesTrib").text = "10"

# Serializar sin pretty print para evitar whitespace
xml_bytes = etree.tostring(rde, encoding='UTF-8', xml_declaration=False, pretty_print=False)

# Agregar declaración XML manualmente
xml_str = f'<?xml version="1.0" encoding="UTF-8"?>{xml_bytes.decode("utf-8")}'

# Guardar
with open("test_rde_clean.xml", "w", encoding="utf-8") as f:
    f.write(xml_str)

print("XML limpio generado: test_rde_clean.xml")
print("✅ Sin prefijos en Signature")
print("✅ gCamFuFD agregado fuera de DE (orden: DE, gCamFuFD, Signature)")
