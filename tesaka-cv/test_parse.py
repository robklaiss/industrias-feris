#!/usr/bin/env python3

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from lxml import etree

# Test parsing the exact same way
xml_path = Path("artifacts/last_sent_payload/lote_from_SENT_fixed.xml")
xml_bytes = xml_path.read_bytes()

print("Testing XML parsing...")
try:
    parser_detect = etree.XMLParser(remove_blank_text=False)
    xml_root_original = etree.fromstring(xml_bytes, parser=parser_detect)
    print("✅ Parsing successful")
    
    # Check if it's a lote
    def local_tag(tag):
        return tag.split("}", 1)[1] if isinstance(tag, str) and tag.startswith("{") else tag
    
    input_is_lote = local_tag(xml_root_original.tag) == "rLoteDE"
    print(f"Is lote: {input_is_lote}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print(f"Error type: {type(e)}")
    import traceback
    traceback.print_exc()
