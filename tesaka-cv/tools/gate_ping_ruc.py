#!/usr/bin/env python3
"""
Ping sencillo al GATE (siConsRUC) para diagnosticar SOAPAction/transport.

Uso:
  .venv/bin/python -m tools.gate_ping_ruc --env test --ruc 4554737
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.sifen_client.config import get_sifen_config
from app.sifen_client.soap_client import SoapClient
from app.sifen_client.exceptions import SifenClientError


def main() -> int:
    parser = argparse.ArgumentParser(description="Ping siConsRUC con dump de artifacts.")
    parser.add_argument("--env", choices=["test", "prod"], default="test")
    parser.add_argument("--ruc", required=True, help="RUC a consultar")
    parser.add_argument("--dump-http", action="store_true", help="Guardar request/response y headers")
    args = parser.parse_args()

    config = get_sifen_config(env=args.env)
    artifacts = Path("artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)

    with SoapClient(config) as client:
        try:
            start = time.time()
            result = client.consulta_ruc_raw(args.ruc, dump_http=args.dump_http)
            elapsed_ms = int((time.time() - start) * 1000)
            result["elapsed_ms_total"] = elapsed_ms
        except SifenClientError as exc:
            print(f"❌ Error consulta RUC: {exc}")
            return 1
        except Exception as exc:
            print(f"❌ Error inesperado: {exc}")
            return 1

    # Guardar artifacts
    ts = time.strftime("%Y%m%d_%H%M%S")
    (artifacts / "gate_last_request.xml").write_text(
        result.get("sent_xml", ""), encoding="utf-8"
    )
    (artifacts / "gate_last_response.xml").write_text(
        result.get("raw_xml", ""), encoding="utf-8"
    )
    meta = {
        "endpoint": result.get("endpoint"),
        "http_status": result.get("http_status"),
        "sent_headers": result.get("sent_headers"),
        "received_headers": result.get("received_headers"),
        "soapaction_mode": result.get("soapaction_mode"),
        "elapsed_ms": result.get("elapsed_ms", result.get("elapsed_ms_total")),
    }
    (artifacts / "gate_last_http_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Endpoint: {meta.get('endpoint')}")
    print(f"HTTP status: {meta.get('http_status')}")
    print(
        f"SOAPAction mode: {meta.get('soapaction_mode')} "
        f"Content-Type: {meta.get('sent_headers', {}).get('Content-Type') if meta.get('sent_headers') else 'N/A'} "
        f"SOAPAction header: {meta.get('sent_headers', {}).get('SOAPAction') if meta.get('sent_headers') else 'N/A'}"
    )
    if "dCodRes" in result or "dMsgRes" in result:
        print(f"dCodRes: {result.get('dCodRes')} dMsgRes: {result.get('dMsgRes')}")
    else:
        print("dCodRes/dMsgRes no encontrados en respuesta.")
    print(f"Guardado artifacts en {artifacts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
