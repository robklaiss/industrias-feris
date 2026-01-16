#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
import inspect
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.xml_generator_v150 import create_rde_xml_v150
from app.sifen_client.xmlsec_signer import sign_de_with_p12


def _require(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise SystemExit(f"Falta env var requerida: {name}")
    return v


def _call_signer(xml, **kwargs):
    from app.sifen_client.xmlsec_signer import sign_de_with_p12
    # lxml no acepta str con declaración de encoding; debe ser bytes
    if isinstance(xml, str):
        xml = xml.encode('utf-8')
    return sign_de_with_p12(xml, **kwargs)

def main() -> None:
    # Forzar test por seguridad
    env = os.getenv("SIFEN_ENV", "test").strip().lower()
    if env != "test":
        raise SystemExit(f"Este generador es TEST-only. SIFEN_ENV={env!r}. Poné: export SIFEN_ENV=test")

    p12_path = _require("SIFEN_P12_PATH")
    p12_password = _require("SIFEN_P12_PASSWORD")

    # Datos básicos (podés ajustar si querés)
    emis_ruc_dv = _require("SIFEN_EMISOR_RUC")  # "4554737-8"
    ruc_num = "".join(c for c in emis_ruc_dv.split("-")[0] if c.isdigit()) or "4554737"

    timbrado = os.getenv("SIFEN_TIMBRADO", "12345678").strip()
    est = os.getenv("SIFEN_EST", "001").strip()
    pun = os.getenv("SIFEN_PUN", "001").strip()
    num = os.getenv("SIFEN_NUM", "0000001").strip()
    tipo_documento = os.getenv("SIFEN_TIPO_DOC", "1").strip()

    # CSC para QR (si tu signer lo usa vía env)
    _require("SIFEN_ID_CSC")
    _require("SIFEN_CSC")

    # Generar XML base (sin firma)
    now = datetime.now()
    fecha = now.strftime("%Y-%m-%d")
    hora = now.strftime("%H:%M:%S")

    xml = create_rde_xml_v150(
        ruc=ruc_num,
        timbrado=timbrado,
        establecimiento=est,
        punto_expedicion=pun,
        numero_documento=num,
        tipo_documento=tipo_documento,
        fecha=fecha,
        hora=hora,
        csc=os.getenv("SIFEN_CODSEG", "").strip() or None,
    )

    # Firmar + insertar QR (el signer se encarga del dCarQR / gCamFuFD)
    signed = _call_signer(xml, p12_path=p12_path, p12_password=p12_password)

    # Guardar
    out = Path.home() / "Desktop" / f"SIFEN_TEST_{now.strftime('%Y%m%d_%H%M%S')}.xml"
    if isinstance(signed, (bytes, bytearray)):
        out.write_bytes(signed)
    else:
        out.write_text(signed, encoding="utf-8")

    print("✅ XML TEST generado y firmado:")
    print(str(out))
    print("")
    print("Siguiente:")
    print(f"  python3 tools/inspect_qr.py '{out}' --modo 1")
    print("  # luego prevalidar con captcha fresco:")
    print(f"  python3 tools/prevalidate_http.py '{out}' --modo 1 --captcha 'VALOR_CAPTCHA_RECIEN_COPIADO'")


if __name__ == "__main__":
    main()
