#!/usr/bin/env python3
"""
Script para verificar que las rutas de API estén registradas correctamente
"""
import sys
import os
from pathlib import Path

# Forzar modo TEST para evitar errores
os.environ["SIFEN_ENV"] = "test"

# Agregar el path del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

def main():
    print("=== Verificación de rutas registradas ===\n")
    
    # Rutas esperadas
    expected_routes = [
        "/api/v1/artifacts/{did}",
        "/api/v1/artifacts/{did}/de",
        "/api/v1/artifacts/{did}/rechazo",
        "/api/v1/artifacts/{did}/meta",
        "/api/v1/artifacts/latest",
        "/api/v1/follow",
        "/api/v1/emitir"
    ]
    
    # Obtener todas las rutas registradas
    registered_routes = []
    for route in app.routes:
        if hasattr(route, 'path'):
            registered_routes.append(route.path)
    
    print("Rutas registradas en FastAPI:")
    for route in sorted(registered_routes):
        if route.startswith('/api/v1/'):
            print(f"  ✓ {route}")
    
    print("\n=== Verificación de rutas esperadas ===")
    all_ok = True
    
    for expected in expected_routes:
        # Convertir a patrón para buscar coincidencias
        # {did} -> cualquier string que no contenga /
        if '{did}' in expected:
            pattern = expected.replace('{did}', '[^/]+')
        else:
            pattern = expected.replace('{', '').replace('}', '')
        
        # Buscar si hay una ruta que coincida
        found = False
        for registered in registered_routes:
            if '{' not in expected:
                if registered == expected:
                    found = True
                    break
            else:
                # Para rutas con parámetros, verificar la estructura
                if registered.replace('{did}', 'X').replace('{prot}', 'X') == expected.replace('{did}', 'X').replace('{prot}', 'X'):
                    found = True
                    break
        
        if found:
            print(f"  ✓ {expected}")
        else:
            print(f"  ✗ {expected} - NO ENCONTRADA")
            all_ok = False
    
    print("\n=== Verificación del módulo routes_artifacts ===")
    try:
        from app.routes_artifacts import validate_did
        print("  ✓ validate_did importable correctamente")
        
        # Probar validate_did
        assert validate_did("123456789") == True
        assert validate_did("") == False
        assert validate_did("../malicious") == False
        print("  ✓ validate_did funciona correctamente")
    except Exception as e:
        print(f"  ✗ Error con validate_did: {e}")
        all_ok = False
    
    print("\n=== Resultado final ===")
    if all_ok:
        print("✅ Todas las rutas están registradas y funcionando")
        return 0
    else:
        print("❌ Hay rutas faltantes o con errores")
        return 1

if __name__ == "__main__":
    sys.exit(main())
