#!/usr/bin/env python3
"""
Extrae el último SOAP enviado (soap_raw_sent_lote_*.xml), inspecciona el ZIP/xDE y
verifica que lote.xml tenga rLoteDE + xDE -> rDE 1:1. También compara contra
artifacts/last_lote.xml para asegurar que se envió el archivo correcto.
"""
from __future__ import annotations

import argparse
import base64
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

try:
    import lxml.etree as etree
except ImportError as exc:  # pragma: no cover - friendly CLI error
    raise SystemExit(
        "❌ lxml no está instalado. Instale dependencias con: pip install lxml"
    ) from exc

from tools.lote_structure_utils import analyze_lote_bytes


def _find_latest_soap(artifacts_dir: Path) -> Optional[Path]:
    candidates = sorted(
        artifacts_dir.glob("soap_raw_sent_lote_*.xml"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _read_soap(path: Path) -> bytes:
    if not path or not path.exists():
        raise FileNotFoundError(f"Archivo SOAP no encontrado: {path}")
    return path.read_bytes()


def _extract_xde_bytes(soap_bytes: bytes) -> bytes:
    root = etree.fromstring(soap_bytes)
    xde_elem = root.find(".//*[local-name()='xDE']")
    if xde_elem is None or not (xde_elem.text or "").strip():
        raise RuntimeError("SOAP no contiene <xDE>")
    xde_clean = re.sub(r"\s+", "", xde_elem.text.strip())
    try:
        return base64.b64decode(xde_clean)
    except Exception as exc:
        raise RuntimeError(f"xDE no es Base64 válido: {exc}") from exc


def _extract_lote_from_zip(zip_bytes: bytes) -> bytes:
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
            if "lote.xml" not in zf.namelist():
                raise RuntimeError(f"ZIP no contiene lote.xml (archivos: {zf.namelist()})")
            return zf.read("lote.xml")
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"xDE no decodifica a ZIP válido: {exc}") from exc


def _compare_with_last_lote(current_bytes: bytes, artifacts_dir: Path) -> tuple[bool, Optional[str]]:
    last_path = artifacts_dir / "last_lote.xml"
    if not last_path.exists():
        return True, None
    existing = last_path.read_bytes()
    if existing == current_bytes:
        return True, None

    current_info, _ = analyze_lote_bytes(current_bytes)
    existing_info, _ = analyze_lote_bytes(existing)
    diag_content = (
        "Mismatch entre lote extraído del SOAP y artifacts/last_lote.xml\n"
        f"SOAP DE.Id: {current_info.first_de_id or 'N/A'}\n"
        f"last_lote DE.Id: {existing_info.first_de_id or 'N/A'}\n"
        f"SOAP bytes: {len(current_bytes)}\n"
        f"last_lote bytes: {len(existing)}\n"
    )
    diag_path = artifacts_dir / "diag_mismatch_last_lote_vs_sent.txt"
    diag_path.write_text(diag_content, encoding="utf-8")
    return False, str(diag_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida el lote extraído del último SOAP enviado (soap_raw_sent_lote_*.xml)",
    )
    parser.add_argument(
        "--soap",
        type=Path,
        help="Path al SOAP a inspeccionar (default: último artifacts/soap_raw_sent_lote_*.xml)",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("artifacts"),
        help="Directorio donde buscar artifacts (default: artifacts/)",
    )
    args = parser.parse_args()

    artifacts_dir = args.artifacts_dir
    try:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    soap_path = args.soap or _find_latest_soap(artifacts_dir)
    if not soap_path:
        print("❌ No se encontraron archivos soap_raw_sent_lote_*.xml")
        return 1

    print(f"📄 Analizando SOAP: {soap_path}")
    try:
        soap_bytes = _read_soap(soap_path)
        zip_bytes = _extract_xde_bytes(soap_bytes)
        lote_xml_bytes = _extract_lote_from_zip(zip_bytes)
    except Exception as exc:
        print(f"❌ Error al extraer ZIP/lote: {exc}")
        return 1

    try:
        info, _ = analyze_lote_bytes(lote_xml_bytes)
    except Exception as exc:
        print(f"❌ lote.xml inválido: {exc}")
        return 1

    print("\n🔍 lote.xml extraído del SOAP")
    print(f"   root: {info.root_local} (ns={info.root_namespace or 'VACÍO'})")
    print(f"   xDE count: {info.xde_count}")
    print(f"   rDE count: {info.rde_total}")
    if info.first_de_id:
        print(f"   Primer DE.Id: {info.first_de_id}")

    structure_errors = list(info.errors)
    if structure_errors:
        print("\n❌ Sanity falló:")
        for idx, message in enumerate(structure_errors, 1):
            print(f"   {idx}. {message}")
        return 1

    match, diag_path = _compare_with_last_lote(lote_xml_bytes, artifacts_dir)
    if not match:
        print("\n❌ El lote del SOAP difiere de artifacts/last_lote.xml")
        if diag_path:
            print(f"   Ver detalles en: {diag_path}")
        return 1

    extracted_path = artifacts_dir / "soap_last_lote.xml"
    try:
        extracted_path.write_bytes(lote_xml_bytes)
        print(f"\n💾 Guardado lote extraído en: {extracted_path}")
    except Exception:
        pass

    print("\n✅ Preflight OK: root rLoteDE, namespace correcto y xDE/rDE 1:1 (coincide con last_lote.xml)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
