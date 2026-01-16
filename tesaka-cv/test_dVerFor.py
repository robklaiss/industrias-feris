#!/usr/bin/env python3

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from lxml import etree

# Read the original file
xml_path = Path("artifacts/last_sent_payload/lote_from_SENT_fixed.xml")
xml_bytes = xml_path.read_bytes()

print("=== ORIGINAL XML ===")
print(xml_bytes.decode('utf-8')[:500])

# Parse with etree
parser = etree.XMLParser(remove_blank_text=False)
root = etree.fromstring(xml_bytes, parser=parser)

print("\n=== PARSED WITH ETREE ===")
print(f"Root tag: {root.tag}")
print(f"First child tag: {root[0].tag if len(root) > 0 else 'No children'}")

# Check if dVerFor is present
rde = root[0]
dVerFor = rde.find("{http://ekuatia.set.gov.py/sifen/xsd}dVerFor")
print(f"dVerFor found: {dVerFor is not None}")
if dVerFor is not None:
    print(f"dVerFor value: {dVerFor.text}")

# Re-serialize
reserialized = etree.tostring(root, encoding='utf-8', xml_declaration=True, pretty_print=False)

print("\n=== RESERIALIZED XML ===")
print(reserialized.decode('utf-8')[:500])

# Check dVerFor after reserialization
root2 = etree.fromstring(reserialized, parser=parser)
rde2 = root2[0]
dVerFor2 = rde2.find("{http://ekuatia.set.gov.py/sifen/xsd}dVerFor")
print(f"\ndVerFor found after reserialization: {dVerFor2 is not None}")
if dVerFor2 is not None:
    print(f"dVerFor value after reserialization: {dVerFor2.text}")
