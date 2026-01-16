#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from lxml import etree

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
NS = {"s": SIFEN_NS, "ds": DS_NS}

def normalize_signature_under_rde(xml_bytes: bytes) -> bytes:
    root = etree.fromstring(xml_bytes)

    # encontrar rDE (puede ser root directo)
    rde = root if root.tag == f"{{{SIFEN_NS}}}rDE" else root.xpath("//s:rDE", namespaces=NS)[0]

    sigs = rde.xpath(".//ds:Signature", namespaces=NS)
    if not sigs:
        return xml_bytes
    sig = sigs[0]
    parent = sig.getparent()

    # DE hijo directo de rDE
    de = rde.find(f"{{{SIFEN_NS}}}DE")
    if de is None:
        return xml_bytes

    # si Signature está dentro de DE => mover
    if parent is de or de in sig.iterancestors():
        # detach
        parent.remove(sig)
        # insert después de DE
        kids = list(rde)
        de_idx = kids.index(de)
        rde.insert(de_idx + 1, sig)

    return etree.tostring(rde, xml_declaration=True, encoding="UTF-8")

def inspect(xml_bytes: bytes) -> None:
    root = etree.fromstring(xml_bytes)
    rde = root if root.tag == f"{{{SIFEN_NS}}}rDE" else root.xpath("//s:rDE", namespaces=NS)[0]
    sigs = rde.xpath(".//ds:Signature", namespaces=NS)
    print("Signature count:", len(sigs))
    if sigs:
        print("Signature parent:", sigs[0].getparent().tag)
    print("rDE children order:", [c.tag for c in list(rde)])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml_in", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--inspect-only", action="store_true")
    args = ap.parse_args()

    if not args.xml_in.exists():
        print(f"ERROR: Archivo no encontrado: {args.xml_in}")
        return

    with open(args.xml_in, "rb") as f:
        data = f.read()

    if args.inspect_only:
        inspect(data)
        return

    fixed = normalize_signature_under_rde(data)
    inspect(fixed)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "wb") as f:
            f.write(fixed)
        print("OK ->", args.out)

if __name__ == "__main__":
    main()
