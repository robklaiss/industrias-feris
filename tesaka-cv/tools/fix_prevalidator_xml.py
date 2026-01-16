#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from lxml import etree as ET

NS_DS = "http://www.w3.org/2000/09/xmldsig#"


def _local(tag: Optional[str]) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find_signature(root: ET._Element) -> Optional[ET._Element]:
    sig = root.find(".//{%s}Signature" % NS_DS)
    if sig is not None:
        return sig
    matches = root.xpath(".//*[local-name()='Signature' and namespace-uri()=$ds]", ds=NS_DS)  # type: ignore[arg-type]
    return matches[0] if matches else None


def _normalize_text(node: Optional[ET._Element]) -> bool:
    """Return True if whitespace was present before normalization."""
    if node is None or node.text is None:
        return False
    original = node.text
    cleaned = "".join(original.split())
    node.text = cleaned
    return cleaned != original


def fix_signature(root: ET._Element) -> dict:
    report = {
        "root": _local(root.tag),
        "signature_present": False,
        "signature_parent": None,
        "sig_value_whitespace": None,
        "cert_whitespace": None,
    }
    signature = _find_signature(root)
    if signature is None:
        return report

    report["signature_present"] = True
    parent = signature.getparent()
    report["signature_parent"] = _local(parent.tag if parent is not None else None)

    # Force ds prefix
    new_sig = ET.Element(ET.QName(NS_DS, "Signature"), nsmap={"ds": NS_DS})
    for attr, value in signature.items():
        new_sig.set(attr, value)
    new_sig.text = signature.text
    new_sig.tail = signature.tail
    for child in list(signature):
        signature.remove(child)
        new_sig.append(child)

    if parent is not None:
        index = parent.index(signature)
        parent.remove(signature)
        parent.insert(index, new_sig)
        signature = new_sig

    sig_value = signature.find(".//{%s}SignatureValue" % NS_DS)
    cert_value = signature.find(".//{%s}X509Certificate" % NS_DS)
    report["sig_value_whitespace"] = _normalize_text(sig_value)
    report["cert_whitespace"] = _normalize_text(cert_value)

    return report


def process(input_path: Path, output_path: Path) -> dict:
    parser = ET.XMLParser(remove_blank_text=False)
    tree = ET.parse(str(input_path), parser)
    root = tree.getroot()
    report = fix_signature(root)
    tree.write(
        str(output_path),
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=False,
    )
    return report


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Forza ds:Signature y normaliza SignatureValue/X509Certificate para Prevalidador SIFEN."
    )
    parser.add_argument("input", help="XML original")
    parser.add_argument("output", help="XML de salida")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    if not input_path.exists():
        print(f"ERROR: no existe {input_path}", file=sys.stderr)
        return 1

    report = process(input_path, output_path)
    print(f"ROOT={report['root']}")
    print(f"Signature present: {'YES' if report['signature_present'] else 'NO'}")
    print(f"Signature parent: {report['signature_parent'] or 'N/A'}")
    sig_ws = report['sig_value_whitespace']
    cert_ws = report['cert_whitespace']
    if sig_ws is None:
        print("SignatureValue whitespace: N/A (no node)")
    else:
        print(f"SignatureValue whitespace: {'YES' if sig_ws else 'NO'}")
    if cert_ws is None:
        print("X509Certificate whitespace: N/A (no node)")
    else:
        print(f"X509Certificate whitespace: {'YES' if cert_ws else 'NO'}")
    print(f"OUTPUT -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
