#!/usr/bin/env python3
"""
Compara el último SOAP enviado (soap_raw_sent_lote_*.xml) contra artifacts/last_lote.xml.

Valida:
1. Coincidencia de DE.Id (CDC)
2. Opcionalmente muestra diff si difieren
"""

from __future__ import annotations

import argparse
import base64
import difflib
import sys
from io import BytesIO
from pathlib import Path
from typing import Optional
import zipfile

from lxml import etree


def _latest_soap_file(artifacts_dir: Path) -> Path:
    candidates = sorted(artifacts_dir.glob("soap_raw_sent_lote_*.xml"))
    if not candidates:
        raise FileNotFoundError(f"No se encontró soap_raw_sent_lote_*.xml en {artifacts_dir}")
    return candidates[-1]


def _extract_lote_from_soap(soap_path: Path) -> bytes:
    content = soap_path.read_bytes()
    root = etree.fromstring(content)
    xde = root.find(f".//{{http://ekuatia.set.gov.py/sifen/xsd}}xDE")
    if xde is None:
        xde = root.find(".//xDE")
    if xde is None or not xde.text or not xde.text.strip():
        raise RuntimeError(f"No se encontró xDE en {soap_path}")
    xde_b64 = "".join(xde.text.split())
    zip_bytes = base64.b64decode(xde_b64)
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
        if "lote.xml" not in zf.namelist():
            raise RuntimeError(f"ZIP en {soap_path} no contiene lote.xml (namelist={zf.namelist()})")
        return zf.read("lote.xml")


def _extract_de_meta(lote_bytes: bytes) -> dict[str, Optional[str]]:
    fields = {
        "de_id": None,
        "dNumTim": None,
        "dEst": None,
        "dPunExp": None,
        "dNumDoc": None,
        "dFeEmiDE": None,
        "dRucEm": None,
    }
    try:
        root = etree.fromstring(lote_bytes)
        rde = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}rDE")
        if rde is None:
            nodes = root.xpath(".//*[local-name()='rDE']")
            rde = nodes[0] if nodes else None
        if rde is None:
            return fields
        de = rde.find(".//{http://ekuatia.set.gov.py/sifen/xsd}DE")
        if de is None:
            nodes = rde.xpath(".//*[local-name()='DE']")
            de = nodes[0] if nodes else None
        if de is None:
            return fields
        fields["de_id"] = de.get("Id") or de.get("id")

        def _local_text(parent, local_name: str) -> Optional[str]:
            node = parent.find(f".//{{http://ekuatia.set.gov.py/sifen/xsd}}{local_name}")
            if node is not None and node.text:
                return node.text.strip()
            nodes = parent.xpath(f".//*[local-name()='{local_name}']")
            if nodes and nodes[0].text:
                return nodes[0].text.strip()
            return None

        fields["dNumTim"] = _local_text(de, "dNumTim")
        fields["dEst"] = _local_text(de, "dEst")
        fields["dPunExp"] = _local_text(de, "dPunExp")
        fields["dNumDoc"] = _local_text(de, "dNumDoc")
        fields["dFeEmiDE"] = _local_text(de, "dFeEmiDE")
        fields["dRucEm"] = _local_text(de, "dRucEm")
    except Exception:
        pass
    return fields


def _print_meta(label: str, meta: dict[str, Optional[str]]) -> None:
    print(
        f"{label}: "
        f"DE.Id={meta.get('de_id') or 'N/A'}, "
        f"Timbrado={meta.get('dNumTim') or 'N/A'}, "
        f"Est={meta.get('dEst') or 'N/A'}, "
        f"PunExp={meta.get('dPunExp') or 'N/A'}, "
        f"NumDoc={meta.get('dNumDoc') or 'N/A'}, "
        f"FechaEmi={meta.get('dFeEmiDE') or 'N/A'}, "
        f"RucEm={meta.get('dRucEm') or 'N/A'}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compara el último SOAP enviado contra artifacts/last_lote.xml"
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("artifacts"),
        help="Directorio donde buscar soap_raw_sent_lote_*.xml y last_lote.xml"
    )
    parser.add_argument(
        "--soap",
        type=Path,
        help="SOAP específico a comparar (default: último soap_raw_sent_lote_*.xml)"
    )
    parser.add_argument(
        "--last-lote",
        type=Path,
        help="Path personalizado a last_lote.xml (default: artifacts/last_lote.xml)"
    )
    parser.add_argument(
        "--show-diff",
        action="store_true",
        help="Muestra diff simple si los archivos difieren"
    )

    args = parser.parse_args()

    artifacts_dir = args.artifacts_dir
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    try:
        soap_path = args.soap or _latest_soap_file(artifacts_dir)
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        return 1

    last_lote_path = args.last_lote or (artifacts_dir / "last_lote.xml")
    if not last_lote_path.exists():
        print(f"❌ No existe {last_lote_path}")
        return 1

    try:
        soap_lote_bytes = _extract_lote_from_soap(soap_path)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"❌ No se pudo extraer lote del SOAP {soap_path}: {exc}")
        return 1

    last_lote_bytes = last_lote_path.read_bytes()

    soap_meta = _extract_de_meta(soap_lote_bytes)
    last_meta = _extract_de_meta(last_lote_bytes)

    print(f"SOAP: {soap_path}")
    print(f"LAST: {last_lote_path}")
    _print_meta("SOAP lote", soap_meta)
    _print_meta("Last lote", last_meta)

    if soap_lote_bytes == last_lote_bytes:
        print("✅ El lote enviado coincide con artifacts/last_lote.xml")
        return 0

    print("❌ El lote enviado NO coincide con artifacts/last_lote.xml")
    if soap_meta.get("de_id") != last_meta.get("de_id"):
        print(
            f"   DE.Id mismatch: SOAP={soap_meta.get('de_id') or 'N/A'} "
            f"vs LAST={last_meta.get('de_id') or 'N/A'}"
        )

    if args.show_diff:
        soap_text = soap_lote_bytes.decode("utf-8", errors="replace").splitlines()
        last_text = last_lote_bytes.decode("utf-8", errors="replace").splitlines()
        diff = difflib.unified_diff(last_text, soap_text, fromfile="last_lote.xml", tofile=str(soap_path))
        print("\n".join(list(diff)[:200]))

    return 1


if __name__ == "__main__":
    sys.exit(main())
