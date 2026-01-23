#!/usr/bin/env python3
"""
Generador de PDF con réplica exacta del diseño SIFEN.
Basado en análisis de posiciones exactas del PDF original.
"""

import os
import sys
from datetime import datetime

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import black
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase import pdfmetrics
    from tools.generar_factura import generar_factura, datos_ejemplo
    import qrcode
    from PIL import Image
    import io
except ImportError as e:
    print("Error: Falta instalar dependencias")
    print("Ejecuta: pip install reportlab qrcode[pil] PyMuPDF")
    sys.exit(1)


def generar_qr_code(cdc, url="https://ekuatia.set.gov.py/consultas/"):
    """Genera el código QR para el CDC"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=4,
        border=0,
    )
    qr.add_data(f"{url}?cdc={cdc}")
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    return img


def generar_pdf_exacto(xml_file, pdf_file=None):
    """
    Genera un PDF replicando exactamente el diseño del original.
    """
    # Parsear XML
    import xml.etree.ElementTree as ET
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    # Namespace
    ns = {"s": "http://ekuatia.set.gov.py/sifen/xsd"}
    
    # Extraer datos
    de = root.find("s:DE", ns)
    
    # Emisor
    gEmis = de.find(".//s:gEmis", ns)
    emisor = {
        "ruc": gEmis.find("s:dRucEm", ns).text if gEmis is not None and gEmis.find("s:dRucEm", ns) is not None else "",
        "dv": gEmis.find("s:dDVEmi", ns).text if gEmis is not None and gEmis.find("s:dDVEmi", ns) is not None else "",
        "nombre": gEmis.find("s:dNomEmi", ns).text if gEmis is not None and gEmis.find("s:dNomEmi", ns) is not None else "",
        "direccion": gEmis.find("s:dDirEmi", ns).text if gEmis is not None and gEmis.find("s:dDirEmi", ns) is not None else "",
        "ciudad": gEmis.find("s:dDesCiuEmi", ns).text if gEmis is not None and gEmis.find("s:dDesCiuEmi", ns) is not None else "",
        "telefono": gEmis.find("s:dTelEmi", ns).text if gEmis is not None and gEmis.find("s:dTelEmi", ns) is not None else "",
        "email": gEmis.find("s:dEmailE", ns).text if gEmis is not None and gEmis.find("s:dEmailE", ns) is not None else ""
    }
    
    # Actividades económicas
    actividades = []
    if gEmis is not None:
        for act in gEmis.findall("s:gActEco", ns):
            desc = act.find("s:dDesActEco", ns)
            if desc is not None and desc.text:
                actividades.append(desc.text)
    
    # Receptor
    gDatRec = de.find(".//s:gDatRec", ns)
    receptor = {
        "ruc": gDatRec.find("s:dRucRec", ns).text if gDatRec is not None and gDatRec.find("s:dRucRec", ns) is not None else "",
        "dv": gDatRec.find("s:dDVRec", ns).text if gDatRec is not None and gDatRec.find("s:dDVRec", ns) is not None else "",
        "nombre": gDatRec.find("s:dNomRec", ns).text if gDatRec is not None and gDatRec.find("s:dNomRec", ns) is not None else "",
        "direccion": gDatRec.find("s:dDirRec", ns).text if gDatRec is not None and gDatRec.find("s:dDirRec", ns) is not None else "",
        "telefono": gDatRec.find("s:dTelRec", ns).text if gDatRec is not None and gDatRec.find("s:dTelRec", ns) is not None else "",
        "email": gDatRec.find("s:dEmailRec", ns).text if gDatRec is not None and gDatRec.find("s:dEmailRec", ns) is not None else ""
    }
    
    # Timbrado
    gTimb = de.find("s:gTimb", ns)
    timbrado = {
        "numero": gTimb.find("s:dNumTim", ns).text if gTimb is not None and gTimb.find("s:dNumTim", ns) is not None else "",
        "est": gTimb.find("s:dEst", ns).text if gTimb is not None and gTimb.find("s:dEst", ns) is not None else "",
        "exp": gTimb.find("s:dPunExp", ns).text if gTimb is not None and gTimb.find("s:dPunExp", ns) is not None else "",
        "doc": gTimb.find("s:dNumDoc", ns).text if gTimb is not None and gTimb.find("s:dNumDoc", ns) is not None else "",
        "inicio": gTimb.find("s:dFeIniT", ns).text if gTimb is not None and gTimb.find("s:dFeIniT", ns) is not None else ""
    }
    
    # Items
    items = []
    gCamItem = de.findall(".//s:gCamItem", ns)
    for item in gCamItem:
        items.append({
            "descripcion": item.find("s:dDesProSer", ns).text if item.find("s:dDesProSer", ns) is not None else "",
            "cantidad": item.find("s:dCantProSer", ns).text if item.find("s:dCantProSer", ns) is not None else "",
            "precio": item.find(".//s:dPUniProSer", ns).text if item.find(".//s:dPUniProSer", ns) is not None else "",
            "total": item.find(".//s:dTotOpeItem", ns).text if item.find(".//s:dTotOpeItem", ns) is not None else "",
            "iva": item.find(".//s:dTasaIVA", ns).text if item.find(".//s:dTasaIVA", ns) is not None else "0"
        })
    
    # Totales
    gTotSub = de.find("s:gTotSub", ns)
    totales = {
        "subtotal": gTotSub.find("s:dTotOpe", ns).text if gTotSub is not None and gTotSub.find("s:dTotOpe", ns) is not None else "0",
        "iva5": gTotSub.find("s:dIVA5", ns).text if gTotSub is not None and gTotSub.find("s:dIVA5", ns) is not None else "0",
        "iva10": gTotSub.find("s:dIVA10", ns).text if gTotSub is not None and gTotSub.find("s:dIVA10", ns) is not None else "0",
        "total_iva": gTotSub.find("s:dTotIVA", ns).text if gTotSub is not None and gTotSub.find("s:dTotIVA", ns) is not None else "0",
        "total": gTotSub.find("s:dTotGralOpe", ns).text if gTotSub is not None and gTotSub.find("s:dTotGralOpe", ns) is not None else "0"
    }
    
    # Crear PDF
    if pdf_file is None:
        base_name = os.path.splitext(os.path.basename(xml_file))[0]
        pdf_file = f"{base_name}_exacto.pdf"
    
    c = canvas.Canvas(pdf_file, pagesize=A4)
    width, height = A4
    
    # Configurar fuentes (usando Helvetica que es estándar)
    font_normal = 'Helvetica'
    font_bold = 'Helvetica-Bold'
    
    # === CABECERA (posiciones exactas del original) ===
    
    # Datos del emisor (izquierda)
    # "de ANTONIO VIDAL OVIEDO BENITEZ" - x=72.7, y=71.7
    c.setFont(font_normal, 10)
    c.drawString(72.7, height - 71.7, f"de {emisor['nombre'].upper()}")
    
    # "SAN PEDRO CASI EMILIO JOHANSEN N° 0" - x=61.4, y=86.7
    c.drawString(61.4, height - 86.7, f"{emisor['direccion']} N° 0")
    
    # "VILLA ELISA - TELÉF. (0961)822555" - x=76.0, y=101.7
    c.drawString(76.0, height - 101.7, f"{emisor['ciudad']} - TELÉF. {emisor['telefono']}")
    
    # Actividades económicas - x=58.5, y=119.2
    y_act = height - 119.2
    c.setFont(font_normal, 8)
    for i, act in enumerate(actividades[:2]):
        if i == 0:
            c.drawString(58.5, y_act, act)
        else:
            # Dividir texto largo si es necesario
            if len(act) > 40:
                c.drawString(27.1, y_act + 11.8, act[:40])
                c.drawString(128.9, y_act + 23.6, act[40:])
            else:
                c.drawString(58.5, y_act + 11.8, act)
    
    # Timbrado (derecha)
    # "TIMBRADO N° 18502837" - x=383.1, y=54.8
    c.setFont(font_normal, 11)
    c.drawString(383.1, height - 54.8, f"TIMBRADO N° {timbrado['numero']}")
    
    # "Fecha Inicio Vigencia: 06/12/2025" - x=353.8, y=67.6
    fecha_inicio = datetime.strptime(timbrado['inicio'], '%Y-%m-%d').strftime('%d/%m/%Y')
    c.drawString(353.8, height - 67.6, f"Fecha Inicio Vigencia: {fecha_inicio}")
    
    # "RUC 4009031 - 0" - x=404.8, y=80.5
    c.drawString(404.8, height - 80.5, f"RUC {emisor['ruc']} - {emisor['dv']}")
    
    # "FACTURA ELECTRÓNICA" - x=382.8, y=93.3
    c.drawString(382.8, height - 93.3, "FACTURA ELECTRÓNICA")
    
    # "001-001-0000119" - x=403.7, y=106.1
    c.drawString(403.7, height - 106.1, f"{timbrado['est']}-{timbrado['exp']}-{timbrado['doc']}")
    
    # === DATOS DEL RECEPTOR ===
    c.setFont(font_normal, 8)
    
    # "Fecha de emisión:" - x=22.0, y=160.2
    c.drawString(22.0, height - 160.2, "Fecha de emisión:")
    # "19/01/2026" - x=103.8, y=160.2
    fecha_emision = datetime.now().strftime('%d/%m/%Y')
    c.drawString(103.8, height - 160.2, fecha_emision)
    
    # "RUC/Documento de Identidad N°:" - x=22.0, y=176.2
    c.drawString(22.0, height - 176.2, "RUC/Documento de Identidad N°:")
    # "7524653-8" - x=179.0, y=176.2
    c.drawString(179.0, height - 176.2, f"{receptor['ruc']}-{receptor['dv']}")
    
    # "Nombre o Razón Social:" - x=22.0, y=192.2
    c.drawString(22.0, height - 192.2, "Nombre o Razón Social:")
    # "ROBIN KLAISS" - x=128.9, y=192.2
    c.drawString(128.9, height - 192.2, receptor['nombre'])
    
    # "Dirección:" - x=22.0, y=208.2
    c.drawString(22.0, height - 208.2, "Dirección:")
    
    # "Teléfono:" - x=22.0, y=224.2
    c.drawString(22.0, height - 224.2, "Teléfono:")
    
    # "Correo Electrónico:" - x=22.0, y=240.2
    c.drawString(22.0, height - 240.2, "Correo Electrónico:")
    # "robin@vinculo.com.py" - x=119.0, y=240.2
    c.drawString(119.0, height - 240.2, receptor['email'])
    
    # Tipo y condición (derecha)
    # "Tipo de transacción:" - x=326.0, y=160.2
    c.drawString(326.0, height - 160.2, "Tipo de transacción:")
    # "Venta de mercadería" - x=426.0, y=160.2
    c.drawString(426.0, height - 160.2, "Venta de mercadería")
    
    # "Condición de venta:" - x=326.0, y=176.2
    c.drawString(326.0, height - 176.2, "Condición de venta:")
    # "Contado" - x=426.0, y=176.2
    c.drawString(426.0, height - 176.2, "Contado")
    
    # === LÍNEA SEPARADORA ===
    c.line(22.0, height - 260.0, width - 22.0, height - 260.0)
    
    # === TABLA DE ITEMS ===
    y_items = height - 275.0
    
    # Headers
    c.setFont(font_normal, 8)
    c.drawString(22.0, y_items, "COD.")
    c.drawString(65.0, y_items, "CANTIDAD")
    c.drawString(130.0, y_items, "DESCRIPCIÓN")
    c.drawString(350.0, y_items, "PRECIO")
    c.drawString(400.0, y_items, "UNITARIO")
    c.drawString(450.0, y_items, "(INCLUIDO")
    c.drawString(450.0, y_items - 8, "IMPUESTO)")
    c.drawString(500.0, y_items, "DESCUENTO")
    c.drawString(550.0, y_items, "VALOR DE VENTA")
    
    # Headers de valores
    y_items -= 15.0
    c.drawString(480.0, y_items, "EXENTAS")
    c.drawString(510.0, y_items, "5%")
    c.drawString(540.0, y_items, "10%")
    
    y_items -= 10.0
    c.line(22.0, y_items, width - 22.0, y_items)
    y_items -= 10.0
    
    # Items
    for item in items:
        c.drawString(65.0, y_items, item['cantidad'])
        c.drawString(130.0, y_items, item['descripcion'])
        c.drawString(400.0, y_items, formatear_guarani(item['precio']))
        c.drawString(500.0, y_items, "0")
        
        # Valores según IVA
        if item['iva'] == '5':
            c.drawString(510.0, y_items, formatear_guarani(item['total']))
            c.drawString(540.0, y_items, "0")
        elif item['iva'] == '10':
            c.drawString(510.0, y_items, "0")
            c.drawString(540.0, y_items, formatear_guarani(item['total']))
        else:
            c.drawString(480.0, y_items, formatear_guarani(item['total']))
            c.drawString(510.0, y_items, "0")
            c.drawString(540.0, y_items, "0")
        
        y_items -= 12.0
        if y_items < 150:  # Salto de página si es necesario
            c.showPage()
            y_items = height - 100.0
    
    # === TOTALES ===
    y_items -= 10.0
    c.line(22.0, y_items, width - 22.0, y_items)
    y_items -= 15.0
    
    c.setFont(font_normal, 9)
    c.drawString(480.0, y_items, "SUBTOTAL:")
    c.drawString(550.0, y_items, formatear_guarani(totales['subtotal']))
    
    y_items -= 12.0
    c.setFont(font_normal, 10)
    c.drawString(480.0, y_items, "TOTAL DE LA OPERACIÓN:")
    c.drawString(550.0, y_items, formatear_guarani(totales['total']))
    
    y_items -= 15.0
    c.setFont(font_normal, 9)
    c.drawString(450.0, y_items, "LIQUIDACIÓN IVA: (5%)")
    c.drawString(510.0, y_items, formatear_guarani(totales['iva5']))
    c.drawString(540.0, y_items, formatear_guarani(totales['iva10']))
    c.drawString(545.0, y_items + 15.0, "TOTAL IVA:")
    c.drawString(550.0, y_items + 15.0, formatear_guarani(totales['total_iva']))
    
    # === PIE DE PÁGINA ===
    y_pie = 80.0
    c.setFont(font_normal, 8)
    c.drawString(22.0, y_pie, "Consulte la validez de esta Factura Electrónica con el número de CDC impreso abajo en:")
    c.drawString(22.0, y_pie - 10, "https://ekuatia.set.gov.py/consultas/")
    
    # CDC
    c.setFont(font_normal, 7)
    c.drawCentredString(width/2, y_pie - 30, de.get('Id', ''))
    
    # Generar y agregar QR
    qr_img = generar_qr_code(de.get('Id', ''))
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)
    
    # Guardar QR temporalmente
    qr_temp_file = "temp_qr.png"
    with open(qr_temp_file, "wb") as f:
        f.write(qr_buffer.getvalue())
    
    # Dibujar QR
    qr_size = 60
    c.drawImage(qr_temp_file, width/2 - qr_size/2, y_pie - 80, width=qr_size, height=qr_size)
    
    # Limpiar archivo temporal
    os.remove(qr_temp_file)
    
    c.save()
    print(f"PDF exacto generado: {pdf_file}")
    return pdf_file


def formatear_guarani(valor):
    """Formatea número a moneda guaraní"""
    try:
        return f"{int(valor):,}".replace(",", ".")
    except:
        return str(valor)


def main():
    """Función principal"""
    print("=" * 60)
    print("GENERADOR DE PDF EXACTO (RÉPLICA SIFEN)")
    print("=" * 60)
    
    # Generar XML de ejemplo
    print("\n1. Generando XML de ejemplo...")
    xml_file = "factura_ejemplo_exacto.xml"
    generar_factura(datos_ejemplo(), xml_file)
    
    # Generar PDF exacto
    print("\n2. Generando PDF con réplica exacta...")
    pdf_file = generar_pdf_exacto(xml_file)
    
    if pdf_file:
        print(f"\n✓ PDF generado: {pdf_file}")
        print("\nEl PDF replica exactamente el diseño original")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
