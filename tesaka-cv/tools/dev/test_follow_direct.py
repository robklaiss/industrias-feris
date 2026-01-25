#!/usr/bin/env python3
"""
Test directo del endpoint /api/v1/follow
"""
import requests
import json
import sys
from pathlib import Path

# Base URL
BASE_URL = "http://localhost:8000"

def test_follow_direct():
    """Test del endpoint POST /api/v1/follow con debug"""
    print("\n🧪 Test POST /api/v1/follow (DEBUG)")
    print("-" * 40)
    
    # Usar un protocolo de prueba
    test_prot = "123456789012345"
    
    try:
        response = requests.get(f"{BASE_URL}/api/v1/follow?prot={test_prot}", timeout=20)
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        
        if response.ok:
            result = response.json()
            print("\n✅ Respuesta JSON:")
            print(json.dumps(result, indent=2))
        else:
            print(f"\n❌ Error HTTP {response.status_code}")
            print("Response body:")
            print(response.text)
            
            # Guardar response para análisis
            output_path = Path(f"/tmp/follow_error_{response.status_code}.xml")
            output_path.write_text(response.text, encoding="utf-8")
            print(f"\n💾 Response guardado en: {output_path}")
            
            # Buscar indicios del error
            if "0160" in response.text:
                print("\n🚨 Error 0160 detectado - XML mal formado")
            if "dCodRes" in response.text:
                import re
                cod_res = re.search(r'<dCodRes>([^<]+)</dCodRes>', response.text)
                if cod_res:
                    print(f"\n📋 Código SIFEN: {cod_res.group(1)}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Error de conexión. Asegúrate de que el servidor esté corriendo:")
        print("   cd tesaka-cv && .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000")
        return 1
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(test_follow_direct())
