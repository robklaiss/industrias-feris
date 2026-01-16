from __future__ import annotations

from typing import Tuple, Union

from lxml import etree

from app.sifen_client.xml_generator_v150 import generate_cdc

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"


def _localname(tag: Union[str, bytes]) -> str:
    if isinstance(tag, (str, bytes)):
        text = tag.decode() if isinstance(tag, bytes) else tag
        if "}" in text:
            return text.split("}", 1)[1]
        return text
    return str(tag)


def _find_first(element: etree._Element, localname: str) -> etree._Element:
    nodes = element.xpath(f".//*[local-name()='{localname}']")
    if not nodes:
        raise RuntimeError(f"No se encontró <{localname}> en el DE")
    return nodes[0]


def _get_required_text(element: etree._Element, localname: str) -> str:
    node = _find_first(element, localname)
    text = (node.text or "").strip()
    if not text:
        raise RuntimeError(f"<{localname}> está vacío en el DE")
    return text


def _ensure_de_element(node: etree._Element) -> etree._Element:
    if node is None:
        raise ValueError("Elemento DE inválido (None)")

    if _localname(node.tag) == "DE":
        return node

    if _localname(node.tag) == "rDE":
        de_candidates = node.xpath(".//*[local-name()='DE']")
        if de_candidates:
            return de_candidates[0]
        raise RuntimeError("No se encontró elemento <DE> dentro de <rDE>")

    raise RuntimeError(f"Se esperaba elemento <DE>, llegó: {node.tag}")


def build_cdc_from_de_xml(
    de_element: etree._Element,
) -> Tuple[str, str]:
    """
    Reconstruye el CDC (DE@Id) y su DV a partir de un elemento <DE> ya poblado.

    Args:
        de_element: Elemento <DE> o <rDE> (se seleccionará el primer <DE> interno)

    Returns:
        (cdc, dv) donde:
            cdc: CDC completo de 44 dígitos
            dv: Dígito verificador final (último dígito del CDC)
    """
    de_el = _ensure_de_element(de_element)

    ruc = _get_required_text(de_el, "dRucEm")
    dv_emisor = _get_required_text(de_el, "dDVEmi")
    timbrado = _get_required_text(de_el, "dNumTim")
    establecimiento = _get_required_text(de_el, "dEst")
    punto_exp = _get_required_text(de_el, "dPunExp")
    numero_doc = _get_required_text(de_el, "dNumDoc")
    tipo_doc = _get_required_text(de_el, "iTiDE")
    fecha_emision = _get_required_text(de_el, "dFeEmiDE")

    try:
        total_gs = _get_required_text(de_el, "dTotalGs")
    except RuntimeError:
        total_gs = "0"

    fecha_digits = "".join(ch for ch in fecha_emision if ch.isdigit())[:8]
    if len(fecha_digits) != 8:
        raise RuntimeError(f"dFeEmiDE no tiene formato válido para CDC: {fecha_emision!r}")

    numero_doc_digits = "".join(ch for ch in numero_doc if ch.isdigit())
    if not numero_doc_digits:
        raise RuntimeError("dNumDoc no contiene dígitos")
    numero_doc_formatted = numero_doc_digits.zfill(7)[-7:]

    ruc_formatted = "".join(ch for ch in ruc if ch.isdigit())
    if not ruc_formatted:
        raise RuntimeError("dRucEm inválido para construir CDC")
    ruc_with_dv = f"{ruc_formatted}-{dv_emisor}"

    cdc = generate_cdc(
        ruc=ruc_with_dv,
        timbrado=timbrado,
        establecimiento=establecimiento,
        punto_expedicion=punto_exp,
        numero_documento=numero_doc_formatted,
        tipo_documento=tipo_doc,
        fecha=fecha_digits,
        monto=total_gs or "0",
    )

    if len(cdc) != 44 or not cdc.isdigit():
        raise RuntimeError(f"CDC construido inválido: {cdc!r}")

    return cdc, cdc[-1]
