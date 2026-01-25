#!/usr/bin/env python3
"""
Script para depurar qué XML genera el endpoint /api/v1/emitir
"""
import requests
import json
import sys
from pathlib import Path

# Base URL
BASE_URL = "http://localhost:8000"

def test_emitir_debug():
    """Test del endpoint POST /api/v1/emitir con debug"""
    print("\n🧪 Test POST /api/v1/emitir (DEBUG)")
    print("-" * 40)
    
    data = {
        "ruc": "80012345-7",
        "timbrado": "12345678",
        "establecimiento": "001",
        "punto_expedicion": "001",
        "numero_documento": "0000001",
        "env": "test"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/v1/emitir", json=data, timeout=20)
        print(f"Status: {response.status_code}")
        
        if response.ok:
            result = response.json()
            print("✅ Respuesta recibida:")
            print(f"   dId: {result.get('dId', 'N/A')}")
            print(f"   dProtConsLote: {result.get('dProtConsLote', 'N/A')}")
            print(f"   estado: {result.get('status', 'N/A')}")
            print(f"   success: {result.get('success', False)}")
            
            # Descargar el XML DE para revisar firma
            did = result.get('dId')
            if did:
                de_url = f"{BASE_URL}/api/v1/artifacts/{did}/de"
                de_response = requests.get(de_url)
                if de_response.ok:
                    # Guardar XML para análisis
                    output_path = Path(f"/tmp/DE_debug_{did}.xml")
                    output_path.write_text(de_response.text, encoding="utf-8")
                    print(f"\n💾 XML guardado en: {output_path}")
                    
                    # Buscar problemas de firma
                    xml_content = de_response.text
                    issues = []
                    
                    if 'rsa-sha1' in xml_content.lower():
                        issues.append("❌ RSA-SHA1 encontrado (debe ser RSA-SHA256)")
                    if 'xmldsig#sha1' in xml_content.lower():
                        issues.append("❌ SHA-1 Digest encontrado (debe ser SHA-256)")
                    if 'dGhpcyBpcyBhIHRlc3Q' in xml_content:
                        issues.append("❌ Firma placeholder/dummy encontrada")
                    
                    if issues:
                        print("\n🚨 Problemas detectados en el XML:")
                        for issue in issues:
                            print(f"   {issue}")
                    else:
                        print("\n✅ No se detectaron problemas de firma SHA-1/dummy")
                        
                    # Verificar dRucEm
                    import re
                    ruc_match = re.search(r'<dRucEm>([^<]+)</dRucEm>', xml_content)
                    if ruc_match:
                        ruc_value = ruc_match.group(1)
                        if ruc_value.startswith('0'):
                            print(f"⚠️  dRucEm tiene cero a la izquierda: {ruc_value}")
                        else:
                            print(f"✅ dRucEm sin cero inicial: {ruc_value}")
                else:
                    print(f"❌ Error descargando XML: {de_response.status_code}")
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("❌ Error de conexión. Asegúrate de que el servidor esté corriendo:")
        print("   cd tesaka-cv && .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000")
        return 1
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(test_emitir_debug())
