#!/usr/bin/env python3
"""
Prueba rapida del GATE siConsRUC. Ejecuta consulta_ruc_raw con dump_http=True y
escribe artifacts/consulta_ruc_attempt_*.json por intento.
"""
import json
import os
import sys
import getpass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _ensure_cert_password() -> None:
    """Pide el password del P12 si no está en el entorno."""
    cert_path = (
        os.getenv("SIFEN_CERT_PATH")
        or os.getenv("SIFEN_SIGN_P12_PATH")
        or os.getenv("SIFEN_MTLS_P12_PATH")
    )
    if not cert_path:
        return

    existing = (
        os.getenv("SIFEN_CERT_PASS")
        or os.getenv("SIFEN_CERT_PASSWORD")
        or os.getenv("SIFEN_SIGN_P12_PASSWORD")
    )
    if existing:
        return

    pw = getpass.getpass("Password del certificado P12/mTLS: ")
    if not pw:
        return
    os.environ["SIFEN_CERT_PASS"] = pw
    os.environ.setdefault("SIFEN_CERT_PASSWORD", pw)
    os.environ.setdefault("SIFEN_SIGN_P12_PASSWORD", pw)


def main() -> int:
    from app.sifen_client.config import SifenConfig
    from app.sifen_client.soap_client import SoapClient

    _ensure_cert_password()

    env = os.getenv("SIFEN_ENV", "test")
    ruc = os.getenv("SIFEN_TEST_RUC_CONSULTA", "4554737-8")

    config = SifenConfig(env)
    with SoapClient(config) as client:
        resp = client.consulta_ruc_raw(ruc=ruc, dump_http=True)

    print(json.dumps(resp, indent=2, ensure_ascii=False))

    d_cod_res = str(resp.get("dCodRes") or "").strip()
    ok = bool(resp.get("ok")) or d_cod_res in ("0000", "0502")
    if ok:
        print("consulta_ruc_raw OK (GATE respondió habilitado)")
        return 0

    print("consulta_ruc_raw NO OK (revisar artifacts/consulta_ruc_attempt_*.json)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
