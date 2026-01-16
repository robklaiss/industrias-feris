#!/usr/bin/env python3

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from lxml import etree

# Simulate what the code does
xml_path = Path("artifacts/last_sent_payload/lote_from_SENT_fixed.xml")
xml_bytes = xml_path.read_bytes()

print("=== STEP 1: Read original ===")
print(f"Has dVerFor: {b'<dVerFor>150</dVerFor>' in xml_bytes}")

# Step 2: Parse (like in the code)
parser_detect = etree.XMLParser(remove_blank_text=False)
xml_root_original = etree.fromstring(xml_bytes, parser=parser_detect)
input_is_lote = xml_root_original.tag.endswith('}rLoteDE')

print(f"\n=== STEP 2: Parsed ===")
print(f"Is lote: {input_is_lote}")
print(f"Root tag: {xml_root_original.tag}")

# Step 3: Check structure
lote_root = xml_root_original
rde_nodes = lote_root.xpath(".//*[local-name()='rDE']")
print(f"\n=== STEP 3: Structure check ===")
print(f"Found {len(rde_nodes)} rDE nodes")

# Check first rDE
if rde_nodes:
    rde = rde_nodes[0]
    dVerFor = rde.find("{http://ekuatia.set.gov.py/sifen/xsd}dVerFor")
    print(f"dVerFor in rDE: {dVerFor is not None}")
    if dVerFor is not None:
        print(f"dVerFor value: {dVerFor.text}")
    
    # Check children order
    children = list(rde)
    def local_tag(tag):
        """Extract local name from a tag"""
        if isinstance(tag, str) and tag.startswith("{"):
            return tag.split("}", 1)[1]
        elif hasattr(tag, 'tag'):  # etree element
            return local_tag(tag.tag)
        else:
            return str(tag)
    print(f"rDE children order: {[local_tag(c.tag) for c in children]}")

# Step 4: Check if it needs wrapping
from tools.send_sirecepde import _analyze_lote_structure
structure = _analyze_lote_structure(lote_root)
print(f"\n=== STEP 4: Structure analysis ===")
print(f"Mode: {structure.mode}")
print(f"Direct rDE count: {structure.direct_rde_sifen_count}")
print(f"xDE wrapper count: {structure.xde_wrapper_count}")

# Step 5: Apply wrapping if needed
normalized_lote_root = lote_root
if structure.direct_rde_sifen_count > 0 and structure.xde_wrapper_count == 0:
    print("\n=== STEP 5: Wrapping rDE in xDE ===")
    from tools.send_sirecepde import _wrap_direct_rde_with_xde
    normalized_lote_root = _wrap_direct_rde_with_xde(lote_root)
    
    # Check after wrapping
    xde = normalized_lote_root[0]
    rde_wrapped = xde[0]
    dVerFor_wrapped = rde_wrapped.find("{http://ekuatia.set.gov.py/sifen/xsd}dVerFor")
    print(f"dVerFor after wrapping: {dVerFor_wrapped is not None}")
    if dVerFor_wrapped is not None:
        print(f"dVerFor value after wrapping: {dVerFor_wrapped.text}")
    
    children_wrapped = list(rde_wrapped)
    print(f"rDE children after wrapping: {[local_tag(c.tag) for c in children_wrapped]}")

# Step 6: Serialize (like in the code)
xml_bytes_final = etree.tostring(
    normalized_lote_root,
    xml_declaration=True,
    encoding="utf-8",
    pretty_print=False,
)

print(f"\n=== STEP 6: Final serialization ===")
print(f"Has dVerFor: {b'<dVerFor>150</dVerFor>' in xml_bytes_final}")
print(f"First 500 chars:")
print(xml_bytes_final.decode('utf-8')[:500])
