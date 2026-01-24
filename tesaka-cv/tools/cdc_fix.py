#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Funciones para calcular CDC desde XML y corregir DE@Id.
"""

from lxml import etree
import re
import base64
import zipfile
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple

# Importar función de cálculo de DV
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.cdc_dv import calc_cdc_dv


def local(tag: str) -> str:
    """Extrae el localname de un tag (ignorando namespace)."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def find_text_by_localname(root: ET.Element, localname: str) -> Optional[str]:
    """Busca el primer elemento con el localname dado y retorna su texto."""
    for el in root.iter():
        if local(el.tag) == localname:
            txt = (el.text or "").strip()
            if txt:
                return txt
    return None


def extract_digits(value: Optional[str], width: Optional[int] = None) -> str:
    """Extrae solo dígitos de un valor y opcionalmente hace zero-fill."""
    if value is None:
        return ""
    digits = re.sub(r"\D", "", str(value))
    if width is not None:
        return digits.zfill(width)
    return digits


def _find_first_text_by_localname(root: ET.Element, name: str) -> Optional[str]:
    """Busca el primer elemento por localname y retorna su texto (puede ser vacío)."""
    for el in root.iter():
        if local(el.tag) == name:
            return (el.text or "").strip()
    return None


def normalize_xml_for_de_context(xml_bytes: bytes) -> bytes:
    """
    Normaliza el XML de entrada para que el resto del pipeline siempre opere
    sobre un XML que contenga `<DE>`.

    Soporta:
    - XML directo `<DE>`.
    - Lote `<rLoteDE>` que contiene `<DE>`.
    - SOAP async que contiene `<xDE>` con ZIP(base64) que incluye `lote.xml`.
    """
    # Nota: no llamar recursivamente; esta funcion es el normalizador raiz.
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return xml_bytes

    # Si ya contiene <DE>, no tocar
    for el in root.iter():
        if local(el.tag) == "DE":
            return xml_bytes

    # Intentar extraer xDE (ZIP base64) desde SOAP
    xde_b64 = _find_first_text_by_localname(root, "xDE")
    if not xde_b64:
        return xml_bytes

    try:
        zip_bytes = base64.b64decode(xde_b64)
    except Exception:
        return xml_bytes

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
            names = z.namelist()
            target = None
            for n in names:
                if n.lower().endswith("lote.xml"):
                    target = n
                    break
            if target is None:
                for n in names:
                    if n.lower().endswith(".xml"):
                        target = n
                        break
            if target is None:
                return xml_bytes
            return z.read(target)
    except Exception:
        return xml_bytes


def extract_ruc_dv_from_any_xml(xml_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
    """Extrae (dRucEm, dDVEmi) desde DE/lote o desde SOAP async (xDE)."""
    normalized = normalize_xml_for_de_context(xml_bytes)
    try:
        root = ET.fromstring(normalized)
    except ET.ParseError:
        return (None, None)

    # Buscar primer <DE>
    de = None
    if local(root.tag) == "DE":
        de = root
    else:
        for el in root.iter():
            if local(el.tag) == "DE":
                de = el
                break

    if de is None:
        return (None, None)

    ruc = find_text_by_localname(de, "dRucEm")
    dv = find_text_by_localname(de, "dDVEmi")
    return (ruc, dv)


def assert_ruc_dv_present(xml_bytes: bytes) -> None:
    """Valida que el payload contenga dRucEm y dDVEmi (no vacíos)."""
    ruc, dv = extract_ruc_dv_from_any_xml(xml_bytes)
    if not ruc or not dv:
        raise ValueError(
            "Faltan campos obligatorios del emisor: dRucEm y/o dDVEmi. "
            "Asegurar que el pipeline está construyendo el <DE> correctamente (o que el SOAP xDE incluye lote.xml válido)."
        )


def compute_cdc_from_xml(xml_bytes: bytes) -> str:
    """
    Calcula el CDC desde los campos del XML.
    
    Estructura del CDC (43 dígitos + 1 DV = 44):
    - tipde2: dTipDE o iTipDE (2 dígitos)
    - ruc8: dRucEm (8 dígitos con zero fill)
    - dv1: dDVEmi (1 dígito)
    - est3: dEst (3 dígitos)
    - pun3: dPunExp (3 dígitos)
    - num7: dNumDoc (7 dígitos)
    - fec8: dFeEmiDE (YYYYMMDD desde ISO)
    - tipemi1: iTipEmi (1 dígito)
    - timb8: dNumTim (8 dígitos)
    - codseg1: dCodSeg (tomar último dígito, 1)
    
    Returns:
        CDC completo de 44 dígitos
        
    Raises:
        ValueError: Si falta algún campo requerido
    """
    xml_bytes = normalize_xml_for_de_context(xml_bytes)
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError(f"XML inválido: {e}")
    
    # Buscar <DE>
    de = None
    if local(root.tag) == "DE":
        de = root
    else:
        for el in root.iter():
            if local(el.tag) == "DE":
                de = el
                break
    
    if de is None:
        raise ValueError("No se encontró elemento <DE> en el XML")

    # Candado: RUC y DV del emisor deben existir siempre
    assert_ruc_dv_present(xml_bytes)
    
    # Extraer campos según estructura CDC SIFEN
    # Estructura: tipde2 + ruc8 + dv1 + est3 + pun3 + num7 + tipcont1 + fec8 + tipemi1 + codseg1
    
    # 1) Tipo documento (2 dígitos)
    tipde = find_text_by_localname(de, "iTiDE")
    tipde2 = extract_digits(tipde, 2)
    if len(tipde2) != 2:
        raise ValueError(f"iTiDE debe tener 2 dígitos. Encontrado: {tipde!r}")
    
    # 2) RUC (8 dígitos con zero-fill)
    ruc = find_text_by_localname(de, "dRucEm")
    ruc8 = extract_digits(ruc, 8)
    if len(ruc8) != 8:
        raise ValueError(f"dRucEm debe tener 8 dígitos (con zero-fill). Encontrado: {ruc!r} -> {ruc8}")
    
    # 3) DV RUC (1 dígito)
    dv_ruc = find_text_by_localname(de, "dDVEmi")
    dv1 = extract_digits(dv_ruc, 1)
    if len(dv1) != 1:
        raise ValueError(f"dDVEmi debe tener 1 dígito. Encontrado: {dv_ruc!r}")
    
    # 4) Establecimiento (3 dígitos)
    est = find_text_by_localname(de, "dEst")
    est3 = extract_digits(est, 3)
    if len(est3) != 3:
        raise ValueError(f"dEst debe tener 3 dígitos. Encontrado: {est!r}")
    
    # 5) Punto expedición (3 dígitos)
    pun = find_text_by_localname(de, "dPunExp")
    pun3 = extract_digits(pun, 3)
    if len(pun3) != 3:
        raise ValueError(f"dPunExp debe tener 3 dígitos. Encontrado: {pun!r}")
    
    # 6) Número documento (7 dígitos)
    num = find_text_by_localname(de, "dNumDoc")
    num7 = extract_digits(num, 7)
    if len(num7) != 7:
        raise ValueError(f"dNumDoc debe tener 7 dígitos (con zero-fill). Encontrado: {num!r} -> {num7}")
    
    # 7) Tipo contribuyente (1 dígito) - entre numDoc y fecha
    tipcont = find_text_by_localname(de, "iTipCont") or find_text_by_localname(de, "dTipCont")
    tipcont1 = extract_digits(tipcont, 1)
    
    # Fallback: inferir desde DE@Id si existe
    if len(tipcont1) != 1:
        de_id = de.get("Id", "").strip()
        de_id_digits = re.sub(r"\D", "", de_id)
        if len(de_id_digits) >= 25:
            # tipCont está en posición 24 (índice 24:25)
            tipcont1 = de_id_digits[24:25]
    
    if len(tipcont1) != 1:
        raise ValueError(f"iTipCont debe tener 1 dígito. Encontrado: {tipcont!r}")
    
    # 8) Fecha emisión (8 dígitos YYYYMMDD)
    # Buscar en múltiples tags posibles
    fec = None
    for tag_name in ["dFeEmiDE", "dFecEmiDE", "dFeEmi", "dFecEmi"]:
        fec = find_text_by_localname(de, tag_name)
        if fec:
            break
    
    fec8 = ""
    if fec:
        # Buscar formato ISO: YYYY-MM-DDTHH:MM:SS o YYYY-MM-DD
        # También puede venir como YYYY-MM-DDTHH:MM:SS
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(fec))
        if m:
            fec8 = m.group(1) + m.group(2) + m.group(3)
        else:
            # Intentar YYYYMMDD directo
            digits = extract_digits(fec)
            if len(digits) >= 8:
                fec8 = digits[:8]
    
    # Fallback: inferir desde DE@Id si existe y fec8 no se pudo obtener
    if len(fec8) != 8:
        de_id = de.get("Id", "").strip()
        de_id_digits = re.sub(r"\D", "", de_id)
        if len(de_id_digits) >= 33:
            # fec8 está en posición 25-33 (índice 25:33)
            # Layout: tipDE2(2)+ruc8(8)+dv1(1)+est3(3)+pun3(3)+num7(7)+tipCont1(1)+fec8(8)+...
            # Posiciones: 0-2, 2-10, 10-11, 11-14, 14-17, 17-24, 24-25, 25-33
            fec8 = de_id_digits[25:33]
            if len(fec8) == 8:
                # Validar que sean dígitos válidos (año razonable)
                if fec8.isdigit():
                    year = int(fec8[:4])
                    if 2000 <= year <= 2100:
                        # Parece una fecha válida
                        pass
                    else:
                        # Año fuera de rango, pero usar de todos modos
                        pass
    
    # Validación final: si fec8 no tiene 8 dígitos, abortar
    if len(fec8) != 8:
        de_id = de.get("Id", "").strip()
        de_id_digits = re.sub(r"\D", "", de_id) if de_id else ""
        error_msg = f"No se pudo obtener fec8 (YYYYMMDD). "
        error_msg += f"Buscado en tags: dFeEmiDE, dFecEmiDE, dFeEmi, dFecEmi. "
        error_msg += f"Encontrado en XML: {fec!r}. "
        if de_id:
            error_msg += f"DE@Id disponible: {de_id[:20]}... (len={len(de_id_digits)}). "
            if len(de_id_digits) < 33:
                error_msg += f"DE@Id demasiado corto para extraer fec8 (necesita >= 33 dígitos)."
            else:
                error_msg += f"Extracción desde DE@Id[25:33] falló."
        else:
            error_msg += f"DE@Id no disponible."
        raise ValueError(error_msg)
    
    # 9) Tipo emisión (1 dígito)
    tipemi = find_text_by_localname(de, "iTipEmi")
    tipemi1 = extract_digits(tipemi, 1)
    if len(tipemi1) != 1:
        raise ValueError(f"iTipEmi debe tener 1 dígito. Encontrado: {tipemi!r}")
    
    # 10) Timbrado (8 dígitos)
    timb = find_text_by_localname(de, "dNumTim")
    timb8 = extract_digits(timb, 8)
    if len(timb8) != 8:
        raise ValueError(f"dNumTim debe tener 8 dígitos. Encontrado: {timb!r} -> {timb8}")
    
    # 11) Código seguridad (tomar último dígito)
    codseg = find_text_by_localname(de, "dCodSeg")
    codseg_digits = extract_digits(codseg)
    if not codseg_digits:
        raise ValueError(f"dCodSeg debe contener al menos un dígito. Encontrado: {codseg!r}")
    # Tomar último dígito
    codseg1 = codseg_digits[-1]
    
    # Armar base (43 dígitos)
    # Orden: tipde2 + ruc8 + dv1 + est3 + pun3 + num7 + tipCont1 + fec8 + tipEmi1 + timb8 + codseg1
    base43 = tipde2 + ruc8 + dv1 + est3 + pun3 + num7 + tipcont1 + fec8 + tipemi1 + timb8 + codseg1
    
    if len(base43) != 43:
        # Mensaje de error detallado
        parts = {
            "tipde2": (tipde2, len(tipde2)),
            "ruc8": (ruc8, len(ruc8)),
            "dv1": (dv1, len(dv1)),
            "est3": (est3, len(est3)),
            "pun3": (pun3, len(pun3)),
            "num7": (num7, len(num7)),
            "tipCont1": (tipcont1, len(tipcont1)),
            "fec8": (fec8, len(fec8)),
            "tipEmi1": (tipemi1, len(tipemi1)),
            "timb8": (timb8, len(timb8)),
            "codseg1": (codseg1, len(codseg1)),
        }
        missing = [k for k, (v, l) in parts.items() if l == 0]
        wrong_len = [f"{k}(len={l})" for k, (v, l) in parts.items() if l > 0 and l != int(k[-1])]
        error_msg = f"Base CDC debe tener 43 dígitos. Generado: {len(base43)} dígitos"
        if missing:
            error_msg += f". Campos faltantes: {', '.join(missing)}"
        if wrong_len:
            error_msg += f". Campos con longitud incorrecta: {', '.join(wrong_len)}"
        error_msg += f". Valores parciales: {', '.join(f'{k}={v!r}' for k, (v, l) in parts.items())}"
        raise ValueError(error_msg)
    
    # Calcular DV
    dv = calc_cdc_dv(base43)
    
    # CDC completo (44 dígitos)
    cdc = base43 + str(dv)
    
    return cdc


def set_de_id(xml_bytes: bytes, new_id: str) -> bytes:
    """
    Setea el atributo Id del elemento <DE> en el XML.
    
    Args:
        xml_bytes: XML original (bytes)
        new_id: Nuevo valor para DE@Id
        
    Returns:
        XML modificado (bytes)
        
    Raises:
        ValueError: Si no se encuentra <DE> o el XML es inválido
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError(f"XML inválido: {e}")
    
    # Buscar <DE>
    de = None
    if local(root.tag) == "DE":
        de = root
    else:
        for el in root.iter():
            if local(el.tag) == "DE":
                de = el
                break
    
    if de is None:
        raise ValueError("No se encontró elemento <DE> en el XML")
    
    # Setear Id
    de.set("Id", new_id)
    
    # Serializar de vuelta
    # Preservar encoding y declaración XML si existía
    xml_str = xml_bytes.decode("utf-8", errors="ignore")
    has_decl = xml_str.strip().startswith("<?xml")
    
    # Serializar
    xml_result = ET.tostring(root, encoding="utf-8", xml_declaration=has_decl)
    
    return xml_result


def fix_de_id_in_file(path: str) -> str:
    """
    Lee un archivo XML, calcula el CDC desde sus campos, setea DE@Id y guarda.
    
    Args:
        path: Ruta al archivo XML
        
    Returns:
        CDC final seteado en DE@Id
        
    Raises:
        SystemExit: Si hay error (con código 1)
    """
    xml_path = Path(path)
    
    if not xml_path.exists():
        raise SystemExit(f"❌ Archivo no existe: {xml_path}")
    
    # Leer XML
    try:
        xml_bytes = xml_path.read_bytes()
    except Exception as e:
        raise SystemExit(f"❌ Error al leer archivo: {e}")
    
    # Calcular CDC desde XML
    try:
        cdc = compute_cdc_from_xml(xml_bytes)
    except ValueError as e:
        raise SystemExit(f"❌ Error al calcular CDC desde XML: {e}")
    
    # Validar que el CDC sea válido
    if len(cdc) != 44 or not cdc.isdigit():
        raise SystemExit(f"❌ CDC calculado es inválido: {cdc!r} (debe ser 44 dígitos)")
    
    # Setear DE@Id
    try:
        xml_fixed = set_de_id(xml_bytes, cdc)
    except ValueError as e:
        raise SystemExit(f"❌ Error al setear DE@Id: {e}")
    
    # Verificar que quedó bien seteado
    try:
        root_check = ET.fromstring(xml_fixed)
        de_check = None
        if local(root_check.tag) == "DE":
            de_check = root_check
        else:
            for el in root_check.iter():
                if local(el.tag) == "DE":
                    de_check = el
                    break
        
        if de_check is None:
            raise SystemExit("❌ Error: <DE> desapareció después de setear Id")
        
        id_seteado = de_check.get("Id", "").strip()
        if id_seteado != cdc:
            raise SystemExit(f"❌ Error: DE@Id no quedó seteado correctamente. Esperado: {cdc}, Obtenido: {id_seteado!r}")
        
        # Recalcular CDC desde el XML modificado para verificar consistencia
        try:
            cdc_verif = compute_cdc_from_xml(xml_fixed)
            if cdc_verif != cdc:
                raise SystemExit(f"❌ Inconsistencia: CDC recalculado ({cdc_verif}) != CDC seteado ({cdc})")
        except ValueError as e:
            raise SystemExit(f"❌ Error al verificar CDC después de setear: {e}")
        
    except ET.ParseError as e:
        raise SystemExit(f"❌ XML resultante es inválido: {e}")
    
    # Guardar archivo
    try:
        xml_path.write_bytes(xml_fixed)
    except Exception as e:
        raise SystemExit(f"❌ Error al guardar archivo: {e}")
    
    return cdc

