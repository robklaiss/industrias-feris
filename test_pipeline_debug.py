#!/usr/bin/env python3
"""
Script para probar el pipeline de send_sirecepde con instrumentación
y detectar exactamente dónde cambia el XML
"""
import os
import sys
from pathlib import Path

# Agregar el directorio del proyecto al path
sys.path.insert(0, str(Path(__file__).parent))

# Configurar variables de entorno para debug
os.environ["SIFEN_DEBUG_SOAP"] = "1"
os.environ["SIFEN_DUMP_HTTP"] = "1"

# Importar y ejecutar send_sirecepde con un XML de prueba
from tesaka_cv.tools.send_sirecepde import main

if __name__ == "__main__":
    # Simular argumentos de línea de comandos
    sys.argv = [
        "send_sirecepde.py",
        "--env", "test",
        "--xml", "artifacts/test_signed.xml",  # Ajustar este path a un XML real
        "--dump-http"
    ]
    
    print("="*60)
    print("EJECUTANDO TEST DE PIPELINE CON INSTRUMENTACIÓN")
    print("="*60)
    print()
    
    # Ejecutar main
    exit_code = main()
    
    print()
    print("="*60)
    print("ANÁLISIS DE HASHES")
    print("="*60)
    
    # Leer los hashes generados
    artifacts_dir = Path("artifacts")
    if artifacts_dir.exists():
        print("\nArchivos de stage generados:")
        for f in sorted(artifacts_dir.glob("_stage_*.xml")):
            size = f.stat().st_size
            print(f"  - {f.name}: {size} bytes")
    
    print()
    print("Para analizar los cambios:")
    print("1. Comparar los hashes mostrados en la salida")
    print("2. Si hay un cambio entre etapas, comparar los archivos:")
    print("   diff artifacts/_stage_XX_before.xml artifacts/_stage_XX_after.xml")
    print()
    
    sys.exit(exit_code)
