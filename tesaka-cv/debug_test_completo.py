#!/usr/bin/env python3
"""Debug del test completo"""

import re
import zipfile
import io

# Test con wrapper
xml_con_wrapper = '<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><rDE Id="test"><dVerFor>150</dVerFor></rDE></rLoteDE>'

print("XML original:")
print(xml_con_wrapper)
print()

# Simular la función completa
lote_xml = re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', xml_con_wrapper, flags=re.S)

print(f"¿Empieza con <rLoteDE>? {lote_xml.strip().startswith('<rLoteDE')}")

if lote_xml.strip().startswith('<rLoteDE'):
    # Ya tiene wrapper, solo agregar XML declaration
    payload = '<?xml version="1.0" encoding="UTF-8"?>' + lote_xml
    print("No agregando wrapper extra")
else:
    # CLONAR TIPS: agregar declaration + wrapper extra
    payload = '<?xml version="1.0" encoding="UTF-8"?><rLoteDE>' + lote_xml + '</rLoteDE>'
    print("Agregando wrapper extra")

print("\nPayload final:")
print(payload)
print(f"\nCantidad de <rLoteDE>: {payload.count('<rLoteDE')}")
print(f"Tiene doble wrapper? {'<rLoteDE><rLoteDE' in payload}")
