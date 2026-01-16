#!/usr/bin/env python3
"""
Inspección rápida de un ZIP (lote.xml) o XML directo para contar xDE/rDE y mostrar IDs.
Útil para depurar por qué el contador local mostraba "NOT_FOUND".
"""
from __future__ import annotations

import argparse
import base64
import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.lote_structure_utils import analyze_lote_bytes


def _load_xml_from_zip_bytes(zip_bytes: bytes) -> bytes:
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        if "lote.xml" in names:
            return zf.read("lote.xml")
        xml_candidates = [n for n in names if n.lower().endswith(".xml")]
        if not xml_candidates:
            raise RuntimeError(f"ZIP debe contener al menos un XML (archivos: {names})")
        return zf.read(xml_candidates[0])


def _load_xml_from_zip(zip_path: Path) -> bytes:
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP no encontrado: {zip_path}")
    return _load_xml_from_zip_bytes(zip_path.read_bytes())


def _load_xml(path: Path) -> bytes:
    if not path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {path}")
    return path.read_bytes()


def _extract_from_soap(path: Path) -> bytes:
    import lxml.etree as etree

    soap_bytes = path.read_bytes()
    root = etree.fromstring(soap_bytes)
    xde_elem = root.find(".//*[local-name()='xDE']")
    if xde_elem is None or not (xde_elem.text or "").strip():
        raise RuntimeError("SOAP no contiene xDE con contenido")
    xde_clean = re.sub(r"\s+", "", xde_elem.text.strip())
    zip_bytes = base64.b64decode(xde_clean)
    return _load_xml_from_zip_bytes(zip_bytes)


def _analyze_source(xml_bytes: bytes, label: str) -> bool:
    info, _ = analyze_lote_bytes(xml_bytes)
    print(f"\n🔍 {label}")
    print(f"   root: {info.root_local} (ns={info.root_namespace or 'VACÍO'})")
    print(f"   xDE count: {info.xde_count}")
    print(f"   rDE count: {info.rde_total}")
    if info.first_de_id:
        print(f"   Primer DE.Id: {info.first_de_id}")
    if info.errors:
        print("   ❌ Errores:")
        for err in info.errors:
            print(f"      - {err}")
        return False
    print("   ✅ Estructura correcta (rLoteDE + xDE/rDE 1:1)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cuenta xDE/rDE dentro de lote.xml (desde ZIP o XML directo)",
    )
    parser.add_argument("--zip", type=Path, help="ZIP que contiene lote.xml")
    parser.add_argument("--xml", type=Path, help="Archivo XML directo (default: artifacts/last_lote.xml)")
    parser.add_argument("--label", type=str, default=None, help="Etiqueta opcional para el resumen")
    args = parser.parse_args()

    xml_bytes: Optional[bytes] = None
    label = args.label or ""

    if args.zip:
        try:
            xml_bytes = _load_xml_from_zip(args.zip)
            label = label or f"{args.zip}"
        except Exception as exc:
            print(f"❌ Error al leer ZIP: {exc}")
            return 1

    artifacts_dir = Path("artifacts")
    if xml_bytes is None and not args.xml and not args.zip:
        candidates = [
            artifacts_dir / "lote_zip_unknown.zip",
            artifacts_dir / "last_xde.zip",
            artifacts_dir / "last_lote.zip",
        ]
        zip_found = next((p for p in candidates if p.exists()), None)
        if zip_found:
            try:
                xml_bytes = _load_xml_from_zip(zip_found)
                label = label or f"{zip_found}"
            except Exception as exc:
                print(f"⚠️  No se pudo leer ZIP {zip_found}: {exc}")
        if xml_bytes is None:
            soap_path = artifacts_dir / "soap_last_request_SENT.xml"
            if soap_path.exists():
                try:
                    xml_bytes = _extract_from_soap(soap_path)
                    label = label or f"{soap_path} (xDE)"
                except Exception as exc:
                    print(f"⚠️  No se pudo extraer xDE de {soap_path}: {exc}")

    if xml_bytes is None:
        xml_path = args.xml or artifacts_dir / "last_lote.xml"
        try:
            xml_bytes = _load_xml(xml_path)
            label = label or f"{xml_path}"
        except Exception as exc:
            print(f"❌ Error al leer XML: {exc}")
            return 1

    ok = _analyze_source(xml_bytes, label)
    return 0 if ok and analyze_lote_bytes(xml_bytes)[0].rde_total >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
