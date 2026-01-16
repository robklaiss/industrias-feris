#!/usr/bin/env python3
"""
Generador de PDF SIFEN con QR
Crea la representación impresa del documento electrónico con código QR
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
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import Image
import base64

class SifenPDFGenerator:
    """Generador de PDF para documentos SIFEN"""
    
    def __init__(self):
        self.page_size = A4
        self.margin = 15 * mm
        
    def parse_xml(self, xml_path):
        """Parsea el XML SIFEN"""
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(xml_path, parser)
        root = tree.getroot()
        
        # Extraer datos
        SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
        data = {}
        
        # Datos del DE
        de = root.find(f".//{SIFEN_NS}DE")
        data['cdc'] = de.get('Id')
        data['dv_id'] = de.find(f"{SIFEN_NS}dDVId").text
        data['fec_firma'] = de.find(f"{SIFEN_NS}dFecFirma").text
        
        # Timbrado
        gTimb = de.find(f".//{SIFEN_NS}gTimb")
        data['num_tim'] = gTimb.find(f"{SIFEN_NS}dNumTim").text
        data['est'] = gTimb.find(f"{SIFEN_NS}dEst").text
        data['pun_exp'] = gTimb.find(f"{SIFEN_NS}dPunExp").text
        data['num_doc'] = gTimb.find(f"{SIFEN_NS}dNumDoc").text
        data['fe_ini_t'] = gTimb.find(f"{SIFEN_NS}dFeIniT").text
        
        # Emisor
        gEmis = de.find(f".//{SIFEN_NS}gEmis")
        data['ruc_em'] = gEmis.find(f"{SIFEN_NS}dRucEm").text
        data['dv_emi'] = gEmis.find(f"{SIFEN_NS}dDVEmi").text
        data['nom_emi'] = gEmis.find(f"{SIFEN_NS}dNomEmi").text
        data['dir_emi'] = gEmis.find(f"{SIFEN_NS}dDirEmi").text
        
        # Receptor
        gDatRec = de.find(f".//{SIFEN_NS}gDatRec")
        data['ruc_rec'] = gDatRec.find(f"{SIFEN_NS}dRucRec").text
        data['dv_rec'] = gDatRec.find(f"{SIFEN_NS}dDVRec").text
        data['nom_rec'] = gDatRec.find(f"{SIFEN_NS}dNomRec").text
        
        # Totales
        gTotSub = de.find(f".//{SIFEN_NS}gTotSub")
        if gTotSub is not None:
            data['tot_gral_ope'] = gTotSub.find(f"{SIFEN_NS}dTotGralOpe").text
            data['tot_iva'] = gTotSub.find(f"{SIFEN_NS}dTotIVA").text
            data['iva_5'] = gTotSub.find(f"{SIFEN_NS}dIVA5").text
            data['iva_10'] = gTotSub.find(f"{SIFEN_NS}dIVA10").text
            data['sub_ex'] = gTotSub.find(f"{SIFEN_NS}dSubExe").text
            data['sub_5'] = gTotSub.find(f"{SIFEN_NS}dSub5").text
            data['sub_10'] = gTotSub.find(f"{SIFEN_NS}dSub10").text
        else:
            # Si no hay gTotSub, buscar en gCamFE (formato antiguo)
            gCamFE = de.find(f".//{SIFEN_NS}gCamFE")
            if gCamFE is not None:
                data['tot_gral_ope'] = gCamFE.find(f"{SIFEN_NS}dTotGralOpe").text
                data['tot_iva'] = gCamFE.find(f"{SIFEN_NS}dTotalIVA").text
                data['iva_5'] = "0"
                data['iva_10'] = data['tot_iva']
                data['sub_ex'] = "0"
                data['sub_5'] = "0"
                data['sub_10'] = data['tot_gral_ope']
        
        # QR
        gCamFuFD = root.find(f".//{SIFEN_NS}gCamFuFD")
        if gCamFuFD is not None:
            data['qr'] = gCamFuFD.find(f"{SIFEN_NS}dCarQR").text
        else:
            data['qr'] = ""
        
        # Items
        data['items'] = []
        gCamItem = de.findall(f".//{SIFEN_NS}gCamItem")
        for item in gCamItem:
            item_data = {
                'cod_int': item.find(f"{SIFEN_NS}dCodInt").text,
                'des_pro': item.find(f"{SIFEN_NS}dDesProSer").text,
                'cant': item.find(f"{SIFEN_NS}dCantProSer").text,
                'uni_med': item.find(f"{SIFEN_NS}cUniMed").text,
                'precio': item.find(f".//{SIFEN_NS}dPUniProSer").text,
                'total': item.find(f".//{SIFEN_NS}dTotOpeItem").text
            }
            data['items'].append(item_data)
        
        return data
    
    def generar_qr(self, qr_data):
        """Genera la imagen del código QR"""
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
        style_small = styles['Normal']
        style_small.fontSize = 8
        
        # Contenido
        story = []
        
        # Título
        title = Paragraph("FACTURA ELECTRÓNICA", style_title)
        story.append(title)
        story.append(Spacer(1, 10))
        
        # Encabezado - Timbrado
        header_data = [
            ["RUC:", f"{data['ruc_em']}-{data['dv_emi']}", "Timbrado N°:", data['num_tim']],
            ["Nombre:", data['nom_emi'], "Establecimiento:", data['est']],
            ["Dirección:", data['dir_emi'], "Punto Expedición:", data['pun_exp']],
            ["N° Factura:", data['num_doc'], "Vigencia:", data['fe_ini_t']]
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
        story.append(Paragraph("Datos del Receptor", style_normal))
        rec_data = [
            ["RUC:", f"{data['ruc_rec']}-{data['dv_rec']}", "Nombre:", data['nom_rec']]
        ]
        
        rec_table = Table(rec_data, colWidths=[40*mm, 60*mm, 40*mm, 60*mm])
        rec_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ]))
        story.append(rec_table)
        story.append(Spacer(1, 10))
        
        # Items
        story.append(Paragraph("Detalle de Items", style_normal))
        
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
        story.append(Paragraph(f"CDC: {data['cdc']}", style_normal))
        story.append(Spacer(1, 5))
        
        if data['qr']:
            # Generar QR
            qr_img = self.generar_qr(data['qr'])
            qr_path = "/tmp/qr_temp.png"
            qr_img.save(qr_path)
            
            # Agregar QR al PDF
            story.append(Spacer(1, 10))
            story.append(Paragraph("Código QR de Autenticación:", style_normal))
            
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
        
        # Footer
        story.append(Spacer(1, 20))
        footer_text = f"Fecha y hora de firma: {data['fec_firma']}"
        story.append(Paragraph(footer_text, style_small))
        
        # Generar PDF
        doc.build(story)
        
        # Limpiar QR temporal
        if data['qr'] and os.path.exists("/tmp/qr_temp.png"):
            os.remove("/tmp/qr_temp.png")

def main():
    parser = argparse.ArgumentParser(description="Generar PDF SIFEN con QR")
    parser.add_argument('--xml', required=True, help='Archivo XML SIFEN')
    parser.add_argument('--output', required=True, help='Archivo PDF de salida')
    
    args = parser.parse_args()
    
    if not Path(args.xml).exists():
        print(f"❌ Archivo XML no encontrado: {args.xml}")
        sys.exit(1)
    
    try:
        generator = SifenPDFGenerator()
        generator.generar_pdf(args.xml, args.output)
        print(f"✅ PDF generado: {args.output}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
