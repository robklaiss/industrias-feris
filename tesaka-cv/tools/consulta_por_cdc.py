#!/usr/bin/env python3
"""
Consulta estado de un DE por CDC usando SoapClient.consulta_de_por_cdc_raw.

Uso:
  .venv/bin/python -m tools.consulta_por_cdc --env test --cdc <CDC> [--dump-http]
"""
from __future__ import annotations

import argparse
import json
import datetime as dt
from pathlib import Path

from app.sifen_client.config import get_sifen_config
from app.sifen_client.soap_client import SoapClient
from app.sifen_client.exceptions import SifenClientError


def main() -> int:
    parser = argparse.ArgumentParser(description="Consulta DE por CDC (siConsDE).")
    parser.add_argument("--env", choices=["test", "prod"], default="test")
    parser.add_argument("--cdc", required=True, help="CDC a consultar")
    parser.add_argument("--dump-http", action="store_true", help="Guardar headers/body en resultado")
    args = parser.parse_args()

    config = get_sifen_config(env=args.env)
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    with SoapClient(config) as client:
        try:
            result = client.consulta_de_por_cdc_raw(args.cdc, dump_http=args.dump_http)
        except SifenClientError as exc:
            print(f"❌ Error consulta CDC: {exc}")
            return 1
        except Exception as exc:
            print(f"❌ Error inesperado: {exc}")
            return 1

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = artifacts_dir / f"consulta_por_cdc_{args.cdc}_{timestamp}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"💾 Guardado: {out_path}")
    print(
        f"Resultado: http_status={result.get('http_status')} "
        f"dCodRes={result.get('dCodRes')} "
        f"dMsgRes={result.get('dMsgRes')} "
        f"dProtAut={result.get('dProtAut')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
