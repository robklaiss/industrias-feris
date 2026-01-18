#!/usr/bin/env python3
"""Generate a test XML with the real RUC"""

import sys
sys.path.insert(0, 'tesaka-cv')

from pathlib import Path
import xml.etree.ElementTree as ET

# Load the original XML
xml_path = Path('tesaka-cv/../artifacts/de_20260109_180059.xml')
tree = ET.parse(xml_path)
root = root = tree.getroot()

# Update the RUC in the XML
ruc_emisor = root.find('.//{http://ekuatia.set.gov.py/sifen/xsd}dRucEm')
if ruc_emisor is not None:
    ruc_emisor.text = '4554737'
    print("Updated dRucEm to 4554737")

# Update DV if needed
dv_emisor = root.find('.//{http://ekuatia.set.gov.py/sifen/xsd}dDVEmi')
if dv_emisor is not None:
    dv_emisor.text = '8'
    print("Updated dDVEmi to 8")

# Update recipient RUC too
ruc_rec = root.find('.//{http://ekuatia.set.gov.py/sifen/xsd}dRucRec')
if ruc_rec is not None:
    ruc_rec.text = '4554737'
    print("Updated dRucRec to 4554737")

# Update recipient DV
dv_rec = root.find('.//{http://ekuatia.set.gov.py/sifen/xsd}dDVRec')
if dv_rec is not None:
    dv_rec.text = '8'
    print("Updated dDVRec to 8")

# Save the new XML
output_path = Path('tesaka-cv/../artifacts/de_test_real_ruc.xml')
tree.write(output_path, encoding='UTF-8', xml_declaration=True)
print(f"\nSaved new XML to: {output_path}")
