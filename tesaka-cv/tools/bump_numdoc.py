#!/usr/bin/env python3
"""
CLI para mutar dNumDoc/dFeEmiDE en un XML rDE y regenerar el CDC+dDVId.

Uso:
    python -m tools.bump_numdoc --in artifacts/last_lote.xml \
        --out artifacts/last_lote_bump3.xml --numdoc 0000003 --bump-date
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

from lxml import etree

# Agregar repo root al PYTHONPATH para imports locales
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.sifen_client.cdc_builder import build_cdc_from_de_xml

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
NS = {"s": SIFEN_NS}


def _find_first(element: etree._Element, localname: str) -> etree._Element:
    node = element.find(f".//s:{localname}", namespaces=NS)
    if node is None:
        node = element.find(f".//*[local-name()='{localname}']")
    if node is None:
        raise RuntimeError(f"No se encontró <{localname}> en el XML")
    return node


def _ensure_de(root: etree._Element) -> etree._Element:
    if root is None:
        raise RuntimeError("XML vacío, no se encontró elemento raíz")
    if root.tag.endswith("}DE") or root.tag == "DE":
        return root
    de = root.find(".//s:DE", namespaces=NS)
    if de is None:
        de = root.find(".//*[local-name()='DE']")
    if de is None:
        raise RuntimeError("No se encontró elemento <DE> en el XML")
    return de


def bump_numdoc(
    input_path: Path,
    output_path: Path,
    new_numdoc: str,
    bump_date: bool = False,
) -> Path:
    """
    Mutates dNumDoc (and optionally dFeEmiDE) while rebuilding the CDC/dDVId.
    """
    xml_bytes = input_path.read_bytes()
    parser = etree.XMLParser(remove_blank_text=False, recover=False)
    root = etree.fromstring(xml_bytes, parser=parser)

    de_elem = _ensure_de(root)
    gtimb = _find_first(de_elem, "gTimb")
    dnumdoc = _find_first(gtimb, "dNumDoc")

    digits = "".join(ch for ch in str(new_numdoc) if ch.isdigit())
    if not digits:
        raise ValueError("--numdoc debe contener al menos un dígito")
    formatted = digits.zfill(7)[-7:]

    old_numdoc = dnumdoc.text or ""
    dnumdoc.text = formatted

    if bump_date:
        gdat = _find_first(de_elem, "gDatGralOpe")
        dfeemi = _find_first(gdat, "dFeEmiDE")
        now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        dfeemi.text = now_iso

    new_cdc, new_dv = build_cdc_from_de_xml(de_elem)
    old_cdc = de_elem.get("Id") or de_elem.get("id") or ""
    de_elem.set("Id", new_cdc)

    try:
        ddvid = _find_first(de_elem, "dDVId")
    except RuntimeError:
        ddvid = etree.SubElement(de_elem, f"{{{SIFEN_NS}}}dDVId")
    ddvid.text = new_dv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(
        etree.tostring(
            root,
            encoding="UTF-8",
            pretty_print=True,
            xml_declaration=True,
        )
    )

    print("✅ bump_numdoc completado")
    print(f"   Archivo de entrada: {input_path}")
    print(f"   Archivo de salida : {output_path}")
    print(f"   dNumDoc {old_numdoc} -> {formatted}")
    if old_cdc != new_cdc:
        print(f"   CDC {old_cdc or '(vacío)'} -> {new_cdc}")
    else:
        print(f"   CDC sin cambios ({new_cdc})")
    print(f"   dDVId -> {new_dv}")
    if bump_date:
        print("   dFeEmiDE actualizado a NOW")

    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mutar dNumDoc/dFeEmiDE y regenerar CDC")
    parser.add_argument("--in", dest="input", required=True, help="XML rDE origen")
    parser.add_argument("--out", dest="output", required=True, help="XML destino")
    parser.add_argument("--numdoc", required=True, help="Nuevo dNumDoc (7 dígitos, se auto-pad)")
    parser.add_argument("--bump-date", action="store_true", help="Actualizar dFeEmiDE a NOW")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    if not input_path.exists():
        raise FileNotFoundError(f"Archivo de entrada no existe: {input_path}")

    bump_numdoc(
        input_path=input_path,
        output_path=output_path,
        new_numdoc=args.numdoc,
        bump_date=args.bump_date,
    )


if __name__ == "__main__":
    main()
