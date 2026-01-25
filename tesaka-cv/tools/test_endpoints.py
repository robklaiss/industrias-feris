#!/usr/bin/env python3
"""
Test simple para verificar que los endpoints funcionen correctamente
"""
import os
import sys
from pathlib import Path

# Forzar modo TEST
os.environ["SIFEN_ENV"] = "test"

# Agregar el path del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_artifacts_endpoints():
    print("=== Test de endpoints de artifacts ===\n")
    
    # Test /api/v1/artifacts/latest (debe devolver 404 si no hay artifacts)
    print("1. GET /api/v1/artifacts/latest")
    response = client.get("/api/v1/artifacts/latest")
    print(f"   Status: {response.status_code}")
    if response.status_code == 404:
        print("   ✅ Respuesta esperada (404 - No hay artifacts)")
    else:
        print(f"   Response: {response.json()}")
    
    # Test /api/v1/artifacts/{did} con did inválido
    print("\n2. GET /api/v1/artifacts/../invalid")
    response = client.get("/api/v1/artifacts/../invalid")
    print(f"   Status: {response.status_code}")
    if response.status_code == 400:
        print("   ✅ Respuesta esperada (400 - dId inválido)")
    else:
        print(f"   Response: {response.json()}")
    
    # Test /api/v1/artifacts/123456789 (debe devolver 404 si no existe)
    print("\n3. GET /api/v1/artifacts/123456789")
    response = client.get("/api/v1/artifacts/123456789")
    print(f"   Status: {response.status_code}")
    if response.status_code == 404:
        print("   ✅ Respuesta esperada (404 - No encontrado)")
    else:
        print(f"   Response: {response.json()}")
    
    # Test /api/v1/artifacts/123456789/meta
    print("\n4. GET /api/v1/artifacts/123456789/meta")
    response = client.get("/api/v1/artifacts/123456789/meta")
    print(f"   Status: {response.status_code}")
    if response.status_code == 404:
        print("   ✅ Respuesta esperada (404 - Metadata no encontrada)")
    else:
        print(f"   Response: {response.json()}")

def test_follow_endpoint():
    print("\n=== Test de endpoint /api/v1/follow ===\n")
    
    # Test sin parámetros
    print("1. GET /api/v1/follow (sin parámetros)")
    response = client.get("/api/v1/follow")
    print(f"   Status: {response.status_code}")
    if response.status_code == 400:
        print("   ✅ Respuesta esperada (400 - Se requiere did o prot)")
    else:
        print(f"   Response: {response.json()}")
    
    # Test con prot vacío
    print("\n2. GET /api/v1/follow?prot=")
    response = client.get("/api/v1/follow?prot=")
    print(f"   Status: {response.status_code}")
    if response.status_code == 400:
        print("   ✅ Respuesta esperada (400 - prot es requerido)")
        print(f"   Mensaje: {response.json().get('detail', '')}")
    else:
        print(f"   Response: {response.json()}")
    
    # Test con prot solo espacios
    print("\n3. GET /api/v1/follow?prot=   ")
    response = client.get("/api/v1/follow?prot=   ")
    print(f"   Status: {response.status_code}")
    if response.status_code == 400:
        print("   ✅ Respuesta esperada (400 - prot no puede estar vacío)")
        print(f"   Mensaje: {response.json().get('detail', '')}")
    else:
        print(f"   Response: {response.json()}")
    
    # Test con prot válido (pero probablemente no exista en SIFEN)
    print("\n4. GET /api/v1/follow?prot=123456")
    response = client.get("/api/v1/follow?prot=123456")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    if response.status_code == 500:
        print("   ✅ Respuesta esperada (500 - Error de conexión SIFEN en modo TEST)")

def main():
    print("=== Test de endpoints - MODO TEST ===\n")
    
    test_artifacts_endpoints()
    test_follow_endpoint()
    
    print("\n=== Tests completados ===")

if __name__ == "__main__":
    main()
