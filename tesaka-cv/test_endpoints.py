#!/usr/bin/env python3
"""
Script para probar los endpoints de emisión de facturas
"""
import requests
import json
import time

# Base URL
BASE_URL = "http://localhost:8000"

def test_emitir():
    """Test del endpoint POST /api/v1/emitir"""
    print("\n🧪 Test POST /api/v1/emitir")
    print("-" * 40)
    
    data = {
        "ruc": "80012345",
        "timbrado": "12345678",
        "establecimiento": "001",
        "punto_expedicion": "001",
        "numero_documento": "0000001",
        "env": "test"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/v1/emitir", json=data)
        print(f"Status: {response.status_code}")
        
        if response.ok:
            result = response.json()
            print("✅ Factura emitida exitosamente:")
            # Mostrar solo campos clave
            print(f"   dId: {result.get('dId', 'N/A')}")
            print(f"   dProtConsLote: {result.get('dProtConsLote', 'N/A')}")
            print(f"   estado: {result.get('status', 'N/A')}")
            print(f"   success: {result.get('success', False)}")
            
            # Si se emitió correctamente, probar seguimiento
            if result.get("dProtConsLote"):
                time.sleep(2)  # Esperar un momento antes de consultar
                test_follow(result["dProtConsLote"])
        else:
            print("❌ Error:")
            try:
                error = response.json()
                print(f"   {error.get('detail', str(error))}")
            except:
                print(f"   {response.text[:200]}...")
            
    except requests.exceptions.ConnectionError:
        print("❌ Error de conexión - asegúrate que el servidor está corriendo")
    except Exception as e:
        print(f"❌ Error: {e}")

def test_follow(dprot=None):
    """Test del endpoint GET /api/v1/follow"""
    print("\n🧪 Test GET /api/v1/follow")
    print("-" * 40)
    
    # Usar el protocolo proporcionado o uno de ejemplo
    param = dprot or "12345678901234567890"
    
    try:
        response = requests.get(f"{BASE_URL}/api/v1/follow", params={"prot": param})
        print(f"Status: {response.status_code}")
        
        if response.ok:
            result = response.json()
            print("✅ Consulta de seguimiento:")
            # Mostrar solo campos clave
            print(f"   ok: {result.get('ok', False)}")
            print(f"   dCodRes: {result.get('dCodRes', 'N/A')}")
            print(f"   dMsgRes: {result.get('dMsgRes', 'N/A')}")
            print(f"   dProtConsLote: {result.get('dProtConsLote', 'N/A')}")
            print(f"   dEstRes: {result.get('dEstRes', 'N/A')}")
            print(f"   estado: {result.get('estado', 'N/A')}")
        else:
            print("❌ Error:")
            try:
                error = response.json()
                print(f"   {error.get('detail', str(error))}")
            except:
                print(f"   {response.text[:200]}...")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def test_ui():
    """Test de las interfaces web"""
    print("\n🧪 Test UI endpoints")
    print("-" * 40)
    
    endpoints = [
        "/ui/emitir",
        "/ui/seguimiento"
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}")
            print(f"{endpoint}: Status {response.status_code}")
            if response.ok:
                print(f"✅ UI disponible en {BASE_URL}{endpoint}")
        except Exception as e:
            print(f"❌ Error en {endpoint}: {e}")

if __name__ == "__main__":
    print("🚀 Probando endpoints de SIFEN")
    print(f"   Base URL: {BASE_URL}")
    
    # Probar UI primero
    test_ui()
    
    # Probar emisión
    test_emitir()
