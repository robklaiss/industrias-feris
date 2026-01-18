#!/usr/bin/env python3
"""
Script para probar el fix de whitespace en XML SIFEN
"""

import os
import sys
import tempfile
from pathlib import Path

# Agregar el path del proyecto
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "tesaka-cv"))

from app.sifen_client.xmlsec_signer_clean import _clean_xml_whitespace, sign_de_with_p12_clean

def test_whitespace_cleaning():
    """Prueba la limpieza de whitespace"""
    
    # XML de ejemplo con whitespace
    xml_with_whitespace = b'''<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE>
        <dVerFor>150</dVerFor>
        <DE Id="123">
            <dDVId>1</dDVId>
            <dFecFirma>2026-01-17T14:00:00</dFecFirma>
        </DE>
    </rDE>
</rLoteDE>'''
    
    print("=== XML ANTES DE LIMPIAR ===")
    print(xml_with_whitespace.decode())
    
    print("\n=== LIMPIANDO WHITESPACE ===")
    cleaned = _clean_xml_whitespace(xml_with_whitespace)
    
    print("=== XML DESPUÉS DE LIMPIAR ===")
    print(cleaned.decode())
    
    # Verificar que no hay whitespace
    if b'\n' not in cleaned and b'\t' not in cleaned:
        print("\n✅ ÉXITO: XML sin whitespace")
    else:
        print("\n❌ ERROR: XML aún contiene whitespace")
    
    # Contar nodos de texto vacíos
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(cleaned)
        empty_text_nodes = 0
        for elem in root.iter():
            if elem.text and elem.text.strip() == '':
                empty_text_nodes += 1
        print(f"Nodos de texto vacíos: {empty_text_nodes}")
    except Exception as e:
        print(f"Error verificando nodos: {e}")

def test_sign_with_clean():
    """Prueba la firma con limpieza de whitespace"""
    
    # Buscar un XML de prueba
    xml_path = Path("artifacts/last_lote.xml")
    if not xml_path.exists():
        print(f"❌ No existe archivo de prueba: {xml_path}")
        return
    
    print(f"\n=== PROBANDO FIRMA CON XML: {xml_path} ===")
    
    # Leer XML
    xml_bytes = xml_path.read_bytes()
    
    # Verificar si tiene whitespace
    has_newlines = b'\n' in xml_bytes
    has_tabs = b'\t' in xml_bytes
    print(f"XML original tiene \\n: {has_newlines}")
    print(f"XML original tiene \\t: {has_tabs}")
    
    # Buscar certificado
    cert_path = os.getenv("SIFEN_CERT_PATH")
    cert_password = os.getenv("SIFEN_CERT_PASSWORD")
    
    if not cert_path or not cert_password:
        print("❌ Configure SIFEN_CERT_PATH y SIFEN_CERT_PASSWORD")
        return
    
    if not Path(cert_path).exists():
        print(f"❌ No existe certificado: {cert_path}")
        return
    
    try:
        # Firmar con limpieza
        print("\nFirmando con limpieza de whitespace...")
        signed = sign_de_with_p12_clean(xml_bytes, cert_path, cert_password)
        
        # Guardar resultado
        output_path = Path("artifacts/lote_signed_clean.xml")
        output_path.write_bytes(signed)
        print(f"✅ XML firmado guardado en: {output_path}")
        
        # Verificar que no hay whitespace
        has_newlines_after = b'\n' in signed
        has_tabs_after = b'\t' in signed
        print(f"\nXML firmado tiene \\n: {has_newlines_after}")
        print(f"XML firmado tiene \\t: {has_tabs_after}")
        
        # Verificar firma
        print("\nVerificando firma con xmlsec...")
        import subprocess
        result = subprocess.run(
            ["xmlsec1", "--verify", "--insecure", "--id-attr:Id", "DE", str(output_path)],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Firma válida")
        else:
            print(f"❌ Firma inválida: {result.stderr}")
        
        # Contar reducción de tamaño
        original_size = len(xml_bytes)
        signed_size = len(signed)
        print(f"\nTamaño original: {original_size} bytes")
        print(f"Tamaño firmado: {signed_size} bytes")
        
    except Exception as e:
        print(f"❌ Error firmando: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Función principal"""
    print("=== TEST DE WHITESPACE EN XML SIFEN ===\n")
    
    # Test 1: Limpieza de whitespace
    test_whitespace_cleaning()
    
    # Test 2: Firma con limpieza
    test_sign_with_clean()
    
    print("\n=== TEST COMPLETADO ===")

if __name__ == "__main__":
    main()
