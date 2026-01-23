#!/usr/bin/env python3
"""
Generador de PDF a partir de XML de factura SIFEN.
Este script convierte el XML de la factura en un PDF legible.
"""

import os
import sys
from datetime import datetime

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
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
        return f"Gs. {int(valor):,}".replace(",", ".")
    except:
        return f"Gs. {valor}"


def generar_pdf_factura(xml_file, pdf_file=None):
    """
    Genera un PDF legible a partir del XML de la factura.
    
    Args:
        xml_file (str): Ruta del archivo XML
        pdf_file (str): Ruta del archivo PDF de salida (opcional)
    """
    # Parsear XML para extraer datos
    import xml.etree.ElementTree as ET
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    # Namespace
    ns = {"s": "http://ekuatia.set.gov.py/sifen/xsd"}
    
    # Extraer datos principales
    de = root.find("s:DE", ns)
    if de is None:
        print("Error: No se encontró el elemento DE")
        return None
    
    # Datos del emisor
    gEmis = de.find(".//s:gEmis", ns)
    emisor = {
        "ruc": gEmis.find("s:dRucEm", ns).text if gEmis is not None else "",
        "dv": gEmis.find("s:dDVEmi", ns).text if gEmis is not None else "",
        "nombre": gEmis.find("s:dNomEmi", ns).text if gEmis is not None else "",
        "direccion": gEmis.find("s:dDirEmi", ns).text if gEmis is not None else "",
        "ciudad": gEmis.find("s:dDesCiuEmi", ns).text if gEmis is not None else "",
        "telefono": gEmis.find("s:dTelEmi", ns).text if gEmis is not None else "",
        "email": gEmis.find("s:dEmailE", ns).text if gEmis is not None else ""
    }
    
    # Datos del receptor
    gDatRec = de.find(".//s:gDatRec", ns)
    receptor = {
        "ruc": gDatRec.find("s:dRucRec", ns).text if gDatRec is not None else "",
        "dv": gDatRec.find("s:dDVRec", ns).text if gDatRec is not None else "",
        "nombre": gDatRec.find("s:dNomRec", ns).text if gDatRec is not None else "",
        "email": gDatRec.find("s:dEmailRec", ns).text if gDatRec is not None else ""
    }
    
    # Timbrado
    gTimb = de.find("s:gTimb", ns)
    timbrado = {
        "numero": gTimb.find("s:dNumTim", ns).text if gTimb is not None else "",
        "est": gTimb.find("s:dEst", ns).text if gTimb is not None else "",
        "exp": gTimb.find("s:dPunExp", ns).text if gTimb is not None else "",
        "doc": gTimb.find("s:dNumDoc", ns).text if gTimb is not None else ""
    }
    
    # Items
    items = []
    gCamItem = de.findall(".//s:gCamItem", ns)
    for item in gCamItem:
        items.append({
            "descripcion": item.find("s:dDesProSer", ns).text,
            "cantidad": item.find("s:dCantProSer", ns).text,
            "precio": item.find(".//s:dPUniProSer", ns).text,
            "total": item.find(".//s:dTotOpeItem", ns).text,
            "iva": item.find(".//s:dLiqIVAItem", ns).text
        })
    
    # Totales
    gTotSub = de.find("s:gTotSub", ns)
    totales = {
        "subtotal": gTotSub.find("s:dTotOpe", ns).text if gTotSub is not None else "0",
        "iva5": gTotSub.find("s:dIVA5", ns).text if gTotSub is not None else "0",
        "iva10": gTotSub.find("s:dIVA10", ns).text if gTotSub is not None else "0",
        "total_iva": gTotSub.find("s:dTotIVA", ns).text if gTotSub is not None else "0",
        "total": gTotSub.find("s:dTotGralOpe", ns).text if gTotSub is not None else "0"
    }
    
    # Crear PDF
    if pdf_file is None:
        base_name = os.path.splitext(os.path.basename(xml_file))[0]
        pdf_file = f"{base_name}.pdf"
    
    c = canvas.Canvas(pdf_file, pagesize=A4)
    width, height = A4
    
    # Configurar fuentes
    try:
        # Intentar usar fuentes del sistema
        pdfmetrics.registerFont(TTFont('Arial', '/System/Library/Fonts/Arial.ttf'))
        font_normal = 'Arial'
        font_bold = 'Arial'
    except:
        # Usar fuentes por defecto
        font_normal = 'Helvetica'
        font_bold = 'Helvetica-Bold'
    
    # Título
    c.setFont(font_bold, 16)
    c.drawCentredString(width/2, height - 3*cm, "FACTURA ELECTRÓNICA")
    
    # Datos del emisor
    y = height - 5*cm
    c.setFont(font_bold, 12)
    c.drawString(2*cm, y, "EMISOR:")
    y -= 0.7*cm
    c.setFont(font_normal, 10)
    c.drawString(2.5*cm, y, f"RUC: {emisor['ruc']}-{emisor['dv']}")
    y -= 0.5*cm
    c.drawString(2.5*cm, y, emisor['nombre'])
    y -= 0.5*cm
    c.drawString(2.5*cm, y, emisor['direccion'])
    y -= 0.5*cm
    c.drawString(2.5*cm, y, f"{emisor['ciudad']} - Tel: {emisor['telefono']}")
    y -= 0.5*cm
    c.drawString(2.5*cm, y, emisor['email'])
    
    # Datos del receptor
    y -= 1.5*cm
    c.setFont(font_bold, 12)
    c.drawString(2*cm, y, "RECEPTOR:")
    y -= 0.7*cm
    c.setFont(font_normal, 10)
    c.drawString(2.5*cm, y, f"RUC: {receptor['ruc']}-{receptor['dv']}")
    y -= 0.5*cm
    c.drawString(2.5*cm, y, receptor['nombre'])
    y -= 0.5*cm
    c.drawString(2.5*cm, y, receptor['email'])
    
    # Timbrado
    y -= 1.5*cm
    c.setFont(font_bold, 12)
    c.drawString(2*cm, y, "TIMBRADO:")
    y -= 0.7*cm
    c.setFont(font_normal, 10)
    c.drawString(2.5*cm, y, f"N°: {timbrado['numero']}")
    y -= 0.5*cm
    c.drawString(2.5*cm, y, f"Establecimiento: {timbrado['est']}")
    y -= 0.5*cm
    c.drawString(2.5*cm, y, f"Punto de Expedición: {timbrado['exp']}")
    y -= 0.5*cm
    c.drawString(2.5*cm, y, f"N° Documento: {timbrado['doc']}")
    
    # Fecha y CDC
    y -= 1.5*cm
    c.setFont(font_bold, 12)
    c.drawString(2*cm, y, "FECHA Y CDC:")
    y -= 0.7*cm
    c.setFont(font_normal, 10)
    c.drawString(2.5*cm, y, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
    y -= 0.5*cm
    c.drawString(2.5*cm, y, f"CDC: {de.get('Id')}")
    
    # Tabla de items
    y -= 2*cm
    c.setFont(font_bold, 10)
    c.drawString(2*cm, y, "DESCRIPCIÓN")
    c.drawString(10*cm, y, "CANT")
    c.drawString(12*cm, y, "PRECIO")
    c.drawString(15*cm, y, "IVA")
    c.drawString(17*cm, y, "TOTAL")
    
    y -= 0.7*cm
    c.line(2*cm, y, 19*cm, y)
    y -= 0.5*cm
    
    c.setFont(font_normal, 9)
    for item in items:
        # Descripción (multilinea si es necesario)
        desc = item['descripcion'][:40]
        c.drawString(2*cm, y, desc)
        c.drawString(10*cm, y, item['cantidad'])
        c.drawString(12*cm, y, formatear_guarani(item['precio']))
        c.drawString(15*cm, y, formatear_guarani(item['iva']))
        c.drawString(17*cm, y, formatear_guarani(item['total']))
        y -= 0.6*cm
        
        if y < 8*cm:  # Salto de página si es necesario
            c.showPage()
            y = height - 3*cm
    
    # Totales
    y -= 1*cm
    c.line(2*cm, y, 19*cm, y)
    y -= 0.7*cm
    
    c.setFont(font_bold, 10)
    c.drawString(14*cm, y, "SUBTOTAL:")
    c.drawString(17*cm, y, formatear_guarani(totales['subtotal']))
    y -= 0.6*cm
    
    if int(totales['iva5']) > 0:
        c.drawString(14*cm, y, "IVA 5%:")
        c.drawString(17*cm, y, formatear_guarani(totales['iva5']))
        y -= 0.6*cm
    
    if int(totales['iva10']) > 0:
        c.drawString(14*cm, y, "IVA 10%:")
        c.drawString(17*cm, y, formatear_guarani(totales['iva10']))
        y -= 0.6*cm
    
    c.setFont(font_bold, 12)
    c.drawString(14*cm, y, "TOTAL:")
    c.drawString(17*cm, y, formatear_guarani(totales['total']))
    
    # Pie de página
    y = 3*cm
    c.setFont(font_normal, 8)
    c.drawCentredString(width/2, y, "Documento generado electrónicamente - Valido para SIFEN")
    
    c.save()
    print(f"PDF generado: {pdf_file}")
    return pdf_file


def main():
    """Función principal"""
    print("=" * 60)
    print("GENERADOR DE PDF A PARTIR DE XML SIFEN")
    print("=" * 60)
    
    # Generar XML de ejemplo primero
    print("\n1. Generando XML de ejemplo...")
    xml_file = "factura_para_pdf.xml"
    generar_factura(datos_ejemplo(), xml_file)
    
    # Generar PDF
    print("\n2. Generando PDF...")
    pdf_file = generar_pdf_factura(xml_file)
    
    if pdf_file:
        print(f"\n✓ PDF generado exitosamente: {pdf_file}")
        print("\nPara ver el PDF:")
        print(f"- Abre el archivo: {pdf_file}")
        print("- O haz doble clic en el archivo")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
