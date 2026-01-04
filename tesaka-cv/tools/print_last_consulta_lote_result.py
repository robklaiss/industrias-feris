#!/usr/bin/env python3
"""
Herramienta de diagnóstico para consultar rápidamente el resultado de la última consulta de lote.

- Busca automáticamente el archivo más reciente: artifacts/consulta_lote_*.xml (por mtime)
- Imprime exactamente 5 líneas:
  FILE: ...
  dFecProc: ...
  dEstRes: ...
  dCodRes: ...
  dMsgRes: ...

Notas:
- Soporta XML con namespaces/prefijos sin complicarse: usa regex ignorando prefijos.
- Rápido y seguro: lee el archivo y extrae tags sin colgarse.
- Exit code:
  - 0 si encontró un archivo (aunque falten campos)
  - 1 si no hay archivos o si --file no existe
"""

from __future__ import annotations

import sys
import argparse
import re
from pathlib import Path
from typing import Optional, Dict


PATTERN_GLOB_DEFAULT = "consulta_lote_*.xml"


def _extract_tag_value(xml_text: str, localname: str) -> Optional[str]:
    """
    Extrae el texto del primer tag cuyo localname coincida, ignorando prefijos de namespace.

    Ejemplos que matchea:
      <dCodRes>0160</dCodRes>
      <ns2:dCodRes>0160</ns2:dCodRes>
      <ns2:dCodRes attr="x">0160</ns2:dCodRes>

    Retorna None si no encuentra.
    """
    # Prefijo opcional: (\w+:)?
    # Atributos opcionales en el tag de apertura: \b[^>]*?
    # Contenido: (.*?) con DOTALL
    # Cierre: </(\w+:)?localname>
    pattern = re.compile(
        rf"<(?:\w+:)?{re.escape(localname)}\b[^>]*>(.*?)</(?:\w+:)?{re.escape(localname)}>",
        re.IGNORECASE | re.DOTALL,
    )
    m = pattern.search(xml_text)
    if not m:
        return None
    val = m.group(1)
    # Compactar whitespace sin "romper" contenido
    val = val.strip()
    # Si viene con saltos/espacios raros, lo normalizamos a un espacio
    val = re.sub(r"\s+", " ", val).strip()
    return val or None


def extract_fields_from_file(xml_file: Path) -> Dict[str, Optional[str]]:
    """
    Lee el XML y extrae campos principales.

    Si dCodRes/dMsgRes no existen pero existen dCodResLot/dMsgResLot, usa esos como fallback.
    """
    xml_text = xml_file.read_text(encoding="utf-8", errors="ignore")

    d_fec_proc = _extract_tag_value(xml_text, "dFecProc")
    d_est_res = _extract_tag_value(xml_text, "dEstRes")

    d_cod_res = _extract_tag_value(xml_text, "dCodRes")
    d_msg_res = _extract_tag_value(xml_text, "dMsgRes")

    # Fallback por si la respuesta usa campos del lote
    d_cod_res_lot = _extract_tag_value(xml_text, "dCodResLot")
    d_msg_res_lot = _extract_tag_value(xml_text, "dMsgResLot")

    if not d_cod_res and d_cod_res_lot:
        d_cod_res = d_cod_res_lot
    if not d_msg_res and d_msg_res_lot:
        d_msg_res = d_msg_res_lot

    return {
        "dFecProc": d_fec_proc,
        "dEstRes": d_est_res,
        "dCodRes": d_cod_res,
        "dMsgRes": d_msg_res,
    }


def find_latest_consulta_lote_file(artifacts_dir: Path, pattern: str = PATTERN_GLOB_DEFAULT) -> Optional[Path]:
    """
    Busca el archivo más reciente por mtime.
    """
    if not artifacts_dir.exists() or not artifacts_dir.is_dir():
        return None

    files = list(artifacts_dir.glob(pattern))
    if not files:
        return None

    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnóstico rápido del resultado de consulta de lote",
    )
    parser.add_argument("--file", type=Path, help="Archivo XML específico a analizar")
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path("artifacts"),
        help="Directorio donde buscar consulta_lote_*.xml (default: artifacts)",
    )

    args = parser.parse_args()

    if args.file:
        xml_file = args.file
        if not xml_file.exists():
            print(f"No existe el archivo: {xml_file}", file=sys.stderr)
            return 1
    else:
        xml_file = find_latest_consulta_lote_file(args.dir)
        if not xml_file:
            print(f"No hay {args.dir}/{PATTERN_GLOB_DEFAULT} todavía.", file=sys.stderr)
            return 1

    try:
        fields = extract_fields_from_file(xml_file)
    except Exception as e:
        print(f"ERROR: No pude leer/procesar {xml_file}: {e}", file=sys.stderr)
        return 1

    # IMPORTANTE: exactamente 5 líneas en stdout
    print(f"FILE: {xml_file}")
    print(f"dFecProc: {fields.get('dFecProc') or 'N/A'}")
    print(f"dEstRes: {fields.get('dEstRes') or 'N/A'}")
    print(f"dCodRes: {fields.get('dCodRes') or 'N/A'}")
    print(f"dMsgRes: {fields.get('dMsgRes') or 'N/A'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
