#!/usr/bin/env python3
"""
Script de auditoría para reconstruir QR desde XML y comparar con el QR actual.
Identifica exactamente qué campo difiere (si difiere).
"""

import sys
import os
import re
import hashlib
import base64
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path


def extract_xml_values(xml_path: str) -> dict:
    """Extrae todos los valores necesarios para generar el QR desde el XML."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    ns = {
        'sifen': 'http://ekuatia.set.gov.py/sifen/xsd',
        'ds': 'http://www.w3.org/2000/09/xmldsig#'
    }
    
    de = root.find('.//sifen:DE', ns)
    if de is None:
        raise ValueError("No se encontró elemento DE en el XML")
    
    values = {}
    
    # A002 - Id (CDC)
    values['Id'] = de.get('Id', '').strip()
    
    # D002 - dFeEmiDE
    d_fe_node = root.find('.//sifen:dFeEmiDE', ns)
    d_fe = d_fe_node.text.strip() if d_fe_node is not None and d_fe_node.text else None
    if d_fe:
        values['dFeEmiDE_raw'] = d_fe
        values['dFeEmiDE_hex'] = d_fe.encode('utf-8').hex()
    
    # Receptor - iNatRec determina si usar dRucRec o dNumIDRec
    i_nat_rec_node = root.find('.//sifen:iNatRec', ns)
    i_nat_rec = i_nat_rec_node.text.strip() if i_nat_rec_node is not None and i_nat_rec_node.text else None
    
    if i_nat_rec == '1':
        # Persona jurídica - usar dRucRec
        d_ruc_rec_node = root.find('.//sifen:dRucRec', ns)
        receptor_val = d_ruc_rec_node.text.strip() if d_ruc_rec_node is not None and d_ruc_rec_node.text else None
        if receptor_val:
            values['receptor_key'] = 'dRucRec'
            values['receptor_val'] = receptor_val
        else:
            values['receptor_key'] = 'dNumIDRec'
            values['receptor_val'] = '0'
    else:
        # Persona física u otro - usar dNumIDRec
        d_num_id_rec_node = root.find('.//sifen:dNumIDRec', ns)
        receptor_val = d_num_id_rec_node.text.strip() if d_num_id_rec_node is not None and d_num_id_rec_node.text else '0'
        values['receptor_key'] = 'dNumIDRec'
        values['receptor_val'] = receptor_val
    
    # F014 - dTotGralOpe
    d_tot_gral_node = root.find('.//sifen:dTotGralOpe', ns)
    values['dTotGralOpe'] = d_tot_gral_node.text.strip() if d_tot_gral_node is not None and d_tot_gral_node.text else '0'
    
    # F017 - dTotIVA (solo si iTImp = 1 o 5)
    i_timp_node = root.find('.//sifen:iTImp', ns)
    i_timp = i_timp_node.text.strip() if i_timp_node is not None and i_timp_node.text else None
    
    if i_timp in ('1', '5'):
        d_tot_iva_node = root.find('.//sifen:dTotIVA', ns)
        values['dTotIVA'] = d_tot_iva_node.text.strip() if d_tot_iva_node is not None and d_tot_iva_node.text else '0'
    else:
        values['dTotIVA'] = '0'
    
    # E701 - cItems (cantidad de items)
    items = root.findall('.//sifen:gCamItem', ns)
    values['cItems'] = str(len(items))
    
    # XS17 - DigestValue
    digest_node = root.find('.//ds:DigestValue', ns)
    digest_b64 = digest_node.text.strip() if digest_node is not None and digest_node.text else None
    if digest_b64:
        values['DigestValue_b64'] = digest_b64
        # Convertir según especificación: base64 bytes -> hex
        digest_bytes = base64.b64decode(digest_b64)
        digest_b64_reencoded = base64.b64encode(digest_bytes)
        values['DigestValue_hex'] = digest_b64_reencoded.hex()
    
    # QR actual en el XML
    qr_node = root.find('.//sifen:dCarQR', ns)
    values['qr_actual'] = qr_node.text.strip().replace('&amp;', '&') if qr_node is not None and qr_node.text else None
    
    return values


def reconstruct_qr(values: dict, csc: str, csc_id: str, env: str = 'TEST') -> dict:
    """Reconstruye el QR URL según la especificación SIFEN."""
    
    # Base URL según ambiente
    if env == 'TEST':
        qr_base = 'https://ekuatia.set.gov.py/consultas-test/qr?'
    else:
        qr_base = 'https://ekuatia.set.gov.py/consultas/qr?'
    
    # Construir parámetros en orden EXACTO según especificación
    params = OrderedDict()
    params['nVersion'] = '150'
    params['Id'] = values['Id']
    params['dFeEmiDE'] = values['dFeEmiDE_hex']
    params[values['receptor_key']] = values['receptor_val']
    params['dTotGralOpe'] = values['dTotGralOpe']
    params['dTotIVA'] = values['dTotIVA']
    params['cItems'] = values['cItems']
    params['DigestValue'] = values['DigestValue_hex']
    params['IdCSC'] = csc_id.zfill(4)  # 4 dígitos con ceros a la izquierda
    
    # Construir string de parámetros
    url_params = '&'.join(f"{k}={v}" for k, v in params.items())
    
    # Calcular hash: SHA-256(url_params + CSC)
    hash_input = url_params + csc
    qr_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()  # lowercase
    
    # URL completa
    qr_url = f"{qr_base}{url_params}&cHashQR={qr_hash}"
    
    return {
        'qr_base': qr_base,
        'params': params,
        'url_params': url_params,
        'hash_input': hash_input,
        'qr_hash': qr_hash,
        'qr_url': qr_url
    }


def parse_qr_params(qr_url: str) -> dict:
    """Parsea los parámetros de una URL QR."""
    match = re.search(r'\?(.*)', qr_url)
    if not match:
        return {}
    
    params = OrderedDict()
    for param in match.group(1).split('&'):
        if '=' in param:
            k, v = param.split('=', 1)
            params[k] = v
    return params


def compare_qrs(actual_qr: str, reconstructed: dict) -> list:
    """Compara QR actual vs reconstruido y retorna diferencias."""
    differences = []
    
    # Comparar base URL
    actual_base = actual_qr.split('?')[0] + '?'
    if actual_base != reconstructed['qr_base']:
        differences.append({
            'field': 'BASE_URL',
            'actual': actual_base,
            'expected': reconstructed['qr_base'],
            'match': False
        })
    
    # Parsear parámetros actuales
    actual_params = parse_qr_params(actual_qr)
    expected_params = reconstructed['params'].copy()
    expected_params['cHashQR'] = reconstructed['qr_hash']
    
    # Comparar cada parámetro
    all_keys = set(actual_params.keys()) | set(expected_params.keys())
    
    for key in all_keys:
        actual_val = actual_params.get(key, 'MISSING')
        expected_val = expected_params.get(key, 'MISSING')
        match = actual_val == expected_val
        
        if not match:
            differences.append({
                'field': key,
                'actual': actual_val,
                'expected': expected_val,
                'match': False
            })
    
    # Comparar URL completa
    if actual_qr != reconstructed['qr_url']:
        differences.append({
            'field': 'FULL_URL',
            'actual': actual_qr[:100] + '...',
            'expected': reconstructed['qr_url'][:100] + '...',
            'match': False
        })
    
    return differences


def audit_qr(xml_path: str, csc: str, csc_id: str, env: str = 'TEST'):
    """Ejecuta auditoría completa del QR."""
    
    print("=" * 80)
    print("AUDITORÍA DE RECONSTRUCCIÓN QR")
    print("=" * 80)
    print(f"XML: {xml_path}")
    print(f"CSC: {csc[:10]}... (len={len(csc)})")
    print(f"CSC ID: {csc_id}")
    print(f"Ambiente: {env}")
    print()
    
    # Paso 1: Extraer valores del XML
    print("PASO 1: Extrayendo valores del XML...")
    values = extract_xml_values(xml_path)
    
    print(f"  ✓ Id: {values['Id']}")
    print(f"  ✓ dFeEmiDE: {values['dFeEmiDE_raw']} -> {values['dFeEmiDE_hex']}")
    print(f"  ✓ Receptor: {values['receptor_key']}={values['receptor_val']}")
    print(f"  ✓ dTotGralOpe: {values['dTotGralOpe']}")
    print(f"  ✓ dTotIVA: {values['dTotIVA']}")
    print(f"  ✓ cItems: {values['cItems']}")
    print(f"  ✓ DigestValue: {values['DigestValue_b64']} -> {values['DigestValue_hex']}")
    print()
    
    # Paso 2: Reconstruir QR
    print("PASO 2: Reconstruyendo QR según especificación...")
    reconstructed = reconstruct_qr(values, csc, csc_id, env)
    
    print(f"  ✓ Base URL: {reconstructed['qr_base']}")
    print(f"  ✓ Parámetros: {len(reconstructed['params'])} parámetros")
    print(f"  ✓ Hash input length: {len(reconstructed['hash_input'])} chars")
    print(f"  ✓ cHashQR: {reconstructed['qr_hash']}")
    print()
    
    # Paso 3: Comparar con QR actual
    print("PASO 3: Comparando QR actual vs reconstruido...")
    differences = compare_qrs(values['qr_actual'], reconstructed)
    
    if not differences:
        print("  ✓ ¡QR ACTUAL COINCIDE EXACTAMENTE CON EL RECONSTRUIDO!")
        print()
        print("=" * 80)
        print("CONCLUSIÓN: El QR está correctamente generado según especificación.")
        print("=" * 80)
        return True
    else:
        print(f"  ✗ Se encontraron {len(differences)} diferencias:")
        print()
        
        for diff in differences:
            print(f"  Campo: {diff['field']}")
            print(f"    Actual:   {diff['actual']}")
            print(f"    Esperado: {diff['expected']}")
            print()
        
        print("=" * 80)
        print("CONCLUSIÓN: El QR NO coincide con la especificación.")
        print("=" * 80)
        return False


if __name__ == '__main__':
    # Configuración
    xml_path = os.path.expanduser('~/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml')
    csc = os.getenv('SIFEN_CSC', 'ABCD0000000000000000000000000000')
    csc_id = os.getenv('SIFEN_CSC_ID', '1')
    env = os.getenv('SIFEN_ENV', 'TEST')
    
    if not Path(xml_path).exists():
        print(f"ERROR: No se encontró el XML en {xml_path}")
        sys.exit(1)
    
    # Ejecutar auditoría
    success = audit_qr(xml_path, csc, csc_id, env)
    
    sys.exit(0 if success else 1)
