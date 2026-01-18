#!/usr/bin/env python3
"""
Forensic analysis tool for SIFEN error 0160 "XML Mal Formado"
Investigates discrepancies between ZIP content and SOAP payload
"""

import base64
import hashlib
import os
import subprocess
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime

def calculate_file_hash(filepath):
    """Calculate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def extract_base64_from_soap(soap_file):
    """Extract base64 content from <sifen:xDE> element in SOAP file"""
    with open(soap_file, 'r', encoding='utf-8') as f:
        soap_content = f.read()
    
    # Find xDE element content
    start_tag = '<sifen:xDE>'
    end_tag = '</sifen:xDE>'
    
    start_idx = soap_content.find(start_tag)
    if start_idx == -1:
        raise ValueError("No se encontró <sifen:xDE> en el SOAP")
    
    start_idx += len(start_tag)
    end_idx = soap_content.find(end_tag, start_idx)
    if end_idx == -1:
        raise ValueError("No se encontró </sifen:xDE> en el SOAP")
    
    # Extract and clean base64 (remove newlines and spaces)
    base64_content = soap_content[start_idx:end_idx].replace('\n', '').replace(' ', '').strip()
    return base64_content

def extract_lote_from_zip(zip_path):
    """Extract lote.xml from a ZIP file"""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        if 'lote.xml' not in zf.namelist():
            raise ValueError("No se encontró lote.xml en el ZIP")
        
        with zf.open('lote.xml') as f:
            return f.read()

def compare_files_binary(file1, file2):
    """Compare two files byte by byte"""
    with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
        while True:
            b1 = f1.read(4096)
            b2 = f2.read(4096)
            
            if b1 != b2:
                return False
            if not b1:  # EOF
                break
    return True

def main():
    artifacts_dir = Path("artifacts")
    if not artifacts_dir.exists():
        print(f"Error: No existe directorio artifacts/", file=sys.stderr)
        sys.exit(1)
    
    # Find the most recent SOAP request file
    soap_files = list(artifacts_dir.glob("recibe_lote_REQ_*.xml"))
    if not soap_files:
        print("Error: No se encontró archivo recibe_lote_REQ_*.xml", file=sys.stderr)
        sys.exit(1)
    
    soap_file = max(soap_files, key=os.path.getctime)
    print(f"Usando archivo SOAP: {soap_file.name}")
    
    # Find the last payload ZIP
    payload_zip = artifacts_dir / "last_lote_from_payload.zip"
    if not payload_zip.exists():
        print("Error: No existe artifacts/last_lote_from_payload.zip", file=sys.stderr)
        print("Ejecuta el envío con --dump-http primero", file=sys.stderr)
        sys.exit(1)
    
    # Step 1: Extract base64 from SOAP
    print("\n1. Extrayendo base64 del SOAP...")
    base64_content = extract_base64_from_soap(soap_file)
    print(f"   Base64 length: {len(base64_content)} caracteres")
    
    # Step 2: Decode base64 to ZIP
    print("\n2. Decodificando base64 a ZIP...")
    try:
        zip_bytes = base64.b64decode(base64_content)
    except Exception as e:
        print(f"   Error decodificando base64: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Save forensic ZIP
    forensic_zip = artifacts_dir / "_forense_from_soap.zip"
    with open(forensic_zip, 'wb') as f:
        f.write(zip_bytes)
    print(f"   Guardado en: {forensic_zip}")
    
    # Step 3: Extract lote.xml from forensic ZIP
    print("\n3. Extrayendo lote.xml del ZIP forense...")
    try:
        lote_bytes = extract_lote_from_zip(forensic_zip)
    except Exception as e:
        print(f"   Error extrayendo lote.xml: {e}", file=sys.stderr)
        sys.exit(1)
    
    forensic_lote = artifacts_dir / "_forense_from_soap_lote.xml"
    with open(forensic_lote, 'wb') as f:
        f.write(lote_bytes)
    print(f"   Guardado en: {forensic_lote}")
    
    # Step 4: Extract lote.xml from payload ZIP
    payload_lote = artifacts_dir / "last_lote_from_payload.xml"
    print("\n4. Extrayendo lote.xml del ZIP payload...")
    try:
        payload_lote_bytes = extract_lote_from_zip(payload_zip)
        with open(payload_lote, 'wb') as f:
            f.write(payload_lote_bytes)
    except Exception as e:
        print(f"   Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Step 5: Compare hashes
    print("\n5. Comparando hashes SHA256...")
    
    # ZIP hashes
    hash_payload_zip = calculate_file_hash(payload_zip)
    hash_forensic_zip = calculate_file_hash(forensic_zip)
    print(f"\n   ZIPs:")
    print(f"   last_lote_from_payload.zip: {hash_payload_zip}")
    print(f"   _forense_from_soap.zip:     {hash_forensic_zip}")
    print(f"   ¿Idénticos?: {'SÍ' if hash_payload_zip == hash_forensic_zip else 'NO'}")
    
    # lote.xml hashes
    hash_payload_lote = calculate_file_hash(payload_lote)
    hash_forensic_lote = calculate_file_hash(forensic_lote)
    print(f"\n   lote.xml:")
    print(f"   last_lote_from_payload.xml: {hash_payload_lote}")
    print(f"   _forense_from_soap_lote.xml: {hash_forensic_lote}")
    print(f"   ¿Idénticos?: {'SÍ' if hash_payload_lote == hash_forensic_lote else 'NO'}")
    
    # Step 6: Binary comparison if hashes differ
    if hash_payload_zip != hash_forensic_zip:
        print(f"\n6. Los ZIPs son DIFERENTES!")
        print(f"   Tamaño payload ZIP: {os.path.getsize(payload_zip)} bytes")
        print(f"   Tamaño forensic ZIP: {os.path.getsize(forensic_zip)} bytes")
        
        # Try to show first differences
        with open(payload_zip, 'rb') as f1, open(forensic_zip, 'rb') as f2:
            payload_data = f1.read()
            forensic_data = f2.read()
            
        min_len = min(len(payload_data), len(forensic_data))
        for i in range(min_len):
            if payload_data[i] != forensic_data[i]:
                print(f"   Primer byte diferente en posición: {i}")
                print(f"   Payload ZIP: 0x{payload_data[i]:02x}")
                print(f"   Forensic ZIP: 0x{forensic_data[i]:02x}")
                break
    
    if hash_payload_lote != hash_forensic_lote:
        print(f"\n6. Los lote.xml son DIFERENTES!")
        print(f"   Tamaño payload lote: {os.path.getsize(payload_lote)} bytes")
        print(f"   Tamaño forensic lote: {os.path.getsize(forensic_lote)} bytes")
        
        # Show textual diff
        print(f"\n   Diff (primeras 20 líneas):")
        try:
            result = subprocess.run(
                ['diff', '-u', str(payload_lote), str(forensic_lote)],
                capture_output=True, text=True
            )
            lines = result.stdout.split('\n')[:20]
            for line in lines:
                print(f"   {line}")
        except:
            print("   No se pudo generar diff")
    
    # Step 7: Summary
    print(f"\n{'='*60}")
    print("RESUMEN FORENSE:")
    print(f"{'='*60}")
    
    if hash_payload_zip == hash_forensic_zip and hash_payload_lote == hash_forensic_lote:
        print("✅ ZIP y lote.xml son IDÉNTICOS en todo el flujo")
        print("   La causa del 0160 NO es una alteración en el transporte")
        print("\nSiguientes pasos a investigar:")
        print("1. QName del request vs WSDL")
        print("2. Binding/operation correcta")
        print("3. Requisitos no documentados de SIFEN")
    else:
        print("❌ Se detectaron DIFERENCIAS!")
        if hash_payload_zip != hash_forensic_zip:
            print("   - El ZIP se alteró entre la construcción y el SOAP")
        if hash_payload_lote != hash_forensic_lote:
            print("   - El lote.xml se alteró")
        print("\nPróximo paso:")
        print("1. Identificar dónde se altera (zip/base64/SOAP)")
        print("2. Corregir el paso mínimo")
        print("3. Reenviar a SIFEN")
    
    # Save forensic report
    report = artifacts_dir / f"_forense_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report, 'w') as f:
        f.write(f"Forense SIFEN 0160 - {datetime.now()}\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"SOAP archivo: {soap_file.name}\n")
        f.write(f"ZIP payload hash: {hash_payload_zip}\n")
        f.write(f"ZIP forensic hash: {hash_forensic_zip}\n")
        f.write(f"ZIPs idénticos: {hash_payload_zip == hash_forensic_zip}\n")
        f.write(f"lote.xml payload hash: {hash_payload_lote}\n")
        f.write(f"lote.xml forensic hash: {hash_forensic_lote}\n")
        f.write(f"lote.xml idénticos: {hash_payload_lote == hash_forensic_lote}\n")
    
    print(f"\nReporte guardado en: {report}")

if __name__ == "__main__":
    main()
