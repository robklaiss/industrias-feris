#!/usr/bin/env python3
"""
Helpers para el script autofix_0160_gTotSub.py

Funciones reutilizables para manejo de artifacts y comandos.
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional, List


def find_latest_file(pattern: str, directory: Path) -> Optional[Path]:
    """Encuentra el archivo más reciente que coincide con el patrón"""
    files = list(directory.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def find_latest_files(patterns: List[str], directory: Path) -> dict:
    """Encuentra los archivos más recientes para múltiples patrones"""
    result = {}
    for pattern in patterns:
        file = find_latest_file(pattern, directory)
        if file:
            result[pattern] = file
    return result


def run_command(cmd: List[str], cwd: Optional[Path] = None, capture: bool = True) -> subprocess.CompletedProcess:
    """
    Ejecuta un comando y retorna el resultado.
    
    Args:
        cmd: Lista de argumentos del comando
        cwd: Directorio de trabajo (opcional)
        capture: Si True, captura stdout/stderr
    
    Returns:
        subprocess.CompletedProcess
    """
    if cwd is None:
        cwd = Path.cwd()
    
    print(f"🔧 Ejecutando: {' '.join(cmd)}")
    
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        if result.returncode != 0:
            print(f"❌ Error en comando: {result.stderr}")
        return result
    else:
        # Mostrar salida en tiempo real
        result = subprocess.run(cmd, cwd=cwd)
        return result


def validate_file_exists(path: Path, description: str) -> None:
    """Valida que un archivo exista, si no, sale con error"""
    if not path.exists():
        print(f"❌ No existe {description}: {path}")
        sys.exit(1)


def extract_iteration_from_filename(filename: str) -> int:
    """Extrae el número de iteración de un nombre de archivo"""
    import re
    match = re.search(r'iter(\d+)', filename)
    if match:
        return int(match.group(1))
    return 0


def format_file_size(size_bytes: int) -> str:
    """Formatea tamaño de archivo para humans"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def print_separator(title: str = "", width: int = 50):
    """Imprime un separador con título opcional"""
    if title:
        print(f"{'-' * width}")
        print(f" {title} ")
        print(f"{'-' * width}")
    else:
        print(f"{'-' * width}")
