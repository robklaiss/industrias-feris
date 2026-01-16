#!/usr/bin/env python3
"""
Descarga el WSDL de recibe-lote con retries y fallback a curl.

Uso:
  .venv/bin/python tools/fetch_wsdl.py --url https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl
"""
from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

import requests


def _download_with_requests(url: str, timeout: int, retries: int) -> bytes:
    session = requests.Session()
    headers = {
        "User-Agent": "tesaka-cv-wsdl-fetch/1.0",
        "Connection": "close",
    }
    backoff = 1
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                return resp.content
            raise RuntimeError(f"status={resp.status_code}, len={len(resp.content)}")
        except Exception as exc:
            if attempt == retries:
                raise
            time.sleep(backoff)
            backoff = min(backoff * 2, 8)
    raise RuntimeError("retries exhausted")


def _download_with_curl(url: str) -> bytes:
    cmd = [
        "curl",
        "--http1.1",
        "--retry",
        "3",
        "--retry-all-errors",
        "-L",
        "-s",
        url,
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False)
    if res.returncode != 0:
        raise RuntimeError(f"curl failed (rc={res.returncode}): {res.stderr.decode('utf-8', 'ignore')}")
    if not res.stdout:
        raise RuntimeError("curl returned empty body")
    return res.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga WSDL de recibe-lote con retries.")
    parser.add_argument(
        "--url",
        default="https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl",
        help="URL del WSDL",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/recibe-lote.wsdl.xml"),
        help="Archivo de salida",
    )
    parser.add_argument("--timeout", type=int, default=15, help="Timeout por intento (segundos)")
    parser.add_argument("--retries", type=int, default=3, help="Cantidad de reintentos con requests")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    content = None
    error = None
    try:
        content = _download_with_requests(args.url, timeout=args.timeout, retries=args.retries)
        print("✅ WSDL descargado con requests")
    except Exception as exc:
        error = str(exc)
        print(f"⚠️  requests falló: {exc}")
        try:
            content = _download_with_curl(args.url)
            print("✅ WSDL descargado con curl")
            error = None
        except Exception as exc2:
            error = f"curl fallback falló: {exc2}"

    if content is None:
        print(f"❌ No se pudo descargar el WSDL. Último error: {error}")
        return 1

    args.out.write_bytes(content)
    print(f"💾 Guardado en: {args.out} (bytes={len(content)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
