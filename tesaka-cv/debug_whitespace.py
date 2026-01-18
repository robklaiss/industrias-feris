#!/usr/bin/env python3
"""Debug del trailing whitespace"""

xml = '<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><rDE Id="test"><dVerFor>150</dVerFor></rDE></rLoteDE>  '

print(f"XML original: {repr(xml)}")
print(f"Empieza con <rLoteDE>? {xml.strip().startswith('<rLoteDE')}")
print(f"Después de strip: {repr(xml.strip())}")
