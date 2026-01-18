#!/usr/bin/env python3
"""Debug de la estructura XML"""

import re
from lxml import etree

# Leer XML
with open('lote_completo.xml', 'r') as f:
    xml_content = f.read()

# Quitar XML declaration
xml_sin_decl = re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', xml_content)

# Parsear
root = etree.fromstring(xml_sin_decl)

print("Root tag:", root.tag)
print("Root xmlns:", root.get('xmlns'))

# Listar todos los elementos hijos
print("\nHijos del root:")
for i, child in enumerate(root):
    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
    print(f"  {i}: {tag}")

# Si el primer hijo es rDE, listar sus hijos
if len(root) > 0:
    first_child = root[0]
    if 'rDE' in first_child.tag:
        print("\nHijos de rDE:")
        for i, child in enumerate(first_child):
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            print(f"  {i}: {tag}")
            if tag == 'Signature':
                print(f"    xmlns: {child.get('xmlns')}")
