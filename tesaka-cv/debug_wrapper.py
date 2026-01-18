#!/usr/bin/env python3
"""Debug del wrapper fix"""

import re

# Test con wrapper
xml_con_wrapper = '<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><rDE Id="test"><dVerFor>150</dVerFor></rDE></rLoteDE>'

print("XML original:")
print(xml_con_wrapper)
print()

# Simular la función
lote_xml = re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', xml_con_wrapper, flags=re.S)
print("Después de quitar XML declaration:")
print(lote_xml)
print()

print(f"¿Empieza con <rLoteDE>? {lote_xml.strip().startswith('<rLoteDE')}")
print(f"Primeros 50 chars: {lote_xml[:50]}")

# Verificar si hay espacios o newlines
print(f"Repr: {repr(lote_xml[:50])}")
