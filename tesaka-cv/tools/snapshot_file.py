#!/usr/bin/env python3
"""
Snapshot utilitario simple para copiar un archivo (aunque no esté en git) y
guardar una copia byte a byte con metadatos básicos.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        print(f"❌ El archivo origen no existe: {src}")
        raise SystemExit(2)

    dst.parent.mkdir(parents=True, exist_ok=True)

    data = src.read_bytes()
    dst.write_bytes(data)

    size_bytes = len(data)
    sha256 = compute_sha256(data)

    print("✅ Snapshot creado correctamente")
    print(f"   Origen : {src}")
    print(f"   Destino: {dst}")
    print(f"   Tamaño : {size_bytes} bytes")
    print(f"   SHA256 : {sha256}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crear snapshot byte a byte de un archivo")
    parser.add_argument("--src", required=True, help="Ruta del archivo origen")
    parser.add_argument("--dst", required=True, help="Ruta del snapshot destino")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    src = Path(os.path.expanduser(args.src)).resolve()
    dst = Path(os.path.expanduser(args.dst)).resolve()

    try:
        snapshot_file(src, dst)
    except SystemExit as exc:
        return int(exc.code)
    except Exception as exc:
        print(f"❌ Error inesperado creando snapshot: {exc}")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
