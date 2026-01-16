#!/usr/bin/env python3

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from lxml import etree

def local_tag(tag):
    """Extract local name from a tag"""
    return tag.split("}", 1)[1] if isinstance(tag, str) and tag.startswith("{") else tag

# Read the original file
xml_path = Path("artifacts/last_sent_payload/lote_from_SENT_fixed.xml")
xml_bytes = xml_path.read_bytes()

# Parse with etree
parser = etree.XMLParser(remove_blank_text=False)
root = etree.fromstring(xml_bytes, parser=parser)

print("=== BEFORE WRAPPING ===")
rde = root[0]
dVerFor = rde.find("{http://ekuatia.set.gov.py/sifen/xsd}dVerFor")
print(f"dVerFor found: {dVerFor is not None}")
if dVerFor is not None:
    print(f"dVerFor value: {dVerFor.text}")
print(f"rDE children before wrapping: {[local_tag(child.tag) for child in rde]}")

# Wrap rDE in xDE (like the code does)
parent = root
child = rde
idx = parent.index(child)
parent.remove(child)
xde_wrapper = etree.Element(etree.QName("http://ekuatia.set.gov.py/sifen/xsd", "xDE"))
xde_wrapper.append(child)
parent.insert(idx, xde_wrapper)

print("\n=== AFTER WRAPPING ===")
# Check the wrapped structure
xde = root[0]  # Now xDE is the first child
rde_wrapped = xde[0]  # rDE is inside xDE
dVerFor_wrapped = rde_wrapped.find("{http://ekuatia.set.gov.py/sifen/xsd}dVerFor")
print(f"dVerFor found after wrapping: {dVerFor_wrapped is not None}")
if dVerFor_wrapped is not None:
    print(f"dVerFor value after wrapping: {dVerFor_wrapped.text}")
print(f"rDE children after wrapping: {[local_tag(child.tag) for child in rde_wrapped]}")

# Re-serialize after wrapping
reserialized = etree.tostring(root, encoding='utf-8', xml_declaration=True, pretty_print=False)

print("\n=== RESERIALIZED AFTER WRAPPING ===")
print(reserialized.decode('utf-8')[:800])

# Final verification
root2 = etree.fromstring(reserialized, parser=parser)
xde2 = root2[0]
rde2 = xde2[0]
dVerFor2 = rde2.find("{http://ekuatia.set.gov.py/sifen/xsd}dVerFor")
print(f"\nFinal dVerFor check: {dVerFor2 is not None}")
if dVerFor2 is not None:
    print(f"Final dVerFor value: {dVerFor2.text}")
    print(f"dVerFor position: {list(rde2).index(dVerFor2)}")
