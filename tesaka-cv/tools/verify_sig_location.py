#!/usr/bin/env python3
"""
tools/verify_sig_location.py

Verify that <Signature> is correctly placed inside <DE> (not under <rDE>).
Exit status:
  0 if OK
  1 if FAIL
"""

import sys
from pathlib import Path
from typing import Optional

from lxml import etree as ET

NS_SIFEN = "http://ekuatia.set.gov.py/sifen/xsd"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"


def _local(tag: Optional[str]) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _first_descendant_by_local(
    parent: Optional[ET._Element], local: str
) -> Optional[ET._Element]:
    if parent is None:
        return None
    matches = parent.xpath(f".//*[local-name()='{local}']")
    return matches[0] if matches else None


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m tools.verify_sig_location <file.xml>")
        sys.exit(2)

    file_path = Path(sys.argv[1])
    if not file_path.is_file():
        print(f"FILE={file_path} (not found)")
        sys.exit(2)

    tree = ET.parse(str(file_path))
    root = tree.getroot()
    root_local = _local(root.tag)

    rde_node: Optional[ET._Element] = None
    de_node: Optional[ET._Element] = None

    if root_local == "rEnviDe":
        rde_node = _first_descendant_by_local(root, "rDE")
        de_node = _first_descendant_by_local(root, "DE")
    elif root_local == "rDE":
        rde_node = root
        de_node = _first_descendant_by_local(root, "DE")
    elif root_local == "DE":
        de_node = root
    else:
        rde_node = _first_descendant_by_local(root, "rDE")
        de_node = _first_descendant_by_local(root, "DE")

    sig_nodes = root.xpath(
        ".//*[local-name()='Signature' and namespace-uri()=$ns]",
        ns=NS_DS,
    )
    sig_node = sig_nodes[0] if sig_nodes else None
    sig_parent = sig_node.getparent() if sig_node is not None else None

    sig_in_de = sig_node is not None and de_node is not None and sig_parent is de_node
    sig_in_rde = sig_node is not None and rde_node is not None and sig_parent is rde_node

    idx_sig = -1
    idx_gcam = -1
    children_de = list(de_node) if de_node is not None else []
    if de_node is not None and sig_node is not None:
        for idx, child in enumerate(children_de):
            if child is sig_node and idx_sig == -1:
                idx_sig = idx
            if _local(child.tag) == "gCamFuFD" and idx_gcam == -1:
                idx_gcam = idx

    print(f"FILE={file_path}")
    print(f"root_local={root_local or 'UNKNOWN'}")
    print(f"sig_parent_local={_local(sig_parent.tag) if sig_parent is not None else 'None'}")
    print(f"sig_in_DE={sig_in_de}")
    print(f"sig_in_rDE={sig_in_rde}")

    fail_reason = None
    if de_node is None:
        fail_reason = "missing DE"
    elif sig_node is None:
        fail_reason = "missing Signature"
    else:
        if sig_in_de:
            if idx_gcam != -1 and idx_sig != idx_gcam - 1:
                fail_reason = "Signature must be immediately before gCamFuFD"
        elif sig_in_rde:
            if rde_node is None:
                fail_reason = "rDE not found"
            else:
                rde_children = list(rde_node)
                try:
                    idx_de_in_rde = rde_children.index(de_node)
                    idx_sig_in_rde = rde_children.index(sig_node)
                    if idx_sig_in_rde != idx_de_in_rde + 1:
                        fail_reason = "Signature under rDE must be immediately after DE"
                except ValueError:
                    fail_reason = "Unable to determine positions under rDE"
        else:
            fail_reason = "Signature must be child of DE or rDE"

    if fail_reason is None:
        print("OK")
        sys.exit(0)
    else:
        print(f"FAIL: {fail_reason}")
        sys.exit(1)

if __name__ == "__main__":
    main()
