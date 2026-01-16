#!/usr/bin/env python3
"""
tools/verify_sig_location.py

Verify that <Signature> is correctly placed inside <DE> (not under <rDE>).
Exit status:
  0 if OK
  1 if FAIL
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS_SIFEN = "http://ekuatia.set.gov.py/sifen/xsd"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"

def _localname(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag

def _namespace(tag):
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else None

def main():
    if len(sys.argv) != 2:
        print("Usage: python -m tools.verify_sig_location <file.xml>")
        sys.exit(2)

    file_path = Path(sys.argv[1])
    if not file_path.is_file():
        print(f"FILE={file_path} (not found)")
        sys.exit(2)

    tree = ET.parse(file_path)
    root = tree.getroot()

    # Find rDE and DE by local-name (namespace-agnostic)
    rde = None
    de = None
    for elem in root.iter():
        ln = _localname(elem.tag)
        if ln == "rDE" and _namespace(elem.tag) == NS_SIFEN:
            rde = elem
        elif ln == "DE" and _namespace(elem.tag) == NS_SIFEN:
            de = elem
        if rde and de:
            break

    if rde is None or de is None:
        print(f"FILE={file_path}")
        print("sig_in_DE=False")
        print("sig_in_rDE=False")
        print("idx_sig=-1")
        print("idx_gCamFuFD=-1")
        print("sig_before_qr=False")
        print("FAIL: missing rDE or DE")
        sys.exit(1)

    sig_in_rde = any(ch for ch in rde if _localname(ch.tag) == "Signature" and _namespace(ch.tag) == NS_DS)
    sig_in_de = any(ch for ch in de if _localname(ch.tag) == "Signature" and _namespace(ch.tag) == NS_DS)

    children_de = list(de)
    idx_sig = -1
    idx_camfufd = -1
    for i, ch in enumerate(children_de):
        ln = _localname(ch.tag)
        ns = _namespace(ch.tag)
        if ln == "Signature" and ns == NS_DS:
            idx_sig = i
        if ln == "gCamFuFD" and ns == NS_SIFEN:
            idx_camfufd = i

    sig_before_qr = (idx_camfufd != -1 and idx_sig != -1 and idx_sig < idx_camfufd)

    print(f"FILE={file_path}")
    print(f"sig_in_DE={sig_in_de}")
    print(f"sig_in_rDE={sig_in_rde}")
    print(f"idx_sig={idx_sig}")
    print(f"idx_gCamFuFD={idx_camfufd}")
    print(f"sig_before_qr={sig_before_qr}")

    ok = sig_in_de and not sig_in_rde and (idx_camfufd == -1 or sig_before_qr)
    if ok:
        print("OK")
        sys.exit(0)
    else:
        print("FAIL")
        sys.exit(1)

if __name__ == "__main__":
    main()
