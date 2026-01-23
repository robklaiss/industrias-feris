#!/usr/bin/env python3
"""Generador de PDF con layout SIFEN sin superposiciones (usa datos dummy)."""

import os
import sys
import io
from datetime import datetime
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from tools.generar_factura import generar_factura, datos_ejemplo
    import qrcode
except ImportError as exc:
    print("Error: Falta instalar dependencias para generar PDF")
    print("Ejecuta: pip install reportlab qrcode[pil]")
    raise SystemExit(1) from exc


PAGE_WIDTH, PAGE_HEIGHT = A4
FONT_NORMAL = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


def wrap_text(text: str, font: str, size: int, max_width: float) -> List[str]:
    if not text:
        return []
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        tentative = (current + " " + word).strip() if current else word
        width = pdfmetrics.stringWidth(tentative, font, size)
        if width <= max_width or not current:
            current = tentative
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_block(c: canvas.Canvas, lines: List[str], x: float, start_y: float, font: str, size: int, leading: float) -> float:
    y = start_y
    for line in lines:
        c.setFont(font, size)
        c.drawString(x, y, line)
        y -= leading
    return y


def draw_wrapped(c: canvas.Canvas, text: str, x: float, start_y: float, width: float, font: str, size: int, leading: float) -> float:
    lines = wrap_text(text, font, size, width)
    if not lines:
        return start_y
    return draw_block(c, lines, x, start_y, font, size, leading)


def generar_qr_code(cdc: str, url: str = "https://ekuatia.set.gov.py/consultas/"):
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=0,
    )
    qr.add_data(f"{url}?cdc={cdc}")
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")


def _read_text(node, tag, ns):
    if node is None:
        return ""
    found = node.find(f"s:{tag}", ns)
    return found.text if found is not None and found.text else ""


def generar_pdf_mejorado(xml_file: str, pdf_file: Optional[str] = None) -> str:
    import xml.etree.ElementTree as ET

    tree = ET.parse(xml_file)
    root = tree.getroot()
    ns = {"s": "http://ekuatia.set.gov.py/sifen/xsd"}
    de = root.find("s:DE", ns)
    if de is None:
        raise ValueError("El XML no contiene el nodo <DE>")

    g_emis = de.find(".//s:gEmis", ns)
    g_rec = de.find(".//s:gDatRec", ns)
    g_timb = de.find(".//s:gTimb", ns)
    g_tot = de.find(".//s:gTotSub", ns)

    emisor = {
        "nombre": _read_text(g_emis, "dNomEmi", ns),
        "direccion": _read_text(g_emis, "dDirEmi", ns),
        "ciudad": _read_text(g_emis, "dDesCiuEmi", ns),
        "telefono": _read_text(g_emis, "dTelEmi", ns),
        "ruc": _read_text(g_emis, "dRucEm", ns),
        "dv": _read_text(g_emis, "dDVEmi", ns),
    }

    actividades = []
    if g_emis is not None:
        for act in g_emis.findall("s:gActEco", ns):
            txt = _read_text(act, "dDesActEco", ns)
            if txt:
                actividades.append(txt)

    receptor = {
        "ruc": _read_text(g_rec, "dRucRec", ns),
        "dv": _read_text(g_rec, "dDVRec", ns),
        "nombre": _read_text(g_rec, "dNomRec", ns),
        "direccion": _read_text(g_rec, "dDirRec", ns),
        "telefono": _read_text(g_rec, "dTelRec", ns),
        "email": _read_text(g_rec, "dEmailRec", ns),
    }

    timbrado = {
        "numero": _read_text(g_timb, "dNumTim", ns),
        "est": _read_text(g_timb, "dEst", ns),
        "exp": _read_text(g_timb, "dPunExp", ns),
        "doc": _read_text(g_timb, "dNumDoc", ns),
        "inicio": _read_text(g_timb, "dFeIniT", ns),
    }

    totales = {
        "sub": _read_text(g_tot, "dTotOpe", ns),
        "total": _read_text(g_tot, "dTotGralOpe", ns),
        "iva5": _read_text(g_tot, "dIVA5", ns),
        "iva10": _read_text(g_tot, "dIVA10", ns),
        "totiva": _read_text(g_tot, "dTotIVA", ns),
    }

    fecha_emision_xml = _read_text(de.find(".//s:gDatGralOpe", ns), "dFeEmiDE", ns)
    try:
        fecha_emision_fmt = datetime.fromisoformat(fecha_emision_xml).strftime("%d/%m/%Y") if fecha_emision_xml else datetime.now().strftime("%d/%m/%Y")
    except ValueError:
        fecha_emision_fmt = datetime.now().strftime("%d/%m/%Y")

    items = []
    for g_item in de.findall(".//s:gCamItem", ns):
        desc = _read_text(g_item, "dDesProSer", ns)
        cant = _read_text(g_item, "dCantProSer", ns)
        precio = _read_text(g_item.find("s:gValorItem", ns), "dPUniProSer", ns)
        tot = _read_text(g_item.find("s:gValorItem", ns), "dTotBruOpeItem", ns)
        iva = _read_text(g_item.find("s:gCamIVA", ns), "dTasaIVA", ns)
        items.append({"descripcion": desc, "cantidad": cant, "precio": precio, "total": tot, "iva": iva})

    if not items:
        items.append({"descripcion": "ITEM SIN DETALLE", "cantidad": "1", "precio": "0", "total": "0", "iva": "0"})

    if pdf_file is None:
        base = os.path.splitext(os.path.basename(xml_file))[0]
        pdf_file = f"{base}_mejorado.pdf"

    c = canvas.Canvas(pdf_file, pagesize=A4)

    # Cabecera izquierda
    left_y = PAGE_HEIGHT - 60
    emitter_lines = [emisor["nombre"].upper(), emisor["direccion"], f"{emisor['ciudad']} - TELÉF. {emisor['telefono']}"]
    emitter_lines = [line for line in emitter_lines if line.strip()]
    left_y = draw_block(c, emitter_lines, 60, left_y, FONT_NORMAL, 10, 12)
    act_y = left_y - 4
    for act in actividades[:2]:
        act_y = draw_wrapped(c, act, 40, act_y, 250, FONT_NORMAL, 8, 10) - 2

    # Cabecera derecha
    c.setFont(FONT_BOLD, 11)
    c.drawRightString(PAGE_WIDTH - 40, PAGE_HEIGHT - 55, f"TIMBRADO N° {timbrado['numero']}")
    c.setFont(FONT_NORMAL, 10)
    if timbrado["inicio"]:
        try:
            fecha_ini = datetime.fromisoformat(timbrado["inicio"]).strftime("%d/%m/%Y")
        except ValueError:
            fecha_ini = timbrado["inicio"]
        c.drawRightString(PAGE_WIDTH - 40, PAGE_HEIGHT - 70, f"Fecha Inicio Vigencia: {fecha_ini}")
    c.drawRightString(PAGE_WIDTH - 40, PAGE_HEIGHT - 85, f"RUC {emisor['ruc']} - {emisor['dv']}")
    c.drawRightString(PAGE_WIDTH - 40, PAGE_HEIGHT - 100, "FACTURA ELECTRÓNICA")
    c.drawRightString(PAGE_WIDTH - 40, PAGE_HEIGHT - 115, f"{timbrado['est']}-{timbrado['exp']}-{timbrado['doc']}")

    # Datos del receptor
    block_y = PAGE_HEIGHT - 160
    c.setFont(FONT_NORMAL, 8)
    c.drawString(25, block_y, "Fecha de emisión:")
    c.drawString(125, block_y, fecha_emision_fmt)
    block_y -= 14
    c.drawString(25, block_y, "RUC/Documento de Identidad N°:")
    c.drawString(170, block_y, f"{receptor['ruc']}-{receptor['dv']}")
    block_y -= 14
    c.drawString(25, block_y, "Nombre o Razón Social:")
    draw_wrapped(c, receptor["nombre"], 150, block_y, 220, FONT_NORMAL, 8, 10)
    block_y -= 18
    c.drawString(25, block_y, "Dirección:")
    draw_wrapped(c, receptor["direccion"], 90, block_y, 250, FONT_NORMAL, 8, 10)
    block_y -= 18
    c.drawString(25, block_y, "Teléfono:")
    c.drawString(90, block_y, receptor["telefono"])
    block_y -= 18
    c.drawString(25, block_y, "Correo Electrónico:")
    draw_wrapped(c, receptor["email"], 140, block_y, 230, FONT_NORMAL, 8, 10)

    c.drawString(330, PAGE_HEIGHT - 160, "Tipo de transacción:")
    c.drawString(460, PAGE_HEIGHT - 160, "Venta de mercadería")
    c.drawString(330, PAGE_HEIGHT - 175, "Condición de venta:")
    c.drawString(460, PAGE_HEIGHT - 175, "Contado")

    # Línea separadora
    c.setLineWidth(1)
    c.line(25, PAGE_HEIGHT - 260, PAGE_WIDTH - 25, PAGE_HEIGHT - 260)

    # Tabla de items
    col_x = [30, 90, 210, 360, 420, 470, 520, 565]
    y = PAGE_HEIGHT - 280
    headers = ["COD.", "CANTIDAD", "DESCRIPCIÓN", "PRECIO", "UNITARIO", "(IMP)", "DESC.", "VALOR"]
    for idx, head in enumerate(headers):
        c.drawString(col_x[idx], y, head)
    y -= 15
    c.setLineWidth(0.5)
    c.line(25, y, PAGE_WIDTH - 25, y)
    y -= 12

    for item in items:
        c.drawString(col_x[1], y, item["cantidad"])
        y = draw_wrapped(c, item["descripcion"], col_x[2], y, 130, FONT_NORMAL, 8, 10)
        c.drawRightString(col_x[3] + 40, y + 10, formatear_guarani(item["precio"]))
        c.drawRightString(col_x[7], y + 10, formatear_guarani(item["total"]))
        y -= 18
        if y < 140:
            c.showPage()
            y = PAGE_HEIGHT - 100

    y -= 5
    c.line(25, y, PAGE_WIDTH - 25, y)
    y -= 18

    c.setFont(FONT_BOLD, 9)
    c.drawRightString(PAGE_WIDTH - 120, y, "SUBTOTAL:")
    c.drawRightString(PAGE_WIDTH - 40, y, formatear_guarani(totales["sub"]))
    y -= 14
    c.drawRightString(PAGE_WIDTH - 120, y, "TOTAL DE LA OPERACIÓN:")
    c.drawRightString(PAGE_WIDTH - 40, y, formatear_guarani(totales["total"]))
    y -= 14
    c.drawRightString(PAGE_WIDTH - 120, y, "TOTAL IVA:")
    c.drawRightString(PAGE_WIDTH - 40, y, formatear_guarani(totales["totiva"]))

    footer_y = 90
    c.setFont(FONT_NORMAL, 7)
    c.drawString(25, footer_y, "Consulte la validez de esta Factura Electrónica con el número de CDC impreso abajo en:")
    c.drawString(25, footer_y - 10, "https://ekuatia.set.gov.py/consultas/")
    c.drawCentredString(PAGE_WIDTH / 2, footer_y - 30, de.get("Id", ""))

    qr_img = generar_qr_code(de.get("Id", ""))
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_size = 60
    c.drawImage(ImageReader(qr_buffer), PAGE_WIDTH / 2 - qr_size / 2, footer_y - 90, width=qr_size, height=qr_size)

    c.save()
    print(f"PDF mejorado generado: {pdf_file}")
    return pdf_file


def formatear_guarani(valor: str) -> str:
    try:
        return f"{int(float(valor)):,}".replace(",", ".")
    except (ValueError, TypeError):
        return valor or "0"


def main():
    print("=" * 60)
    print("GENERADOR DE PDF MEJORADO (DATOS DUMMY)")
    print("=" * 60)
    xml_file = "factura_dummy_mejorado.xml"
    datos = datos_ejemplo()
    datos["dNomEmi"] = "EMPRESA DEMO S.A."
    datos["dRucEm"] = "80012345"
    datos["dDVEmi"] = "7"
    datos["dDirEmi"] = "AV. DEMO 123"
    datos["dDesCiuEmi"] = "ASUNCIÓN"
    datos["dTelEmi"] = "(021) 555000"
    datos["dNomRec"] = "CLIENTE DEMO"
    datos["dRucRec"] = "1234567"
    datos["dDVRec"] = "8"
    generar_factura(datos, xml_file)
    pdf = generar_pdf_mejorado(xml_file)
    print(f"\nPDF listo: {pdf}")


if __name__ == "__main__":
    main()
