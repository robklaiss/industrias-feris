#!/usr/bin/env python3
"""
Verifica la estructura de artifacts/last_lote.xml (o un XML provisto) y falla si
- el root no es rLoteDE
- no existe al menos un rDE
- la cantidad de xDE directos no coincide con rDE
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.lote_structure_utils import (
    SIFEN_NS,
    analyze_lote_bytes,
)


def _load_xml(path: Path) -> bytes:
    if not path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {path}")
    return path.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanity check para lote.xml (verifica root=rLoteDE y xDE/rDE 1:1)",
    )
    parser.add_argument(
        "--xml",
        type=Path,
        default=Path("artifacts/last_lote.xml"),
        help="Path al lote.xml a validar (default: artifacts/last_lote.xml)",
    )
    args = parser.parse_args()

    try:
        xml_bytes = _load_xml(args.xml)
    except Exception as exc:
        print(f"❌ No se pudo leer {args.xml}: {exc}")
        return 1

    try:
        info, _ = analyze_lote_bytes(xml_bytes)
    except Exception as exc:
        print(f"❌ lote.xml inválido: {exc}")
        return 1

    print("🔍 Lote structure:")
    print(f"   archivo: {args.xml}")
    print(f"   root: {info.root_local} (ns={info.root_namespace or 'VACÍO'})")
    print(f"   xDE count: {info.xde_count}")
    print(f"   rDE count (total): {info.rde_total}")
    print(f"   rDE en namespace SIFEN: {info.rde_sifen}")
    if info.first_de_id:
        print(f"   Primer DE.Id: {info.first_de_id}")

    errors: list[str] = []
    if info.root_local != "rLoteDE":
        errors.append(f"root localname != rLoteDE (recibido: {info.root_local})")
    if info.root_namespace != SIFEN_NS:
        errors.append(
            f"rLoteDE debe tener namespace {SIFEN_NS}, recibido: {info.root_namespace or 'VACÍO'}"
        )
    if info.rde_total == 0:
        errors.append("No se encontró ningún <rDE> en el lote")
    if info.xde_count != info.rde_total:
        errors.append(
            f"xDE count ({info.xde_count}) no coincide con rDE count ({info.rde_total})"
        )

    if errors:
        print("\n❌ Sanity FAILED:")
        for idx, message in enumerate(errors, 1):
            print(f"   {idx}. {message}")
        return 1

    print("\n✅ Sanity OK: root=rLoteDE, namespace correcto y xDE/rDE están 1:1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
