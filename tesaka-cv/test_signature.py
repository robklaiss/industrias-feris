#!/usr/bin/env python3

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from lxml import etree

# Read the original file
xml_path = Path("artifacts/last_sent_payload/lote_from_SENT_fixed.xml")
xml_bytes = xml_path.read_bytes()

# Parse
parser = etree.XMLParser(remove_blank_text=False)
root = etree.fromstring(xml_bytes, parser)

print("=== Original structure ===")
rde = root[0]
print(f"rDE children: {[child.tag.split('}')[-1] for child in rde]}")

# Find Signature
sig = rde.find("{http://www.w3.org/2000/09/xmldsig#}Signature")
print(f"Signature found: {sig is not None}")

# Wrap in xDE (like the code does)
parent = root
child = rde
idx = parent.index(child)
parent.remove(child)
xde_wrapper = etree.Element(etree.QName("http://ekuatia.set.gov.py/sifen/xsd", "xDE"))
xde_wrapper.append(child)
parent.insert(idx, xde_wrapper)

# Check structure after wrapping
print("\n=== After wrapping ===")
xde = root[0]
rde_wrapped = xde[0]
print(f"rDE children: {[child.tag.split('}')[-1] for child in rde_wrapped]}")

# Check Signature after wrapping
sig_wrapped = rde_wrapped.find("{http://www.w3.org/2000/09/xmldsig#}Signature")
print(f"Signature found after wrapping: {sig_wrapped is not None}")

# Serialize and re-parse to check final structure
final_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True, pretty_print=False)
final_root = etree.fromstring(final_bytes, parser)

print("\n=== After serialization ===")
xde_final = final_root[0]
rde_final = xde_final[0]
print(f"rDE children: {[child.tag.split('}')[-1] for child in rde_final]}")

# Check if Signature is still there
sig_final = rde_final.find("{http://www.w3.org/2000/09/xmldsig#}Signature")
print(f"Signature found after serialization: {sig_final is not None}")

# Check Signature position relative to DE
de_final = rde_final.find("{http://ekuatia.set.gov.py/sifen/xsd}DE")
if de_final is not None and sig_final is not None:
    de_idx = list(rde_final).index(de_final)
    sig_idx = list(rde_final).index(sig_final)
    print(f"DE index: {de_idx}")
    print(f"Signature index: {sig_idx}")
    print(f"Signature after DE: {sig_idx > de_idx}")
