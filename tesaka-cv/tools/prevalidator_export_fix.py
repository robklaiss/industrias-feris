#!/usr/bin/env python3
from __future__ import annotations

import argparse
import codecs
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

DEFAULT_PROLOG = '<?xml version="1.0" encoding="UTF-8"?>'


def _trim_input(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(codecs.BOM_UTF8):
        data = data[len(codecs.BOM_UTF8) :]
    idx = data.find(b"<")
    if idx == -1:
        raise ValueError("No se encontró '<' en el XML de entrada.")
    data = data[idx:]
    return data.decode("utf-8")


def _extract_prolog(text: str) -> Tuple[str, str]:
    if text.startswith("<?xml"):
        end = text.find("?>")
        if end != -1:
            prolog = text[: end + 2]
            remainder = text[end + 2 :]
            return prolog.strip(), remainder
    return DEFAULT_PROLOG, text


def _extract_de_block(text: str) -> str:
    start = text.find("<DE")
    if start == -1:
        raise ValueError("No se encontró el inicio de <DE ...> en el XML.")
    end = text.find("</DE>", start)
    if end == -1:
        raise ValueError("No se encontró </DE> en el XML.")
    end += len("</DE>")
    return text[start:end]


def _normalize_inner(block: str, tag: str) -> Tuple[str, Optional[Tuple[int, int]]]:
    pattern = re.compile(
        rf"(<(?:[\w\d]+:)?{tag}[^>]*>)(.*?)(</(?:[\w\d]+:)?{tag}>)",
        re.DOTALL,
    )
    match = pattern.search(block)
    if not match:
        return block, None
    before = match.group(2)
    cleaned = "".join(before.split())
    replacement = f"{match.group(1)}{cleaned}{match.group(3)}"
    block = block[: match.start()] + replacement + block[match.end() :]
    return block, (len(before), len(cleaned))


def process(input_path: Path, output_path: Path) -> dict:
    trimmed = _trim_input(input_path)
    prolog, remainder = _extract_prolog(trimmed)
    de_block = _extract_de_block(remainder)

    signature_found = "<Signature" in de_block or "<ds:Signature" in de_block

    de_block, sig_stats = _normalize_inner(de_block, "SignatureValue")
    de_block, cert_stats = _normalize_inner(de_block, "X509Certificate")

    output_text = f"{prolog}\n{de_block}"
    output_path.write_text(output_text, encoding="utf-8")

    return {
        "input": str(input_path),
        "output": str(output_path),
        "bytes": len(output_text.encode("utf-8")),
        "de_found": True,
        "signature_found": signature_found,
        "sig_stats": sig_stats,
        "cert_stats": cert_stats,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exportador seguro para Prevalidador: extrae <DE> intacto y normaliza SignatureValue/X509Certificate."
    )
    parser.add_argument("input_xml", help="XML firmado (contiene <DE ... </DE>)")
    parser.add_argument(
        "output_xml",
        nargs="?",
        default=str(Path.home() / "Desktop" / "SIFEN_PREVALIDADOR_UPLOAD_FIX.xml"),
        help="Ruta de salida (default: Desktop/SIFEN_PREVALIDADOR_UPLOAD_FIX.xml)",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input_xml).expanduser()
    output_path = Path(args.output_xml).expanduser()

    if not input_path.exists():
        print(f"ERROR: no existe {input_path}", file=sys.stderr)
        return 1

    try:
        report = process(input_path, output_path)
    except Exception as exc:  # pragma: no cover - safety
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"IN:  {report['input']}")
    print(f"OUT: {report['output']}")
    print(f"bytes: {report['bytes']}")
    print(f"DE found: {'YES' if report['de_found'] else 'NO'}")
    print(f"Signature found: {'YES' if report['signature_found'] else 'NO'}")

    sig_stats = report["sig_stats"]
    if sig_stats:
        print(f"SignatureValue len before/after: {sig_stats[0]}/{sig_stats[1]}")
    else:
        print("SignatureValue len before/after: N/A")

    cert_stats = report["cert_stats"]
    if cert_stats:
        print(f"X509Certificate len before/after: {cert_stats[0]}/{cert_stats[1]}")
    else:
        print("X509Certificate len before/after: N/A")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
