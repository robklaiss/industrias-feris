#!/usr/bin/env python3
"""
Generador de PDF con diseño personalizado basado en el modelo de factura.
Replica exactamente el diseño de la factura proporcionada.
"""

import os
import sys
from datetime import datetime

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.colors import black, white
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase import pdfmetrics
    from tools.generar_factura import generar_factura, datos_ejemplo
except ImportError as e:
    print("Error: Falta instalar reportlab")
    print("Ejecuta: pip install reportlab")
    sys.exit(1)


def formatear_guarani(valor):
    """Formatea número a moneda guaraní"""
    try:
        return f"{int(valor):,}".replace(",", ".")
    except:
        return str(valor)


def generar_pdf_personalizado(xml_file, pdf_file=None):
    """
    Genera un PDF con el diseño personalizado basado en el modelo.
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
        pdf_file = f"{base_name}_personalizado.pdf"
    
    c = canvas.Canvas(pdf_file, pagesize=A4)
    width, height = A4
    
    # Configurar fuentes
    try:
        pdfmetrics.registerFont(TTFont('Helvetica', '/System/Library/Fonts/Helvetica.ttc'))
        pdfmetrics.registerFont(TTFont('Helvetica-Bold', '/System/Library/Fonts/Helvetica-Bold.ttc'))
        font_normal = 'Helvetica'
        font_bold = 'Helvetica-Bold'
    except:
        font_normal = 'Helvetica'
        font_bold = 'Helvetica-Bold'
    
    # === CABECERA ===
    
    # Logo placeholder (opcional)
    # c.drawImage("logo.png", 2*cm, height-4*cm, width=3*cm, height=1.5*cm)
    
    # Datos del emisor (izquierda)
    y = height - 3*cm
    c.setFont(font_bold, 10)
    c.drawString(2*cm, y, emisor['nombre'].upper())
    y -= 0.4*cm
    c.setFont(font_normal, 9)
    c.drawString(2*cm, y, f"{emisor['direccion']} N° 0")
    y -= 0.4*cm
    c.drawString(2*cm, y, f"{emisor['ciudad']} - TELÉF. {emisor['telefono']}")
    
    # Actividades económicas
    for act in actividades[:2]:  # Máximo 2 líneas como en el original
        y -= 0.4*cm
        # Dividir si es muy largo
        if len(act) > 50:
            c.drawString(2*cm, y, act[:50])
            y -= 0.4*cm
            c.drawString(2*cm, y, act[50:])
        else:
            c.drawString(2*cm, y, act)
    
    # Timbrado (derecha)
    y = height - 3*cm
    c.setFont(font_bold, 9)
    c.drawString(14*cm, y, "TIMBRADO N° " + timbrado['numero'])
    y -= 0.4*cm
    c.setFont(font_normal, 8)
    fecha_inicio = datetime.strptime(timbrado['inicio'], '%Y-%m-%d').strftime('%d/%m/%Y')
    c.drawString(14*cm, y, f"Fecha Inicio Vigencia: {fecha_inicio}")
    
    # RUC y tipo de documento
    y -= 0.8*cm
    c.setFont(font_bold, 11)
    c.drawString(2*cm, y, f"RUC {emisor['ruc']} - {emisor['dv']}")
    c.drawString(12*cm, y, "FACTURA ELECTRÓNICA")
    y -= 0.5*cm
    c.setFont(font_normal, 10)
    c.drawString(2*cm, y, f"{timbrado['est']}-{timbrado['exp']}-{timbrado['doc']}")
    
    # Fecha de emisión
    y -= 0.7*cm
    c.setFont(font_normal, 9)
    fecha_emision = datetime.now().strftime('%d/%m/%Y')
    c.drawString(2*cm, y, f"Fecha de emisión: {fecha_emision}")
    
    # === DATOS DEL RECEPTOR ===
    y -= 1*cm
    c.setFont(font_normal, 9)
    c.drawString(2*cm, y, f"RUC/Documento de Identidad N°: {receptor['ruc']}-{receptor['dv']}")
    y -= 0.4*cm
    c.drawString(2*cm, y, f"Nombre o Razón Social: {receptor['nombre']}")
    y -= 0.4*cm
    c.drawString(2*cm, y, "Dirección:")
    y -= 0.4*cm
    c.drawString(2*cm, y, "Teléfono:")
    y -= 0.4*cm
    c.drawString(2*cm, y, f"Correo Electrónico: {receptor['email']}")
    
    # Tipo de transacción y condición (derecha)
    y = height - 7.5*cm
    c.drawString(10*cm, y, "Tipo de transacción: Venta de mercadería")
    y -= 0.4*cm
    c.drawString(10*cm, y, "Condición de venta: Contado")
    
    # === LÍNEA SEPARADORA ===
    y -= 0.8*cm
    c.line(2*cm, y, 19*cm, y)
    
    # === TABLA DE ITEMS ===
    y -= 0.5*cm
    c.setFont(font_bold, 8)
    c.drawString(2*cm, y, "COD.")
    c.drawString(3.5*cm, y, "CANTIDAD")
    c.drawString(6*cm, y, "DESCRIPCIÓN")
    c.drawString(12*cm, y, "PRECIO")
    c.drawString(14*cm, y, "UNITARIO")
    c.drawString(16*cm, y, "(INCLUIDO")
    c.drawString(16*cm, y-0.3*cm, "IMPUESTO)")
    c.drawString(17.5*cm, y, "DESCUENTO")
    c.drawString(19*cm, y, "VALOR DE VENTA")
    
    y -= 0.4*cm
    c.line(2*cm, y, 19*cm, y)
    
    # Headers de columnas de valores
    y -= 0.5*cm
    c.setFont(font_bold, 8)
    c.drawString(14*cm, y, "EXENTAS")
    c.drawString(15.5*cm, y, "5%")
    c.drawString(17*cm, y, "10%")
    
    y -= 0.7*cm
    c.line(2*cm, y, 19*cm, y)
    y -= 0.5*cm
    
    # Items
    c.setFont(font_normal, 9)
    for i, item in enumerate(items):
        # Código (vacío como en el original)
        c.drawString(2*cm, y, "")
        # Cantidad
        c.drawString(3.5*cm, y, item['cantidad'])
        # Descripción
        c.drawString(6*cm, y, item['descripcion'])
        # Precio unitario
        c.drawString(14*cm, y, formatear_guarani(item['precio']))
        # Descuento (siempre 0)
        c.drawString(17.5*cm, y, "0")
        
        # Valores según IVA
        if item['iva'] == '5':
            c.drawString(15.5*cm, y, formatear_guarani(item['total']))
            c.drawString(17*cm, y, "0")
        elif item['iva'] == '10':
            c.drawString(15.5*cm, y, "0")
            c.drawString(17*cm, y, formatear_guarani(item['total']))
        else:  # Exento
            c.drawString(14*cm, y, formatear_guarani(item['total']))
            c.drawString(15.5*cm, y, "0")
            c.drawString(17*cm, y, "0")
        
        y -= 0.6*cm
        
        if y < 10*cm:  # Salto de página si es necesario
            c.showPage()
            y = height - 3*cm
    
    # === TOTALES ===
    y -= 0.5*cm
    c.line(2*cm, y, 19*cm, y)
    y -= 0.7*cm
    
    # Subtotal
    c.setFont(font_bold, 9)
    c.drawString(14*cm, y, "SUBTOTAL:")
    c.drawString(19*cm, y, formatear_guarani(totales['subtotal']))
    y -= 0.5*cm
    
    # Total operación
    c.setFont(font_bold, 10)
    c.drawString(14*cm, y, "TOTAL DE LA OPERACIÓN:")
    c.drawString(19*cm, y, formatear_guarani(totales['total']))
    y -= 0.7*cm
    
    # Liquidación IVA
    c.setFont(font_bold, 9)
    c.drawString(14*cm, y, "LIQUIDACIÓN IVA: (5%)")
    c.drawString(15.5*cm, y, formatear_guarani(totales['iva5']))
    c.drawString(17*cm, y, formatear_guarani(totales['iva10']))
    c.drawString(18.5*cm, y, "TOTAL IVA:")
    c.drawString(19*cm, y, formatear_guarani(totales['total_iva']))
    
    # === PIE DE PÁGINA ===
    y -= 1.5*cm
    c.setFont(font_normal, 8)
    c.drawString(2*cm, y, "Consulte la validez de esta Factura Electrónica con el número de CDC impreso abajo en:")
    y -= 0.4*cm
    c.drawString(2*cm, y, "https://ekuatia.set.gov.py/consultas/")
    
    # CDC
    y -= 1*cm
    c.setFont(font_normal, 7)
    c.drawCentredString(width/2, y, de.get('Id', ''))
    
    # QR placeholder (opcional)
    # c.drawImage("qr.png", width/2 - 2*cm, y - 3*cm, width=4*cm, height=4*cm)
    
    c.save()
    print(f"PDF personalizado generado: {pdf_file}")
    return pdf_file


def main():
    """Función principal"""
    print("=" * 60)
    print("GENERADOR DE PDF PERSONALIZADO (ESTILO SIFEN)")
    print("=" * 60)
    
    # Generar XML de ejemplo
    print("\n1. Generando XML de ejemplo...")
    xml_file = "factura_ejemplo_personalizado.xml"
    generar_factura(datos_ejemplo(), xml_file)
    
    # Generar PDF personalizado
    print("\n2. Generando PDF con diseño personalizado...")
    pdf_file = generar_pdf_personalizado(xml_file)
    
    if pdf_file:
        print(f"\n✓ PDF generado: {pdf_file}")
        print("\nEl PDF tiene el mismo diseño que la factura de referencia")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
