"""
Módulo para generar PDFs de documentos imprimibles
"""
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


def generate_purchase_order_pdf(purchase_order, cliente, items, monto_total) -> bytes:
    """Genera PDF de orden de compra"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Título
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#000000'),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    elements.append(Paragraph("ORDEN DE COMPRA", title_style))
    elements.append(Paragraph(f"Número: {purchase_order.numero}", styles['Normal']))
    elements.append(Paragraph(f"Fecha: {purchase_order.fecha}", styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Información
    info_data = [
        ['DATOS DEL PROVEEDOR', 'DATOS DEL COMPRADOR'],
        [f"Razón Social: {cliente.get('nombre', '-') if cliente else '-'}",
         f"Contrato: {purchase_order.numero_contrato or '-'}"],
        [f"RUC: {cliente.get('ruc', '-') if cliente else '-'}",
         f"Modo: {purchase_order.sync_mode or '-'}"],
    ]
    if cliente and cliente.get('direccion'):
        info_data.append([f"Dirección: {cliente['direccion']}", ""])
    
    info_table = Table(info_data, colWidths=[9*cm, 9*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Tabla de items
    table_data = [['Producto', 'Unidad', 'Cantidad', 'Precio Unit.', 'Total']]
    for item in items:
        table_data.append([
            item.get('producto', ''),
            item.get('unidad_medida', ''),
            f"{item.get('cantidad', 0):.2f}",
            f"{item.get('precio_unitario', 0):.2f}",
            f"{item.get('cantidad', 0) * item.get('precio_unitario', 0):.2f}"
        ])
    table_data.append(['', '', '', 'TOTAL:', f"{monto_total:.2f}"])
    
    table = Table(table_data, colWidths=[7*cm, 2.5*cm, 2.5*cm, 3*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 1*cm))
    
    # Firmas
    signature_data = [
        ['PROVEEDOR', 'COMPRADOR'],
        ['_________________________', '_________________________'],
        ['Firma y Aclaración', 'Firma y Aclaración'],
    ]
    sig_table = Table(signature_data, colWidths=[9*cm, 9*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    elements.append(sig_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generate_delivery_note_pdf(delivery_note, cliente, items) -> bytes:
    """Genera PDF de nota de entrega"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#000000'),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    elements.append(Paragraph("NOTA INTERNA DE ENTREGA", title_style))
    elements.append(Paragraph(f"Número: {delivery_note.numero_nota}", styles['Normal']))
    elements.append(Paragraph(f"Fecha: {delivery_note.fecha}", styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Información
    info_data = [
        ['DATOS DEL CLIENTE', 'INFORMACIÓN ADICIONAL'],
        [f"Razón Social: {cliente.get('nombre', '-') if cliente else '-'}",
         f"Modo: {delivery_note.sync_mode or '-'}"],
        [f"RUC: {cliente.get('ruc', '-') if cliente else '-'}", ""],
    ]
    if delivery_note.direccion_entrega:
        info_data.append([f"Dirección: {delivery_note.direccion_entrega}", ""])
    if delivery_note.numero_contrato:
        info_data.append([f"Contrato: {delivery_note.numero_contrato}", ""])
    
    info_table = Table(info_data, colWidths=[9*cm, 9*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Tabla de items
    table_data = [['Producto', 'Unidad', 'Cantidad']]
    for item in items:
        table_data.append([
            item.get('producto', ''),
            item.get('unidad_medida', ''),
            f"{item.get('cantidad', 0):.2f}"
        ])
    
    table = Table(table_data, colWidths=[12*cm, 3*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 1*cm))
    
    # Firmas
    signature_data = [
        ['ENTREGA', 'RECIBE'],
        ['_________________________', '_________________________'],
        ['Firma y Aclaración', 'Firma y Aclaración'],
    ]
    if delivery_note.firma_entrega:
        signature_data[1][0] = delivery_note.firma_entrega
    if delivery_note.firma_recibe:
        signature_data[1][1] = delivery_note.firma_recibe
    
    sig_table = Table(signature_data, colWidths=[9*cm, 9*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    elements.append(sig_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generate_remission_pdf(remission, cliente, items) -> bytes:
    """Genera PDF de remisión"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#000000'),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    elements.append(Paragraph("REMISIÓN", title_style))
    elements.append(Paragraph(f"Número: {remission.numero_remision}", styles['Normal']))
    elements.append(Paragraph(f"Fecha: {remission.fecha_inicio}", styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Información
    info_data = [
        ['DATOS DEL CLIENTE', 'TRANSPORTE'],
        [f"Razón Social: {cliente.get('nombre', '-') if cliente else '-'}",
         f"Transportista: {remission.transportista_nombre or '-'}"],
        [f"RUC: {cliente.get('ruc', '-') if cliente else '-'}",
         f"RUC Transportista: {remission.transportista_ruc or '-'}"],
        [f"Contrato: {remission.numero_contrato or '-'}",
         f"Vehículo: {remission.vehiculo_marca or '-'}"],
        ['', f"Chapa: {remission.chapa or '-'}"],
        ['', f"Conductor: {remission.conductor_nombre or '-'}"],
        ['', f"CI Conductor: {remission.conductor_ci or '-'}"],
    ]
    
    info_table = Table(info_data, colWidths=[9*cm, 9*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.3*cm))
    
    # Logística
    logistics_data = [
        ['INFORMACIÓN LOGÍSTICA'],
        [f"Partida: {remission.partida or '-'}"],
        [f"Llegada: {remission.llegada or '-'}"],
    ]
    logistics_table = Table(logistics_data, colWidths=[18*cm])
    logistics_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(logistics_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Tabla de items
    table_data = [['Producto', 'Unidad', 'Cantidad']]
    for item in items:
        table_data.append([
            item.get('producto', ''),
            item.get('unidad_medida', ''),
            f"{item.get('cantidad', 0):.2f}"
        ])
    
    table = Table(table_data, colWidths=[12*cm, 3*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 1*cm))
    
    # Firmas
    signature_data = [
        ['EMISOR', 'CONDUCTOR'],
        ['_________________________', '_________________________'],
        ['Firma y Aclaración', 'Firma y Aclaración'],
    ]
    sig_table = Table(signature_data, colWidths=[9*cm, 9*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    elements.append(sig_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generate_sales_invoice_pdf(sales_invoice, cliente, items, monto_total) -> bytes:
    """Genera PDF de factura de venta"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#000000'),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    elements.append(Paragraph("FACTURA DE VENTA", title_style))
    elements.append(Paragraph(f"Número: {sales_invoice.numero}", styles['Normal']))
    elements.append(Paragraph(f"Fecha: {sales_invoice.fecha}", styles['Normal']))
    elements.append(Paragraph(f"Condición: {sales_invoice.condicion_venta.upper()}", styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Información
    info_data = [
        ['DATOS DEL CLIENTE', 'INFORMACIÓN DE FACTURACIÓN'],
        [f"Razón Social: {cliente.get('nombre', '-') if cliente else '-'}",
         f"Condición: {sales_invoice.condicion_venta.upper()}"],
        [f"RUC: {cliente.get('ruc', '-') if cliente else '-'}", ""],
    ]
    if sales_invoice.direccion:
        info_data.append([f"Dirección: {sales_invoice.direccion}", ""])
    if sales_invoice.numero_contrato:
        info_data.append([f"Contrato: {sales_invoice.numero_contrato}", ""])
    
    info_table = Table(info_data, colWidths=[9*cm, 9*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Tabla de items
    table_data = [['Producto', 'Unidad', 'Cantidad', 'Precio Unit.', 'Subtotal']]
    for item in items:
        table_data.append([
            item.get('producto', ''),
            item.get('unidad_medida', ''),
            f"{item.get('cantidad', 0):.2f}",
            f"{item.get('precio_unitario', 0):.2f}",
            f"{item.get('cantidad', 0) * item.get('precio_unitario', 0):.2f}"
        ])
    table_data.append(['', '', '', 'TOTAL:', f"{monto_total:.2f}"])
    
    table = Table(table_data, colWidths=[6*cm, 2.5*cm, 2.5*cm, 3*cm, 4*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 1*cm))
    
    # Firmas
    signature_data = [
        ['VENDEDOR', 'CLIENTE'],
        ['_________________________', '_________________________'],
        ['Firma y Aclaración', 'Firma y Aclaración'],
    ]
    sig_table = Table(signature_data, colWidths=[9*cm, 9*cm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    elements.append(sig_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

