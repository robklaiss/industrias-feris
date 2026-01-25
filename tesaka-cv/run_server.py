#!/usr/bin/env python3
"""
Script para iniciar el servidor FastAPI
"""
import os
import sys
import uvicorn
from pathlib import Path

# Asegurar que estamos en el directorio correcto
script_dir = Path(__file__).parent
os.chdir(script_dir)

# Configurar variables de entorno si no están seteadas
if not os.getenv("SIFEN_ENV"):
    os.environ["SIFEN_ENV"] = "test"

if not os.getenv("PYTHONPATH"):
    os.environ["PYTHONPATH"] = str(script_dir)

print(f"🚀 Iniciando servidor FastAPI...")
print(f"   Directorio: {script_dir}")
print(f"   Ambiente SIFEN: {os.environ['SIFEN_ENV']}")
print(f"   Python: {sys.executable}")
print()

# Iniciar servidor
uvicorn.run(
    "app.main:app",
    host="0.0.0.0",
    port=8000,
    reload=False,
    log_level="info"
)
