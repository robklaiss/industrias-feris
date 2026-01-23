#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAFE 0160 loop fixer (NO-REGRESSION):
- Solo toca: XMLs en --artifacts-dir y este script en tools/
- Itera: send -> follow -> parse 0160 -> patch XML -> repeat
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[1]
# === PATCH: sys.path add REPO_ROOT v1 ===
import sys
# Asegurar que el repo root esté en sys.path para poder importar 'app.*'
try:
    _rr = str(REPO_ROOT)
    if _rr not in sys.path:
        sys.path.insert(0, _rr)
except Exception:
    pass



def eprint(*a: Any) -> None:
    print(*a, file=sys.stderr)


def latest_file(dirpath: Path, pattern: str) -> Optional[Path]:
    files = sorted(dirpath.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def find_all_str(d: Any, key: str) -> List[str]:
    out: List[str] = []
    if isinstance(d, dict):
        for k, v in d.items():
            if k == key and isinstance(v, str):
                out.append(v)
            out.extend(find_all_str(v, key))
    elif isinstance(d, list):
        for it in d:
            out.extend(find_all_str(it, key))
    return out


def find_first_str(d: Any, key: str) -> Optional[str]:
    xs = find_all_str(d, key)
    return xs[0] if xs else None


def strip_ns(tag: str) -> str:
    if not isinstance(tag, str):
        return str(tag)
    return tag.split("}", 1)[-1] if "}" in tag else tag


def ns_of(el: etree._Element) -> str:
    if el.tag.startswith("{"):
        return el.tag.split("}", 1)[0][1:]
    return ""


def q(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}" if ns else local


def find_first(el: etree._Element, localname: str) -> Optional[etree._Element]:
    for ch in el.iter():
        if strip_ns(ch.tag) == localname:
            return ch
    return None


def find_all(el: etree._Element, localname: str) -> List[etree._Element]:
    return [ch for ch in el.iter() if strip_ns(ch.tag) == localname]


def run_cmd(cmd: List[str], cwd: Path) -> int:
    eprint("\n$ " + " ".join(cmd))
    p = subprocess.run(cmd, cwd=str(cwd))
    return int(p.returncode)


@dataclass
class LoteStatus:
    dCodResLot: Optional[str]
    dMsgResLot: Optional[str]
    de_cdc: Optional[str]
    de_estado: Optional[str]
    de_cod: Optional[str]
    de_msg: Optional[str]


PROCESSING_KEYWORDS = ("processing", "en procesamiento", "en proceso")


def _join_lower(*parts: Optional[str]) -> str:
    return " ".join(p.strip() for p in parts if p and p.strip()).lower()


def status_contains_0160(st: LoteStatus) -> bool:
    values = (
        st.de_cod,
        st.de_msg,
        st.dCodResLot,
        st.dMsgResLot,
    )
    return any("0160" in (val or "") for val in values)


def is_processing_status(st: LoteStatus) -> bool:
    if st.dCodResLot == "0361":
        return True
    if st.de_cod == "0361":
        return True
    combined = _join_lower(st.dMsgResLot, st.de_estado, st.de_msg)
    return any(keyword in combined for keyword in PROCESSING_KEYWORDS)


def is_lote_concluded(st: LoteStatus) -> bool:
    if st.dCodResLot == "0362":
        return True
    return bool(st.de_cod)


def should_stop_without_0160(st: LoteStatus) -> bool:
    if is_processing_status(st):
        return False
    if not is_lote_concluded(st):
        return False
    return not status_contains_0160(st)


def parse_consulta_lote_json(p: Path) -> LoteStatus:
    data = load_json(p)
    dCodResLot = find_first_str(data, "dCodResLot") or find_first_str(data, "dCodRes")
    dMsgResLot = find_first_str(data, "dMsgResLot") or find_first_str(data, "dMsgRes")

    de_msg = find_first_str(data, "dMsgResDE") or find_first_str(data, "dMsgRes")
    de_cod = find_first_str(data, "dCodResDE") or find_first_str(data, "dCodRes")

    de_cdc = find_first_str(data, "cdc") or find_first_str(data, "dCDC") or find_first_str(data, "id") or None

    de_estado = find_first_str(data, "dEstRes") or find_first_str(data, "estado") or None

    return LoteStatus(
        dCodResLot=dCodResLot,
        dMsgResLot=dMsgResLot,
        de_cdc=de_cdc,
        de_estado=de_estado,
        de_cod=de_cod,
        de_msg=de_msg,
    )


# ---------------- XSD helpers ----------------


def parse_tgTotSub_order(xsd_path: Path) -> List[str]:
    if not xsd_path.exists():
        return []
    tree = etree.parse(str(xsd_path))
    root = tree.getroot()
    nsmap = {"xs": "http://www.w3.org/2001/XMLSchema"}
    ct = root.xpath(".//xs:complexType[@name='tgTotSub']", namespaces=nsmap)
    if not ct:
        return []
    names = ct[0].xpath(".//xs:sequence/xs:element/@name", namespaces=nsmap)
    return [str(n) for n in names]


def all_xsd_enums(xsd_path: Path) -> List[str]:
    if not xsd_path.exists():
        return []
    tree = etree.parse(str(xsd_path))
    xs_ns = "http://www.w3.org/2001/XMLSchema"
    vals = tree.xpath("//xs:enumeration/@value", namespaces={"xs": xs_ns})
    return [str(v) for v in vals if isinstance(v, (str, bytes))]


def normalize_cmp(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().upper()


# ---------------- Fixers ----------------


def fix_dDesUniMed(doc: etree._ElementTree) -> int:
    """
    dDesUniMed inválido => setear a un valor ENUM válido del XSD de unidades.
    Importante: NO forzamos "UNIDAD" porque SIFEN justamente dice que es inválido.
    """

    root = doc.getroot()
    nodes = find_all(root, "dDesUniMed")
    if not nodes:
        return 0

    xsd_units = REPO_ROOT / "schemas_sifen" / "Unidades_Medida_v141.xsd"
    enums = all_xsd_enums(xsd_units)
    enum_set = set(enums)


    # Mapeos conocidos (según docs del repo): cUniMed=77 => dDesUniMed='UNI'
    MAP_BY_CUNIMED = {
        '77': 'UNI',
    }
    if not enums:
        return 0

    changed = 0
    for n in nodes:
        cur = (n.text or "").strip()

        # Si viene numérico o cualquier cosa rara, priorizar mapeo por cUniMed del mismo gItem.
        parent = n.getparent()
        cuni = find_first(parent, "cUniMed") if parent is not None else None
        code = (cuni.text or "").strip() if cuni is not None else ""
        mapped = MAP_BY_CUNIMED.get(code)
        if mapped:
            n.text = mapped
            changed += 1
            continue
        if not cur:
            continue
        if cur in enum_set:
            continue

        curN = normalize_cmp(cur)

        # 1) match exacto normalizado
        best = None
        for e in enums:
            if normalize_cmp(e) == curN:
                best = e
                break

        # 2) si el valor actual contiene algo tipo "UNID", buscar enum que contenga "UNID"
        if best is None and ("UNID" in curN):
            for e in enums:
                if "UNID" in normalize_cmp(e):
                    best = e
                    break

        # 3) fallback: primer enum (mejor que seguir con inválido)
        if best is None:
            best = enums[0]

        n.text = best
        changed += 1

    return changed


def parse_0160_expected_found(msg: str) -> Optional[Tuple[str, str]]:
    """
    Parsea el error 0160 del tipo "XML malformado: El elemento esperado es: <EXPECTED> en lugar de: <FOUND>"
    Retorna (expected, found) o None si no matchea.
    """
    # Regex para capturar expected y found del mensaje
    pattern = r"El elemento esperado es:\s*(\w+)\s*en lugar de:\s*(\w+)"
    match = re.search(pattern, msg, re.IGNORECASE)
    if match:
        return match.group(1), match.group(2)
    return None


def ensure_expected_before_found(xml_path: Path, expected: str, found: str) -> Tuple[Path, bool, Dict[str, Any]]:
    """
    Inserta el elemento EXPECTED antes de FOUND en el mismo parent.
    Reglas de seguridad:
    1. Nunca borra nodos existentes
    2. Solo inserta faltantes o reordena dentro del mismo parent
    3. Mantiene namespaces
    4. No duplica si ya existe
    5. Valor por defecto seguro: "0" para campos dTot*/dPorc*
    """
    debug = {
        "expected": expected,
        "found": found,
        "parent_tag": None,
        "action": None,
        "final_order": []
    }
    
    # Parsear XML
    doc = etree.parse(str(xml_path))
    root = doc.getroot()
    changed = False
    
    # Buscar el primer elemento cuyo localname == found
    found_element = None
    for el in root.iter():
        if strip_ns(el.tag) == found:
            found_element = el
            break
    
    if found_element is None:
        # No se encontró el elemento FOUND
        debug["action"] = "FOUND_NOT_FOUND"
        return xml_path, False, debug
    
    # Tomar el parent
    parent = found_element.getparent()
    if parent is None:
        debug["action"] = "NO_PARENT"
        return xml_path, False, debug
    
    debug["parent_tag"] = strip_ns(parent.tag)
    ns = ns_of(parent)
    
    # Buscar EXPECTED dentro del parent
    expected_element = None
    for ch in parent:
        if strip_ns(ch.tag) == expected:
            expected_element = ch
            break
    
    # Si EXPECTED no existe, crearlo
    if expected_element is None:
        # Determinar valor por defecto seguro
        default_value = "0"
        if expected.startswith("dPorc") or expected.startswith("dTot"):
            default_value = "0"
        
        expected_element = etree.Element(q(ns, expected))
        expected_element.text = default_value
        debug["action"] = "CREATED"
    else:
        debug["action"] = "REORDERED"
    
    # Obtener índice de FOUND
    children = list(parent)
    found_idx = None
    for i, ch in enumerate(children):
        if ch is found_element:
            found_idx = i
            break
    
    if found_idx is None:
        debug["action"] = "FOUND_NOT_IN_PARENT"
        return xml_path, False, debug
    
    # Si EXPECTED no está en el árbol, insertarlo antes de FOUND
    if expected_element.getparent() is None:
        parent.insert(found_idx, expected_element)
        changed = True
    else:
        # Si ya existe pero está después de FOUND, moverlo antes
        current_idx = None
        for i, ch in enumerate(children):
            if ch is expected_element:
                current_idx = i
                break
        
        if current_idx is not None and current_idx > found_idx:
            parent.remove(expected_element)
            # Recalcular índice después de remover
            new_children = list(parent)
            new_found_idx = None
            for i, ch in enumerate(new_children):
                if strip_ns(ch.tag) == found:
                    new_found_idx = i
                    break
            if new_found_idx is not None:
                parent.insert(new_found_idx, expected_element)
                changed = True
                debug["action"] = "MOVED_BEFORE"
    
    # Guardar XML nuevo
    if changed:
        # Generar nombre de archivo con loopfix
        artifacts_dir = xml_path.parent
        base_name = xml_path.stem
        # Extraer número de loop si existe
        loop_match = re.search(r'_loopfix_(\d+)', base_name)
        loop_num = 1
        if loop_match:
            loop_num = int(loop_match.group(1)) + 1
        
        new_name = f"{base_name.rsplit('_loopfix', 1)[0]}_loopfix_{loop_num}_{expected}.xml"
        new_path = artifacts_dir / new_name
        
        doc.write(str(new_path), encoding="utf-8", xml_declaration=True)
        
        # Guardar orden final del gTotSub si aplica
        if strip_ns(parent.tag) == "gTotSub":
            debug["final_order"] = [strip_ns(ch.tag) for ch in parent]
        
        return new_path, True, debug
    
    return xml_path, False, debug


def canonical_gTotSub_order(doc: etree._ElementTree) -> int:
    """
    Reordena los elementos de gTotSub en orden canónico.
    Solo reordena los tags conocidos, dejando los desconocidos al final.
    """
    root = doc.getroot()
    gTotSub = find_first(root, "gTotSub")
    if gTotSub is None:
        return 0
    
    # Orden canónico de gTotSub
    canonical_order = [
        "dSubExe",
        "dSubExo",
        "dSub5",
        "dSub10",
        "dTotOpe",
        "dTotDesc",
        "dTotDescGlotem",
        "dTotAntItem",
        "dTotAnt",
        "dPorcDescTotal",
        "dTotIVA",
        "dTotGralOp",
        "dTotGrav",
        "dTotExe"
    ]
    
    ns = ns_of(gTotSub)
    children = list(gTotSub)
    by_name = {}
    
    # Mapear elementos existentes por nombre
    for ch in children:
        name = strip_ns(ch.tag)
        if name not in by_name:
            by_name[name] = ch
    
    # Crear elementos faltantes con valor "0" si son obligatorios
    changed = 0
    for name in canonical_order:
        if name not in by_name:
            el = etree.Element(q(ns, name))
            el.text = "0"
            by_name[name] = el
            changed += 1
    
    # Construir nuevo orden
    new_children = []
    known_set = set(canonical_order)
    
    # Primero los conocidos en orden canónico
    for name in canonical_order:
        if name in by_name:
            new_children.append(by_name[name])
    
    # Luego los desconocidos (que no estén en la lista canónica)
    unknowns = []
    for ch in children:
        name = strip_ns(ch.tag)
        if name not in known_set and ch not in new_children:
            unknowns.append(ch)
    
    # También agregar desconocidos que se crearon
    for name, el in by_name.items():
        if name not in known_set and el not in unknowns and el not in new_children:
            unknowns.append(el)
    
    new_children.extend(unknowns)
    
    # Aplicar nuevo orden si cambió
    current_order = [strip_ns(ch.tag) for ch in children]
    new_order = [strip_ns(ch.tag) for ch in new_children]
    
    if current_order != new_order:
        # Remover todos y reinsertar en nuevo orden
        for ch in list(gTotSub):
            gTotSub.remove(ch)
        for ch in new_children:
            gTotSub.append(ch)
        changed += 1
    
    return changed


def ensure_gTotSub_order_and_subs(doc: etree._ElementTree) -> int:
    root = doc.getroot()
    gTotSub = find_first(root, "gTotSub")
    if gTotSub is None:
        return 0


    # ensure dSub5/dSub10 cuando hay IVA (SIFEN exige dSub5 antes de dTotIVA)
    # (Valores por defecto: 0 si no hay base imponible)
    _ns = ns_of(gTotSub)
    changed = 0
    if find_first(gTotSub, "dTotIVA") is not None:
        if find_first(gTotSub, "dSub5") is None:
            e = etree.SubElement(gTotSub, f"{{{_ns}}}dSub5")
            e.text = "0"
        if find_first(gTotSub, "dSub10") is None:
            e = etree.SubElement(gTotSub, f"{{{_ns}}}dSub10")
            e.text = "0"

    # ensure dTotOpe cuando hay dTotIVA (SIFEN espera dTotOpe ANTES de dTotIVA)
    iva = find_first(gTotSub, "dTotIVA")
    if iva is not None:
        ope = find_first(gTotSub, "dTotOpe")

        # valor sugerido: dTotGralOp si existe, si no 0
        _tot = find_first(gTotSub, "dTotGralOp")
        val = (_tot.text or "0").strip() if _tot is not None else "0"

        did_change = False

        if ope is None:
            ope = etree.Element(f"{{{_ns}}}dTotOpe")
            ope.text = val
            children = list(gTotSub)
            idx_iva = children.index(iva)
            gTotSub.insert(idx_iva, ope)
            did_change = True
        else:
            # asegurar texto no vacío
            if (ope.text or "").strip() == "":
                ope.text = val
                did_change = True

            # si existe pero está DESPUÉS de dTotIVA, mover antes
            children = list(gTotSub)
            idx_ope = children.index(ope)
            idx_iva = children.index(iva)
            if idx_ope > idx_iva:
                gTotSub.remove(ope)
                children = list(gTotSub)
                idx_iva = children.index(iva)
                gTotSub.insert(idx_iva, ope)
                did_change = True

        if did_change:
            changed += 1

    # ensure dTotDesc cuando hay dTotIVA (SIFEN espera dTotDesc ANTES de dTotIVA)
    # y en la práctica lo valida después de dTotOpe.
    iva = find_first(gTotSub, "dTotIVA")
    if iva is not None:
        desc = find_first(gTotSub, "dTotDesc")
        ope = find_first(gTotSub, "dTotOpe")

        # Valor por defecto: 0 (si no hay descuentos)
        desc_val = (desc.text or "0").strip() if desc is not None else "0"
        if desc is None:
            from lxml import etree
            desc = etree.Element(f"{{{_ns}}}dTotDesc")
            desc.text = desc_val or "0"

        # Colocar dTotDesc antes de dTotIVA y, si existe dTotOpe, después de dTotOpe.
        children = list(gTotSub)
        # Si todavía no está en el árbol (cuando lo creamos arriba), insertarlo.
        if desc.getparent() is None:
            idx_iva = children.index(iva)
            gTotSub.insert(idx_iva, desc)
            changed += 1
            children = list(gTotSub)

        # asegurar texto no vacío
        if (desc.text or "").strip() == "":
            desc.text = "0"
            changed += 1

        # Si dTotDesc quedó después de dTotIVA, mover antes
        children = list(gTotSub)
        idx_desc = children.index(desc)
        idx_iva = children.index(iva)
        if idx_desc > idx_iva:
            gTotSub.remove(desc)
            children = list(gTotSub)
            idx_iva = children.index(iva)
            gTotSub.insert(idx_iva, desc)
            changed += 1

        # Si existe dTotOpe y dTotDesc quedó antes, mover para que quede después de dTotOpe
        if ope is not None:
            children = list(gTotSub)
            idx_ope = children.index(ope)
            idx_desc = children.index(desc)
            if idx_desc < idx_ope:
                gTotSub.remove(desc)
                children = list(gTotSub)
                idx_ope = children.index(ope)
                gTotSub.insert(idx_ope + 1, desc)
                changed += 1

    ns = ns_of(gTotSub)
    existing_children = list(gTotSub)
    by_name: Dict[str, etree._Element] = {}
    for ch in existing_children:
        by_name[strip_ns(ch.tag)] = ch

    def ensure(name: str) -> None:
        nonlocal changed
        if name not in by_name:
            el = etree.Element(q(ns, name))
            el.text = "0"
            by_name[name] = el
            changed += 1

    # según tus mensajes de SIFEN: los está esperando en tu caso
    ensure("dSubExe")
    ensure("dSubExo")

    # Orden esperado de gTotSub (clave para 0160: dTotOpe ANTES de dTotIVA)
    order = [
        "dSubExe",
        "dSubExo",
        "dSub5",
        "dSub10",
        "dTotOpe",
        "dTotDesc",
        "dTotIVA",
        "dTotGralOp",
        "dTotGrav",
        "dTotExe",
    ]

    new_children: List[etree._Element] = []
    for name in order:
        if name in by_name:
            new_children.append(by_name[name])

    known = set(order)
    extras = [ch for ch in existing_children if strip_ns(ch.tag) not in known]
    for name, el in by_name.items():
        if name not in known and el not in extras:
            extras.append(el)

    new_children.extend(extras)

    if [strip_ns(c.tag) for c in list(gTotSub)] != [strip_ns(c.tag) for c in new_children]:
        for ch in list(gTotSub):
            gTotSub.remove(ch)
        for ch in new_children:
            gTotSub.append(ch)
        changed += 1

    return changed


def module_name_from_path(p: Path) -> str:
    rel = p.resolve().relative_to(REPO_ROOT.resolve())
    rel_no_suffix = rel.with_suffix("")
    return ".".join(rel_no_suffix.parts)


def discover_qr_generator() -> Optional[Path]:
    # buscar QRGenerator en .py ignorando venv/cache
    candidates: List[Path] = []
    for p in REPO_ROOT.rglob("*.py"):
        s = str(p)
        if "/.venv/" in s or "/site-packages/" in s or "/__pycache__/" in s:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "QRGenerator" in txt:
            candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda p: (0 if "tools" in p.parts else 1, len(str(p))))
    return candidates[0]


def build_dCarQR_using_repo(xml_path: Path) -> Optional[str]:
    """
    Intenta usar QRGenerator del repo usando import normal (dotted module),
    para que funcionen imports relativos.
    """

    p = discover_qr_generator()
    if not p:
        return None

    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        mod_name = module_name_from_path(p)
        module = importlib.import_module(mod_name)
    except Exception as ex:
        eprint(f"[QR] fallo import módulo {p}: {ex}")
        traceback.print_exc()
        return None

    if not hasattr(module, "QRGenerator"):
        eprint(f"[QR] módulo {p} no expone QRGenerator")
        return None

    QRGen = getattr(module, "QRGenerator")

    try:
        gen = QRGen()
    except Exception:
        gen = QRGen  # por si es API estática

    xml_bytes = xml_path.read_bytes()
    xml_str = xml_bytes.decode("utf-8", errors="ignore")

    for meth in ("generate", "build", "from_xml", "make", "create"):
        if hasattr(gen, meth):
            fn = getattr(gen, meth)
            # probar con path
            try:
                v = fn(str(xml_path))
                if isinstance(v, str) and v.strip():
                    return v.strip()
            except Exception:
                pass
            # probar con xml string
            try:
                v = fn(xml_str)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            except Exception:
                pass

    return None


def ensure_gCamFuFD_and_dCarQR(doc: etree._ElementTree, current_xml_path: Path) -> int:
    root = doc.getroot()
    rde = find_first(root, "rDE")
    if rde is None:
        return 0
    ns = ns_of(rde)

    gCamFuFD = None
    for ch in list(rde):
        if strip_ns(ch.tag) == "gCamFuFD":
            gCamFuFD = ch
            break

    changed = 0
    if gCamFuFD is None:
        gCamFuFD = etree.Element(q(ns, "gCamFuFD"))
        sig = None
        for ch in list(rde):
            if strip_ns(ch.tag) == "Signature":
                sig = ch
                break
        if sig is not None:
            rde.insert(rde.index(sig), gCamFuFD)
        else:
            rde.append(gCamFuFD)
        changed += 1

    dCarQR = None
    for ch in list(gCamFuFD):
        if strip_ns(ch.tag) == "dCarQR":
            dCarQR = ch
            break

    if dCarQR is None:
        dCarQR = etree.Element(q(ns, "dCarQR"))
        gCamFuFD.append(dCarQR)
        changed += 1

    if not (dCarQR.text or "").strip():
        qr = build_dCarQR_using_repo(current_xml_path)
        if qr is None:
            # no rompemos el loop con excepción rara: damos error explícito y salimos
            raise RuntimeError(
                "No pude generar dCarQR automáticamente. "
                "No encontré/ejecuté un QRGenerator compatible en el repo."
            )
        dCarQR.text = qr
        changed += 1

    return changed


# ---------------- Main Loop ----------------


def next_fixed_name(artifacts_dir: Path, base: Path, idx: int) -> Path:
    return artifacts_dir / f"{base.stem}_loopfix_{idx}.xml"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="prod")
    ap.add_argument("--artifacts-dir", required=True)
    ap.add_argument("--xml", required=True)
    ap.add_argument("--max-iter", type=int, default=10)
    ap.add_argument("--poll-every", type=int, default=3, help="Segundos entre consultas cuando está en processing")
    ap.add_argument("--max-poll", type=int, default=40, help="Máximo de consultas cuando está en processing")
    args = ap.parse_args()

    artifacts_dir = Path(args.artifacts_dir).expanduser().resolve()
    in_xml = Path(args.xml).expanduser().resolve()

    py = REPO_ROOT / ".venv" / "bin" / "python"
    send_py = REPO_ROOT / "tools" / "send_sirecepde.py"
    follow_py = REPO_ROOT / "tools" / "follow_lote.py"

    if not artifacts_dir.exists():
        eprint(f"ERROR: artifacts-dir no existe: {artifacts_dir}")
        return 2
    if not in_xml.exists():
        eprint(f"ERROR: xml no existe: {in_xml}")
        return 2
    if not py.exists():
        eprint(f"ERROR: no existe {py}")
        return 2
    if not send_py.exists() or not follow_py.exists():
        eprint("ERROR: faltan tools/send_sirecepde.py o tools/follow_lote.py")
        return 2

    current_xml = in_xml

    for i in range(1, args.max_iter + 1):
        print("\n" + "=" * 60)
        print(f"ITER {i}/{args.max_iter}")
        print(f"XML: {current_xml}")

        rc = run_cmd(
            [
                str(py), str(send_py),
                "--env", args.env,
                "--xml", str(current_xml),
                "--bump-doc", "1",
                "--dump-http",
                "--artifacts-dir", str(artifacts_dir),
                "--iteration", str(i),
            ],
            cwd=REPO_ROOT,
        )
        if rc != 0:
            eprint(f"ERROR: send_sirecepde.py exit={rc}")
            return rc

        resp_json = latest_file(artifacts_dir, "response_recepcion_*.json")
        if resp_json is None:
            eprint("ERROR: no encontré response_recepcion_*.json en ARTDIR")
            return 3

        rc = run_cmd(
            [
                str(py), str(follow_py),
                "--env", args.env,
                "--artifacts-dir", str(artifacts_dir),
                "--once",
                str(resp_json),
            ],
            cwd=REPO_ROOT,
        )
        if rc != 0:
            eprint(f"ERROR: follow_lote.py exit={rc}")
            return rc

        consulta_json = latest_file(artifacts_dir, "consulta_lote_*.json")
        if consulta_json is None:
            eprint("ERROR: no encontré consulta_lote_*.json en ARTDIR")
            return 3

        st = parse_consulta_lote_json(consulta_json)
        print("\n--- LOTE STATUS ---")
        print("dCodResLot:", st.dCodResLot)
        print("dMsgResLot:", st.dMsgResLot)
        print("DE cdc/id:", st.de_cdc)
        print("DE estado :", st.de_estado)
        print("DE codRes :", st.de_cod)
        msg = st.de_msg or ""
        print("DE msgRes :", (msg[:240] + "…") if len(msg) > 240 else msg)

        skip_iter = False
        while True:
            msg = st.de_msg or ""

            if st.de_cod and st.de_cod not in ("0160", "0361"):
                print("\n✅ STOP: ya no es 0160 (de_cod =", st.de_cod, ")")
                return 0

            if is_processing_status(st):
                print(
                    f"\n🔄 Status 0361/processing detectado. Polling cada {args.poll_every}s (máx {args.max_poll} intentos)..."
                )
                poll_count = 0
                while poll_count < args.max_poll:
                    poll_count += 1
                    print(
                        f"  Poll {poll_count}/{args.max_poll}: dCodResLot={st.dCodResLot} msg='{st.dMsgResLot}'"
                    )
                    time.sleep(args.poll_every)

                    rc = run_cmd(
                        [
                            str(py), str(follow_py),
                            "--env", args.env,
                            "--artifacts-dir", str(artifacts_dir),
                            "--once",
                            str(resp_json),
                        ],
                        cwd=REPO_ROOT,
                    )
                    if rc != 0:
                        eprint(f"ERROR: follow_lote.py exit={rc} durante polling")
                        return rc

                    new_consulta_json = latest_file(artifacts_dir, "consulta_lote_*.json")
                    if new_consulta_json is None:
                        eprint("ERROR: no encontré consulta_lote_*.json durante polling")
                        return 3

                    st = parse_consulta_lote_json(new_consulta_json)
                    print(
                        f"    Estado actual: Lote {st.dCodResLot} - {st.dMsgResLot} | DE {st.de_cod} - {st.de_estado}"
                    )

                    if not is_processing_status(st):
                        print(f"    ✅ Cambió de estado a {st.dCodResLot} / {st.de_cod}")
                        break

                if is_processing_status(st):
                    print(
                        f"    ⚠️ Sigue en 0361/processing después de {args.max_poll} intentos. Continuando con siguiente iteración..."
                    )
                    skip_iter = True
                else:
                    continue

            break

        if skip_iter:
            continue

        if should_stop_without_0160(st):
            if st.dCodResLot == "0362":
                print(
                    "\n📦 Lote concluido (0362) sin 0160. Resumen:",
                    f"DE codRes={st.de_cod or '-'} estado={st.de_estado or '-'} msg={(st.de_msg or '')[:160]}",
                )
            print("\n✅ STOP: no veo 0160 en respuesta (cod/msg).")
            return 0

        doc = etree.parse(str(current_xml))
        fixes_applied: List[str] = []

        # Parsear error 0160 para extraer expected/found
        expected_found = parse_0160_expected_found(msg)
        
        # Si detectamos patrón expected/found, aplicar fix genérico
        if expected_found:
            expected, found = expected_found
            print(f"[fix] Insertando '{expected}' antes de '{found}'")
            new_xml_path, changed, debug_info = ensure_expected_before_found(current_xml, expected, found)
            if changed:
                fixes_applied.append(f"Inserted {expected} before {found} in {debug_info.get('parent_tag', 'unknown')}")
                if debug_info.get('final_order'):
                    fixes_applied.append(f"gTotSub order: {debug_info['final_order']}")
                # Usar el nuevo XML retornado por ensure_expected_before_found
                current_xml = new_xml_path
                # Ya no necesitamos escribir de nuevo
                print("\n=== FIX SUMMARY ===")
                print("IN :", current_xml)
                print("OUT:", new_xml_path)
                for fx in fixes_applied:
                    print(" -", fx)
                print("✅ wrote OK")
        
        # Generate fix summary markdown (PIPELINE_CONTRACT section 8)
        fix_summary_file = artifacts_dir / f"fix_summary_{i}.md"
        fix_summary_content = f"""# Fix Summary - Iteration {i}

## Applied Fixes:
{chr(10).join(f"- {fx}" for fx in fixes_applied)}

## Files:
- Input: {current_xml.name}
- Output: {out_xml.name}

## Status:
- dCodRes: {st.de_cod or 'N/A'}
- Message: {st.de_msg[:200] + '...' if st.de_msg and len(st.de_msg) > 200 else st.de_msg or 'N/A'}
"""
        try:
            fix_summary_file.write_text(fix_summary_content, encoding="utf-8")
            print(f"📝 Fix summary saved: {fix_summary_file.name}")
        except Exception as e:
            print(f"⚠️  Warning: Could not write fix summary: {e}")

                continue  # Siguiente iteración
        else:
            # Fixes existentes por mensaje específico
            try:
                if "dDesUniMed" in msg:
                    print("[fix] dDesUniMed")
                    n = fix_dDesUniMed(doc)
                    if n:
                        fixes_applied.append(f"dDesUniMed fixed: {n}")

                if ("dSubExo" in msg) or ("dSubExe" in msg) or ("dTotGralOp" in msg) or ("gTotSub" in msg):
                    print("[fix] gTotSub order/subs")
                    # Aplicar orden canónico primero
                    n = canonical_gTotSub_order(doc)
                    if n:
                        fixes_applied.append(f"gTotSub canonical order: {n}")
                    # Luego asegurar subs
                    n = ensure_gTotSub_order_and_subs(doc)
                    if n:
                        fixes_applied.append(f"gTotSub ensured/order: {n}")

                if ("dCarQR" in msg) or ("gCamFuFD" in msg):
                    print("[fix] gCamFuFD/dCarQR")
                    n = ensure_gCamFuFD_and_dCarQR(doc, current_xml)
                    if n:
                        fixes_applied.append(f"gCamFuFD/dCarQR ensured: {n}")

            except Exception as ex:
                eprint("\nERROR aplicando fixes:", ex)
                traceback.print_exc()
                return 4

            # auto-fix adicional: dTotOpe/dTotIVA
            # Si SIFEN dice que esperaba dTotOpe antes de dTotIVA, aplicamos el fixer de gTotSub.
            if ('dTotOpe en lugar de: dTotIVA' in msg) or ('esperado es: dTotOpe' in msg and 'dTotIVA' in msg):
                fixes_applied.append(('gTotSub order/subs', ensure_gTotSub_order_and_subs))
        if not fixes_applied:
            eprint("\nSTOP: 0160 pero no detecté un fix aplicable con este script.")
            eprint("Mensaje:", msg)
            return 5

        out_xml = next_fixed_name(artifacts_dir, current_xml, i)
        doc.write(str(out_xml), encoding="utf-8", xml_declaration=True)

        print("\n=== FIX SUMMARY ===")
        print("IN :", current_xml)
        print("OUT:", out_xml)
        for fx in fixes_applied:
            print(" -", fx)
        print("✅ wrote OK")

        current_xml = out_xml

    eprint("\nSTOP: alcanzado --max-iter sin salir de 0160.")
    return 6


# === PATCH: QRGenerator direct import v2 (pre-main) ===
# IMPORTANTE: este override va ANTES de ejecutar main(), para reemplazar la función vieja.

def _afix_first_text_anywhere(doc, localname: str):
    root = doc.getroot()
    for el in root.iter():
        if strip_ns(el.tag) == localname:
            t = (el.text or "").strip()
            if t:
                return t
    return ""

def _afix_find_first_el_anywhere(doc, localname: str):
    root = doc.getroot()
    for el in root.iter():
        if strip_ns(el.tag) == localname:
            return el
    return None

def _afix_norm_yyyymmdd(s: str) -> str:
    digits = "".join(ch for ch in (s or "") if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else digits

def _afix_guess_env(current_xml_path) -> str:
    # Respeta el --env del script si existe ENV global, sino heurística por path
    try:
        env = (globals().get("ARGS").env or "").upper()  # si tu script guarda ARGS
        if env:
            return "PROD" if env == "PROD" else "TEST"
    except Exception:
        pass
    s = str(current_xml_path).upper()
    return "PROD" if "PROD" in s else "TEST"

def _afix_extract_qr_fields(doc, current_xml_path):
    de = _afix_find_first_el_anywhere(doc, "DE")
    d_id = ""
    if de is not None:
        d_id = (de.get("Id") or de.get("ID") or "").strip()
    if not d_id:
        d_id = _afix_first_text_anywhere(doc, "Id")

    d_fe_emi = _afix_norm_yyyymmdd(
        _afix_first_text_anywhere(doc, "dFeEmiDE")
        or _afix_first_text_anywhere(doc, "dFeEmi")
        or ""
    )

    d_ruc_em = _afix_first_text_anywhere(doc, "dRucEm") or _afix_first_text_anywhere(doc, "dRUCEm") or ""
    d_dv_emi  = _afix_first_text_anywhere(doc, "dDVEmi") or _afix_first_text_anywhere(doc, "dDVId") or ""

    d_est     = _afix_first_text_anywhere(doc, "dEst")
    d_pun_exp = _afix_first_text_anywhere(doc, "dPunExp")
    d_num_doc = _afix_first_text_anywhere(doc, "dNumDoc")

    d_tipo_doc  = (_afix_first_text_anywhere(doc, "dTipoDoc") or _afix_first_text_anywhere(doc, "iTipDoc") or _afix_first_text_anywhere(doc, "iTipDE") or "1")
    d_tipo_cont = (_afix_first_text_anywhere(doc, "dTipoCont") or _afix_first_text_anywhere(doc, "iTipCont") or "0")
    d_tipo_emi  = (_afix_first_text_anywhere(doc, "dTipoEmi") or _afix_first_text_anywhere(doc, "iTipEmi") or "1")

    d_cod_gen = _afix_first_text_anywhere(doc, "dCodGen") or ""
    d_den_suc = _afix_first_text_anywhere(doc, "dDenSuc") or ""

    env = _afix_guess_env(current_xml_path)

    required = {
        "d_id": d_id,
        "d_fe_emi": d_fe_emi,
        "d_ruc_em": d_ruc_em,
        "d_est": d_est,
        "d_pun_exp": d_pun_exp,
        "d_num_doc": d_num_doc,
    }
    missing = [k for k, v in required.items() if not (v or "").strip()]

    return env, d_id, d_fe_emi, d_ruc_em, d_est, d_pun_exp, d_num_doc, d_tipo_doc, d_tipo_cont, d_tipo_emi, d_cod_gen, d_den_suc, d_dv_emi, missing


def ensure_gCamFuFD_and_dCarQR(doc: etree._ElementTree, current_xml_path: Path) -> int:
    """Override: asegura gCamFuFD y dCarQR y genera QR con app.sifen_client.qr_generator.QRGenerator."""
    root = doc.getroot()

    # ubicar rDE
    rde = None
    for el in root.iter():
        if strip_ns(el.tag) == "rDE":
            rde = el
            break
    if rde is None:
        raise RuntimeError("No encontré <rDE> para insertar gCamFuFD/dCarQR")

    ns = ns_of(rde)

    # asegurar gCamFuFD
    gCamFuFD = None
    for ch in list(rde):
        if strip_ns(ch.tag) == "gCamFuFD":
            gCamFuFD = ch
            break

    inserted = 0
    if gCamFuFD is None:
        gCamFuFD = etree.Element(q(ns, "gCamFuFD"))
        sig = None
        for ch in list(rde):
            if strip_ns(ch.tag) == "Signature":
                sig = ch
                break
        if sig is not None:
            rde.insert(list(rde).index(sig), gCamFuFD)
        else:
            rde.append(gCamFuFD)
        inserted += 1

    # asegurar dCarQR
    dCarQR = None
    for ch in list(gCamFuFD):
        if strip_ns(ch.tag) == "dCarQR":
            dCarQR = ch
            break
    if dCarQR is None:
        dCarQR = etree.Element(q(ns, "dCarQR"))
        gCamFuFD.append(dCarQR)
        inserted += 1

    if not (dCarQR.text or "").strip():
        from app.sifen_client.qr_generator import QRGenerator  # ✅ real

        env, d_id, d_fe_emi, d_ruc_em, d_est, d_pun_exp, d_num_doc, d_tipo_doc, d_tipo_cont, d_tipo_emi, d_cod_gen, d_den_suc, d_dv_emi, missing = _afix_extract_qr_fields(doc, current_xml_path)
        if missing:
            raise RuntimeError("No pude generar dCarQR: faltan campos para QRGenerator: " + ", ".join(missing))

        qrg = QRGenerator(environment=env)  # CSC/CSC_ID desde env vars
        res = qrg.generate(
            d_id=d_id,
            d_fe_emi=d_fe_emi,
            d_ruc_em=d_ruc_em,
            d_est=d_est,
            d_pun_exp=d_pun_exp,
            d_num_doc=d_num_doc,
            d_tipo_doc=d_tipo_doc,
            d_tipo_cont=d_tipo_cont,
            d_tipo_emi=d_tipo_emi,
            d_cod_gen=d_cod_gen,
            d_den_suc=d_den_suc,
            d_dv_emi=d_dv_emi,
        )

        dCarQR.text = res.get("url_xml") or res.get("url") or ""
        if not dCarQR.text:
            raise RuntimeError("QRGenerator devolvió vacío (sin url/url_xml)")

        inserted += 1

    return inserted
# === END PATCH v2 ===



if __name__ == "__main__":
    raise SystemExit(main())


# === PATCH: QRGenerator direct import v1 ===
# Objetivo: generar dCarQR usando el QRGenerator real del repo:
#   app.sifen_client.qr_generator.QRGenerator
# Evita heurísticas de búsqueda/importlib raras.

def _first_text_anywhere(doc, localname: str):
    root = doc.getroot()
    for el in root.iter():
        if strip_ns(el.tag) == localname:
            t = (el.text or "").strip()
            if t:
                return t
    return ""

def _find_first_el_anywhere(doc, localname: str):
    root = doc.getroot()
    for el in root.iter():
        if strip_ns(el.tag) == localname:
            return el
    return None

def _normalize_yyyymmdd(s: str) -> str:
    digits = "".join(ch for ch in (s or "") if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else digits

def _guess_env_from_paths(current_xml_path) -> str:
    s = str(current_xml_path).upper()
    return "PROD" if "PROD" in s else "TEST"

def _extract_qr_fields_from_doc(doc, current_xml_path):
    # DE Id (CDC) suele estar como atributo Id en <DE>
    de = _find_first_el_anywhere(doc, "DE")
    d_id = ""
    if de is not None:
        d_id = (de.get("Id") or de.get("ID") or "").strip()
    if not d_id:
        d_id = _first_text_anywhere(doc, "Id")

    d_fe_emi = _normalize_yyyymmdd(
        _first_text_anywhere(doc, "dFeEmiDE")
        or _first_text_anywhere(doc, "dFeEmi")
        or ""
    )

    d_ruc_em = _first_text_anywhere(doc, "dRucEm") or _first_text_anywhere(doc, "dRUCEm") or ""
    d_dv_emi  = _first_text_anywhere(doc, "dDVEmi") or _first_text_anywhere(doc, "dDVId") or ""

    d_est     = _first_text_anywhere(doc, "dEst")
    d_pun_exp = _first_text_anywhere(doc, "dPunExp")
    d_num_doc = _first_text_anywhere(doc, "dNumDoc")

    d_tipo_doc  = (_first_text_anywhere(doc, "dTipoDoc") or _first_text_anywhere(doc, "iTipDoc") or _first_text_anywhere(doc, "iTipDE") or "1")
    d_tipo_cont = (_first_text_anywhere(doc, "dTipoCont") or _first_text_anywhere(doc, "iTipCont") or "0")
    d_tipo_emi  = (_first_text_anywhere(doc, "dTipoEmi") or _first_text_anywhere(doc, "iTipEmi") or "1")

    d_cod_gen = _first_text_anywhere(doc, "dCodGen") or ""
    d_den_suc = _first_text_anywhere(doc, "dDenSuc") or ""

    env = _guess_env_from_paths(current_xml_path)

    required = {
        "d_id": d_id,
        "d_fe_emi": d_fe_emi,
        "d_ruc_em": d_ruc_em,
        "d_est": d_est,
        "d_pun_exp": d_pun_exp,
        "d_num_doc": d_num_doc,
    }
    missing = [k for k, v in required.items() if not (v or "").strip()]

    return env, d_id, d_fe_emi, d_ruc_em, d_est, d_pun_exp, d_num_doc, d_tipo_doc, d_tipo_cont, d_tipo_emi, d_cod_gen, d_den_suc, d_dv_emi, missing


def ensure_gCamFuFD_and_dCarQR(doc: etree._ElementTree, current_xml_path: Path) -> int:
    """Override: asegura gCamFuFD y dCarQR y genera QR con QRGenerator real."""
    root = doc.getroot()

    # ubicar rDE
    rde = None
    for el in root.iter():
        if strip_ns(el.tag) == "rDE":
            rde = el
            break
    if rde is None:
        raise RuntimeError("No encontré <rDE> para insertar gCamFuFD/dCarQR")

    ns = ns_of(rde)

    # asegurar gCamFuFD
    gCamFuFD = None
    for ch in list(rde):
        if strip_ns(ch.tag) == "gCamFuFD":
            gCamFuFD = ch
            break
    inserted = 0
    if gCamFuFD is None:
        gCamFuFD = etree.Element(q(ns, "gCamFuFD"))
        # antes de Signature si existe
        sig = None
        for ch in list(rde):
            if strip_ns(ch.tag) == "Signature":
                sig = ch
                break
        if sig is not None:
            rde.insert(list(rde).index(sig), gCamFuFD)
        else:
            rde.append(gCamFuFD)
        inserted += 1

    # asegurar dCarQR
    dCarQR = None
    for ch in list(gCamFuFD):
        if strip_ns(ch.tag) == "dCarQR":
            dCarQR = ch
            break
    if dCarQR is None:
        dCarQR = etree.Element(q(ns, "dCarQR"))
        gCamFuFD.append(dCarQR)
        inserted += 1

    # generar si vacío
    if not (dCarQR.text or "").strip():
        try:
            from app.sifen_client.qr_generator import QRGenerator
        except Exception as e:
            raise RuntimeError(f"No pude importar QRGenerator real: {e}")

        env, d_id, d_fe_emi, d_ruc_em, d_est, d_pun_exp, d_num_doc, d_tipo_doc, d_tipo_cont, d_tipo_emi, d_cod_gen, d_den_suc, d_dv_emi, missing = _extract_qr_fields_from_doc(doc, current_xml_path)
        if missing:
            raise RuntimeError("No pude generar dCarQR: faltan campos para QRGenerator: " + ", ".join(missing))

        qrg = QRGenerator(environment=env)  # CSC/CSC_ID desde env vars
        res = qrg.generate(
            d_id=d_id,
            d_fe_emi=d_fe_emi,
            d_ruc_em=d_ruc_em,
            d_est=d_est,
            d_pun_exp=d_pun_exp,
            d_num_doc=d_num_doc,
            d_tipo_doc=d_tipo_doc,
            d_tipo_cont=d_tipo_cont,
            d_tipo_emi=d_tipo_emi,
            d_cod_gen=d_cod_gen,
            d_den_suc=d_den_suc,
            d_dv_emi=d_dv_emi,
        )

        dCarQR.text = res.get("url_xml") or res.get("url") or ""
        if not dCarQR.text:
            raise RuntimeError("QRGenerator devolvió vacío (sin url/url_xml)")

        inserted += 1

    return inserted