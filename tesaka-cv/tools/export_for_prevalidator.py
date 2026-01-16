#!/usr/bin/env python3
"""Normaliza rDE+Signature para el prevalidador oficial de SIFEN."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional

from lxml import etree as ET

NS_SIFEN = "http://ekuatia.set.gov.py/sifen/xsd"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
OUT_STD = Path("/tmp/preval_rDE_std.xml")
OUT_RDE = Path("/tmp/preval_rDE.xml")
OUT_DE = Path("/tmp/preval_DE.xml")


def _local(tag: Optional[str]) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse_xml(path: Path) -> ET._ElementTree:
    parser = ET.XMLParser(remove_blank_text=False)
    return ET.parse(str(path), parser)


def _first_by_local(root: ET._Element, local: str) -> Optional[ET._Element]:
    if _local(root.tag) == local:
        return root
    nodes = root.xpath(
        f".//*[local-name()='{local}' and namespace-uri()='{NS_SIFEN}']",
    )
    return nodes[0] if nodes else None


def _clone(elem: ET._Element) -> ET._Element:
    return ET.fromstring(ET.tostring(elem))


def _find_signature(root: ET._Element) -> Optional[ET._Element]:
    sig_nodes = root.xpath(
        ".//*[local-name()='Signature' and namespace-uri()=$ns]",
        ns=NS_DS,
    )
    return sig_nodes[0] if sig_nodes else None


def _locate_rde(root: ET._Element) -> ET._Element:
    local = _local(root.tag)
    if local == "rDE":
        return root
    if local == "rEnviDe":
        rde = _first_by_local(root, "rDE")
        if rde is None:
            raise ValueError("rEnviDe no contiene rDE")
        return rde
    if local == "DE":
        raise ValueError("El archivo contiene solo DE; se requiere rDE completo")
    rde = _first_by_local(root, "rDE")
    if rde is None:
        raise ValueError("No se encontró rDE en el XML")
    return rde


def _force_signature_default_ns(sig: ET._Element) -> ET._Element:
    if sig.tag == f"{{{NS_DS}}}Signature" and sig.nsmap.get(None) == NS_DS:
        return sig
    parent = sig.getparent()
    if parent is None:
        return sig
    new_sig = ET.Element(ET.QName(NS_DS, "Signature"), nsmap={None: NS_DS})
    for k, v in sig.attrib.items():
        new_sig.set(k, v)
    new_sig.text = sig.text
    new_sig.tail = sig.tail
    for child in list(sig):
        sig.remove(child)
        new_sig.append(child)
    parent.replace(sig, new_sig)
    return new_sig


def export(input_path: Path) -> Path:
    tree = _parse_xml(input_path)
    root = tree.getroot()

    rde_source = _locate_rde(root)
    rde_export = _clone(rde_source)

    de_node = _first_by_local(rde_export, "DE")
    if de_node is None:
        raise ValueError("rDE exportado no contiene DE")

    sig_node = _find_signature(rde_export)
    if sig_node is None:
        raise ValueError("No se encontró Signature en el XML")

    sig_node = _force_signature_default_ns(sig_node)

    parent_local = _local(sig_node.getparent().tag if sig_node.getparent() is not None else None)
    if parent_local == "DE":
        sig_node.getparent().remove(sig_node)
        rde_children = list(rde_export)
        try:
            idx_de = rde_children.index(de_node)
        except ValueError:
            raise ValueError("No se pudo localizar DE dentro de rDE exportado")
        rde_export.insert(idx_de + 1, sig_node)
    elif parent_local == "rDE":
        rde_children = list(rde_export)
        try:
            idx_de = rde_children.index(de_node)
            idx_sig = rde_children.index(sig_node)
        except ValueError:
            raise ValueError("No se pudo evaluar posiciones de Signature/DE")
        if idx_sig != idx_de + 1:
            rde_export.remove(sig_node)
            rde_export.insert(idx_de + 1, sig_node)
    else:
        raise ValueError("Signature no está bajo DE ni rDE")

    def _write(path: Path, element: ET._Element) -> None:
        ET.ElementTree(element).write(
            str(path),
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True,
        )

    _write(OUT_STD, rde_export)
    print(f"WROTE {OUT_STD}")

    # Compat copies for tooling that espera los nombres históricos
    _write(OUT_RDE, ET.fromstring(ET.tostring(rde_export)))
    print(f"WROTE {OUT_RDE}")

    _write(OUT_DE, ET.fromstring(ET.tostring(rde_export)))
    print(f"WROTE {OUT_DE}")

    return OUT_STD


def _verify(path: Path) -> int:
    print(f"---- VERIFY {path} ----")
    proc = subprocess.run(
        [sys.executable, "-m", "tools.verify_sig_location", str(path)],
        check=False,
    )
    return proc.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Export XML for prevalidador")
    parser.add_argument("input", type=Path, help="Signed XML path")
    args = parser.parse_args()

    out_path = export(args.input)
    if _verify(out_path) != 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
