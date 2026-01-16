#!/usr/bin/env python3
"""
Genera PDF profesional de factura SIFEN con diseño mejorado
"""

import sys
import os
import argparse
from pathlib import Path
import qrcode
from io import BytesIO
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfgen import canvas

def generar_pdf_profesional(xml_path, output_path):
    """Genera PDF profesional de factura SIFEN"""
    
    # Parsear XML
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(xml_path, parser)
    root = tree.getroot()
    
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    
    # Extraer datos
    de = root.find(f".//{SIFEN_NS}DE")
    cdc = de.get('Id')
    
    gDatGralOpe = root.find(f".//{SIFEN_NS}gDatGralOpe")
    gEmis = gDatGralOpe.find(f"{SIFEN_NS}gEmis")
    gDatRec = gDatGralOpe.find(f"{SIFEN_NS}gDatRec")
    gTimb = root.find(f".//{SIFEN_NS}gTimb")
    gTotSub = root.find(f".//{SIFEN_NS}gTotSub")
    
    # Datos del emisor
    ruc_em = gEmis.find(f"{SIFEN_NS}dRucEm").text
    dv_em = gEmis.find(f"{SIFEN_NS}dDVEmi").text
    nom_em = gEmis.find(f"{SIFEN_NS}dNomEmi").text
    dir_em = gEmis.find(f"{SIFEN_NS}dDirEmi").text
    tel_em = gEmis.find(f"{SIFEN_NS}dTelEmi").text
    email_em = gEmis.find(f"{SIFEN_NS}dEmailE").text
    
    # Datos del receptor
    nom_rec_elem = gDatRec.find(f"{SIFEN_NS}dNomRec")
    nom_rec = nom_rec_elem.text if nom_rec_elem is not None else "CONSUMIDOR FINAL"
    
    ruc_rec_elem = gDatRec.find(f"{SIFEN_NS}dRucRec")
    ruc_rec = ruc_rec_elem.text if ruc_rec_elem is not None else ""
    
    dv_rec_elem = gDatRec.find(f"{SIFEN_NS}dDVRec")
    dv_rec = dv_rec_elem.text if dv_rec_elem is not None else ""
    
    # Timbrado
    timbrado = gTimb.find(f"{SIFEN_NS}dNumTim").text
    est = gTimb.find(f"{SIFEN_NS}dEst").text
    pun_exp = gTimb.find(f"{SIFEN_NS}dPunExp").text
    num_doc = gTimb.find(f"{SIFEN_NS}dNumDoc").text
    
    # Fecha
    fecha_emision = gDatGralOpe.find(f"{SIFEN_NS}dFeEmiDE").text
    
    # Totales
    total_gral = gTotSub.find(f"{SIFEN_NS}dTotGralOpe").text
    total_iva = gTotSub.find(f"{SIFEN_NS}dTotIVA").text
    
    # Items
    items = root.findall(f".//{SIFEN_NS}gCamItem")
    
    # QR
    gCamFuFD = root.find(f"{SIFEN_NS}gCamFuFD")
    qr_url = None
    if gCamFuFD is not None:
        dCarQR = gCamFuFD.find(f"{SIFEN_NS}dCarQR")
        if dCarQR is not None:
            qr_url = dCarQR.text
    
    # Crear PDF
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                           rightMargin=2*cm, leftMargin=2*cm,
                           topMargin=2*cm, bottomMargin=2*cm)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Estilos personalizados
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        spaceAfter=6,
        alignment=TA_CENTER
    )
    
    header_style = ParagraphStyle(
        'Header',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#1a1a1a'),
        fontName='Helvetica-Bold'
    )
    
    # === ENCABEZADO ===
    story.append(Paragraph("FACTURA ELECTRÓNICA", title_style))
    story.append(Paragraph("Documento Tributario Electrónico", subtitle_style))
    story.append(Spacer(1, 0.5*cm))
    
    # === DATOS DEL EMISOR Y RECEPTOR ===
    datos_table = Table([
        [
            Paragraph(f"<b>EMISOR</b><br/>{nom_em}<br/>RUC: {ruc_em}-{dv_em}<br/>{dir_em}<br/>Tel: {tel_em}<br/>Email: {email_em}", styles['Normal']),
            Paragraph(f"<b>RECEPTOR</b><br/>{nom_rec}<br/>RUC: {ruc_rec}-{dv_rec if dv_rec else ''}", styles['Normal'])
        ]
    ], colWidths=[9*cm, 8*cm])
    
    datos_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f0f0f0')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#f8f8f8')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc'))
    ]))
    
    story.append(datos_table)
    story.append(Spacer(1, 0.5*cm))
    
    # === INFORMACIÓN DEL DOCUMENTO ===
    info_doc = Table([
        ["Timbrado:", timbrado, "Fecha:", fecha_emision.split('T')[0]],
        ["Establecimiento:", est, "Punto Exp.:", pun_exp],
        ["Nro. Documento:", f"{est}-{pun_exp}-{num_doc}", "CDC:", cdc[:20] + "..."]
    ], colWidths=[3*cm, 5*cm, 3*cm, 6*cm])
    
    info_doc.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8e8e8')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#e8e8e8')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc'))
    ]))
    
    story.append(info_doc)
    story.append(Spacer(1, 0.5*cm))
    
    # === ITEMS ===
    story.append(Paragraph("<b>DETALLE DE ITEMS</b>", header_style))
    story.append(Spacer(1, 0.3*cm))
    
    items_data = [["Cant.", "Descripción", "Precio Unit.", "Total"]]
    
    for item in items:
        desc = item.find(f"{SIFEN_NS}dDesProSer").text
        cant_elem = item.find(f"{SIFEN_NS}dCantProSer")
        cant = cant_elem.text if cant_elem is not None else "1"
        
        # Buscar precio en gValItem
        gValItem = item.find(f".//{SIFEN_NS}gValItem")
        if gValItem is not None:
            precio_elem = gValItem.find(f"{SIFEN_NS}dPUniProSer")
            total_elem = gValItem.find(f"{SIFEN_NS}dTotOpeItem")
            precio = precio_elem.text if precio_elem is not None else "0"
            total_item = total_elem.text if total_elem is not None else "0"
        else:
            precio = "0"
            total_item = "0"
        
        items_data.append([
            cant,
            desc,
            f"₲ {float(precio):,.0f}",
            f"₲ {float(total_item):,.0f}"
        ])
    
    items_table = Table(items_data, colWidths=[2*cm, 9*cm, 3*cm, 3*cm])
    
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')])
    ]))
    
    story.append(items_table)
    story.append(Spacer(1, 0.5*cm))
    
    # === TOTALES ===
    totales_data = [
        ["Subtotal:", f"₲ {float(total_gral) - float(total_iva):,.0f}"],
        ["IVA:", f"₲ {float(total_iva):,.0f}"],
        ["TOTAL:", f"₲ {float(total_gral):,.0f}"]
    ]
    
    totales_table = Table(totales_data, colWidths=[11*cm, 6*cm])
    
    totales_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 1), 'Helvetica'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 1), 10),
        ('FONTSIZE', (0, 2), (-1, 2), 12),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#2c3e50')),
        ('LINEABOVE', (0, 2), (-1, 2), 2, colors.HexColor('#2c3e50')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(totales_table)
    story.append(Spacer(1, 1*cm))
    
    # === QR CODE ===
    if qr_url:
        story.append(Paragraph("<b>CÓDIGO QR PARA VERIFICACIÓN</b>", header_style))
        story.append(Spacer(1, 0.3*cm))
        
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(qr_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        
        qr_image = Image(qr_buffer, width=4*cm, height=4*cm)
        story.append(qr_image)
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(f"<font size=7>CDC: {cdc}</font>", subtitle_style))
    else:
        story.append(Paragraph("<b>⚠️ CÓDIGO QR NO DISPONIBLE</b>", subtitle_style))
    
    # === PIE DE PÁGINA ===
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        "<font size=8 color='#666666'>Documento Electrónico generado según normativa SIFEN<br/>"
        "Este documento tiene validez tributaria</font>",
        subtitle_style
    ))
    
    # Generar PDF
    doc.build(story)
    
    print(f"✅ PDF profesional generado: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Generar PDF profesional de factura SIFEN")
    parser.add_argument('--xml', required=True, help='XML de factura')
    parser.add_argument('--output', required=True, help='PDF de salida')
    
    args = parser.parse_args()
    
    if not Path(args.xml).exists():
        print(f"❌ Archivo no encontrado: {args.xml}")
        sys.exit(1)
    
    try:
        generar_pdf_profesional(args.xml, args.output)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
