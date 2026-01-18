#!/usr/bin/env python3
"""Test simple para verificar el fix del doble wrapper"""

import re
import zipfile
import io
from tools.send_sirecepde import build_xde_zip_bytes_from_lote_xml

# Test 1: XML sin wrapper
xml_sin_wrapper = '<rDE Id="test"><dVerFor>150</dVerFor></rDE>'

print("Test 1: XML sin wrapper")
zip_bytes = build_xde_zip_bytes_from_lote_xml(xml_sin_wrapper)

zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
with zf.open('xml_file.xml') as f:
    result = f.read().decode('utf-8')
    
if result.count('<rLoteDE>') == 1:
    print("✅ Test 1 pasado: Se agregó wrapper correctamente")
else:
    print("❌ Test 1 falló")
    print(result[:200])

# Test 2: XML con wrapper
xml_con_wrapper = '<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><rDE Id="test"><dVerFor>150</dVerFor></rDE></rLoteDE>'

print("\nTest 2: XML con wrapper")
zip_bytes = build_xde_zip_bytes_from_lote_xml(xml_con_wrapper)

zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
with zf.open('xml_file.xml') as f:
    result = f.read().decode('utf-8')
    
# Contar las etiquetas de apertura
open_count = result.count('<rLoteDE')
close_count = result.count('</rLoteDE>')
    
if open_count == 1 and close_count == 1:
    print("✅ Test 2 pasado: No se agregó wrapper extra")
else:
    print(f"❌ Test 2 falló: {open_count} apertura, {close_count} cierre")
    print(result[:200])
