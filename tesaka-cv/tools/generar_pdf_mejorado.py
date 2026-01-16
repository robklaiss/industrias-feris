#!/usr/bin/env python3
"""
Generador de PDF SIFEN Mejorado - Maneja XMLs con o sin QR
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
import qrcode
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import Image
import base64

class SifenPDFGeneratorMejorado:
    """Generador de PDF mejorado para documentos SIFEN"""
    
    def __init__(self):
        self.page_size = A4
        self.margin = 15 * mm
        
    def parse_xml(self, xml_path):
        """Parsea el XML SIFEN con manejo robusto"""
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(xml_path, parser)
        root = tree.getroot()
        
        # Datos por defecto
        data = {
            'ruc_rec': 'N/A',
            'dv_rec': '',
            'nom_rec': 'CONSUMIDOR FINAL',
            'items': [],
            'tot_gral_ope': '0',
            'tot_iva': '0',
            'iva_5': '0',
            'iva_10': '0',
            'sub_ex': '0',
            'sub_5': '0',
            'sub_10': '0',
            'qr': ''
        }
        
        # Extraer datos
        SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
        
        # Datos del DE
        de = root.find(f".//{SIFEN_NS}DE")
        if de is not None:
            data['cdc'] = de.get('Id', 'N/A')
            data['dv_id'] = de.findtext(f"{SIFEN_NS}dDVId", '0')
            data['fec_firma'] = de.findtext(f"{SIFEN_NS}dFecFirma", 'N/A')
            
            # Timbrado
            gTimb = de.find(f".//{SIFEN_NS}gTimb")
            if gTimb is not None:
                data['num_tim'] = gTimb.findtext(f"{SIFEN_NS}dNumTim", 'N/A')
                data['est'] = gTimb.findtext(f"{SIFEN_NS}dEst", 'N/A')
                data['pun_exp'] = gTimb.findtext(f"{SIFEN_NS}dPunExp", 'N/A')
                data['num_doc'] = gTimb.findtext(f"{SIFEN_NS}dNumDoc", 'N/A')
                data['fe_ini_t'] = gTimb.findtext(f"{SIFEN_NS}dFeIniT", 'N/A')
            
            # Emisor
            gEmis = de.find(f".//{SIFEN_NS}gEmis")
            if gEmis is not None:
                data['ruc_em'] = gEmis.findtext(f"{SIFEN_NS}dRucEm", 'N/A')
                data['dv_emi'] = gEmis.findtext(f"{SIFEN_NS}dDVEmi", '')
                data['nom_emi'] = gEmis.findtext(f"{SIFEN_NS}dNomEmi", 'N/A')
                data['dir_emi'] = gEmis.findtext(f"{SIFEN_NS}dDirEmi", 'N/A')
            
            # Receptor
            gDatRec = de.find(f".//{SIFEN_NS}gDatRec")
            if gDatRec is not None:
                data['ruc_rec'] = gDatRec.findtext(f"{SIFEN_NS}dRucRec", 'N/A')
                data['dv_rec'] = gDatRec.findtext(f"{SIFEN_NS}dDVRec", '')
                data['nom_rec'] = gDatRec.findtext(f"{SIFEN_NS}dNomRec", 'CONSUMIDOR FINAL')
            
            # Items
            gCamItem = de.findall(f".//{SIFEN_NS}gCamItem")
            for item in gCamItem:
                item_data = {
                    'cod_int': item.findtext(f"{SIFEN_NS}dCodInt", ''),
                    'des_pro': item.findtext(f"{SIFEN_NS}dDesProSer", ''),
                    'cant': item.findtext(f"{SIFEN_NS}dCantProSer", '0'),
                    'uni_med': item.findtext(f"{SIFEN_NS}cUniMed", ''),
                    'precio': item.findtext(f".//{SIFEN_NS}dPUniProSer", '0'),
                    'total': item.findtext(f".//{SIFEN_NS}dTotOpeItem", '0')
                }
                data['items'].append(item_data)
            
            # Totales
            gTotSub = de.find(f".//{SIFEN_NS}gTotSub")
            if gTotSub is not None:
                data['tot_gral_ope'] = gTotSub.findtext(f"{SIFEN_NS}dTotGralOpe", '0')
                data['tot_iva'] = gTotSub.findtext(f"{SIFEN_NS}dTotIVA", '0')
                data['iva_5'] = gTotSub.findtext(f"{SIFEN_NS}dIVA5", '0')
                data['iva_10'] = gTotSub.findtext(f"{SIFEN_NS}dIVA10", '0')
                data['sub_ex'] = gTotSub.findtext(f"{SIFEN_NS}dSubExe", '0')
                data['sub_5'] = gTotSub.findtext(f"{SIFEN_NS}dSub5", '0')
                data['sub_10'] = gTotSub.findtext(f"{SIFEN_NS}dSub10", '0')
        
        # QR (puede estar en rDE o fuera)
        gCamFuFD = root.find(f".//{SIFEN_NS}gCamFuFD")
        if gCamFuFD is not None:
            data['qr'] = gCamFuFD.findtext(f"{SIFEN_NS}dCarQR", '')
        
        return data
    
    def generar_qr(self, qr_data):
        """Genera la imagen del código QR"""
        if not qr_data:
            return None
            
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=1,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        return img
    
    def format_number(self, num_str):
        """Formatea número con separadores de miles"""
        try:
            num = float(num_str)
            return f"{num:,.0f}".replace(",", ".")
        except:
            return num_str
    
    def generar_pdf(self, xml_path, output_path):
        """Genera el PDF completo"""
        # Parsear XML
        data = self.parse_xml(xml_path)
        
        # Crear PDF
        doc = SimpleDocTemplate(
            output_path,
            pagesize=self.page_size,
            leftMargin=self.margin,
            rightMargin=self.margin,
            topMargin=self.margin,
            bottomMargin=self.margin
        )
        
        # Estilos
        styles = getSampleStyleSheet()
        style_title = styles['Title']
        style_normal = styles['Normal']
        style_small = ParagraphStyle('CustomSmall', parent=styles['Normal'], fontSize=8)
        style_subtitle = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=12, textColor=colors.darkblue)
        
        # Contenido
        story = []
        
        # Título
        title = Paragraph("FACTURA ELECTRÓNICA", style_title)
        story.append(title)
        story.append(Spacer(1, 10))
        
        # Encabezado - Timbrado
        header_data = [
            ["RUC:", f"{data['ruc_em']}-{data['dv_emi']}", "Timbrado N°:", data.get('num_tim', 'N/A')],
            ["Nombre:", data.get('nom_emi', 'N/A'), "Establecimiento:", data.get('est', 'N/A')],
            ["Dirección:", data.get('dir_emi', 'N/A'), "Punto Expedición:", data.get('pun_exp', 'N/A')],
            ["N° Factura:", data.get('num_doc', 'N/A'), "Vigencia:", data.get('fe_ini_t', 'N/A')]
        ]
        
        header_table = Table(header_data, colWidths=[40*mm, 60*mm, 40*mm, 30*mm])
        header_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))
        
        # Datos del Receptor
        story.append(Paragraph("Datos del Receptor", style_subtitle))
        rec_data = [
            ["RUC:", f"{data['ruc_rec']}-{data['dv_rec']}" if data['dv_rec'] else data['ruc_rec'], 
             "Nombre:", data['nom_rec']]
        ]
        
        rec_table = Table(rec_data, colWidths=[40*mm, 60*mm, 40*mm, 60*mm])
        rec_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
        ]))
        story.append(rec_table)
        story.append(Spacer(1, 10))
        
        # Items
        story.append(Paragraph("Detalle de Items", style_subtitle))
        
        if data['items']:
            # Cabecera de items
            items_header = [["Código", "Descripción", "Cant", "Precio", "Total"]]
            items_table = Table(items_header, colWidths=[30*mm, 70*mm, 20*mm, 30*mm, 30*mm])
            items_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ]))
            story.append(items_table)
            
            # Datos de items
            for item in data['items']:
                item_row = [
                    item['cod_int'],
                    item['des_pro'],
                    item['cant'],
                    self.format_number(item['precio']),
                    self.format_number(item['total'])
                ]
                item_table = Table([item_row], colWidths=[30*mm, 70*mm, 20*mm, 30*mm, 30*mm])
                item_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ]))
                story.append(item_table)
        else:
            story.append(Paragraph("No hay items en el documento", style_small))
        
        story.append(Spacer(1, 10))
        
        # Totales
        totals_data = [
            ["Subtotal Exenta:", self.format_number(data['sub_ex'])],
            ["Subtotal 5%:", self.format_number(data['sub_5'])],
            ["Subtotal 10%:", self.format_number(data['sub_10'])],
            ["IVA 5%:", self.format_number(data['iva_5'])],
            ["IVA 10%:", self.format_number(data['iva_10'])],
            ["Total General:", self.format_number(data['tot_gral_ope'])]
        ]
        
        totals_table = Table(totals_data, colWidths=[80*mm, 30*mm])
        totals_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -2), 'Helvetica'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
        ]))
        story.append(totals_table)
        story.append(Spacer(1, 10))
        
        # CDC y QR
        story.append(Paragraph(f"CDC: {data.get('cdc', 'N/A')}", style_normal))
        story.append(Spacer(1, 5))
        
        if data['qr']:
            # Generar QR
            qr_img = self.generar_qr(data['qr'])
            if qr_img:
                qr_path = "/tmp/qr_temp.png"
                qr_img.save(qr_path)
                
                # Agregar QR al PDF
                story.append(Spacer(1, 10))
                story.append(Paragraph("Código QR de Autenticación:", style_subtitle))
                
                # Crear tabla con QR
                qr_table = Table([[
                    Paragraph("Escanea este código para verificar la autenticidad del documento en SIFEN.", style_small),
                    Image(qr_path, width=40*mm, height=40*mm)
                ]], colWidths=[80*mm, 40*mm])
                qr_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(qr_table)
        else:
            story.append(Paragraph("⚠️ Este documento no contiene código QR", style_small))
        
        # Footer
        story.append(Spacer(1, 20))
        footer_text = f"Fecha y hora de firma: {data.get('fec_firma', 'N/A')}"
        story.append(Paragraph(footer_text, style_small))
        
        # Generar PDF
        doc.build(story)
        
        # Limpiar QR temporal
        if data['qr'] and os.path.exists("/tmp/qr_temp.png"):
            os.remove("/tmp/qr_temp.png")

def main():
    parser = argparse.ArgumentParser(description="Generar PDF SIFEN Mejorado")
    parser.add_argument('--xml', required=True, help='Archivo XML SIFEN')
    parser.add_argument('--output', required=True, help='Archivo PDF de salida')
    
    args = parser.parse_args()
    
    if not Path(args.xml).exists():
        print(f"❌ Archivo XML no encontrado: {args.xml}")
        sys.exit(1)
    
    try:
        generator = SifenPDFGeneratorMejorado()
        generator.generar_pdf(args.xml, args.output)
        print(f"✅ PDF generado: {args.output}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
