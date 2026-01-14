#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recalcula dCarQR para un XML YA FIRMADO (sin tocar la firma).
- Lee datos desde el XML (CDC/Id, dFeEmiDE, receptor, totales, items, DigestValue)
- Calcula cHashQR = sha256( (qs_core) + CSC )  -> en minúsculas
- Reemplaza SOLO el contenido de <dCarQR>...</dCarQR> en el archivo (sin re-formatear el XML)

Uso:
  python3 tools/make_valid_de.py --in in.xml --out out.xml --idcsc 0001 --csc 'MI_CSC'
  # o por env:
  export SIFEN_IDCSC=0001
  export SIFEN_CSC='MI_CSC'
  python3 tools/make_valid_de.py --in in.xml --out out.xml
"""
import argparse
import binascii
import hashlib
import re
import sys
from html import unescape
from pathlib import Path
import xml.etree.ElementTree as ET

# Import safe configuration
from tools.safe_config import require_config, SifenConfigError

NS = {
    "s": "http://ekuatia.set.gov.py/sifen/xsd",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}

def to_hex_ascii(s: str) -> str:
    return binascii.hexlify(s.encode("utf-8")).decode("ascii")

def compute_dcarqr(xml_path: Path, idcsc: str, csc: str) -> str:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    de = root.find("s:DE", NS)
    if de is None:
        raise RuntimeError("No encuentro <DE> (namespace SIFEN).")

    cdc = de.attrib.get("Id", "")
    if not cdc:
        raise RuntimeError("No encuentro atributo Id en <DE> (CDC).")

    dFeEmiDE = de.findtext(".//s:dFeEmiDE", default="", namespaces=NS)
    if not dFeEmiDE:
        raise RuntimeError("No encuentro dFeEmiDE.")

    dRucRec = de.findtext(".//s:gDatRec/s:dRucRec", default="", namespaces=NS)
    dNumIDRec = de.findtext(".//s:gDatRec/s:dNumIDRec", default="", namespaces=NS)
    if dRucRec:
        rec_param = f"dRucRec={dRucRec}"
    elif dNumIDRec:
        rec_param = f"dNumIDRec={dNumIDRec}"
    else:
        raise RuntimeError("No encuentro dRucRec ni dNumIDRec en gDatRec.")

    dTotGralOpe = de.findtext(".//s:gTotSub/s:dTotGralOpe", default="", namespaces=NS)
    dTotIVA = de.findtext(".//s:gTotSub/s:dTotIVA", default="", namespaces=NS)
    if not dTotGralOpe or not dTotIVA:
        raise RuntimeError("No encuentro dTotGralOpe o dTotIVA en gTotSub.")

    cItems = str(len(de.findall(".//s:gDtipDE//s:gCamItem", NS)))

    digest_b64 = root.findtext(
        ".//ds:Signature/ds:SignedInfo/ds:Reference/ds:DigestValue",
        default="",
        namespaces=NS,
    )
    if not digest_b64:
        raise RuntimeError("No encuentro DigestValue dentro de Signature/SignedInfo/Reference.")

    # Base URL: si ya existe dCarQR, respetar su base
    existing = root.findtext(".//s:gCamFuFD/s:dCarQR", default="", namespaces=NS)
    base_url = "https://ekuatia.set.gov.py/consultas/qr"
    if existing:
        raw = unescape(existing)
        base_url = raw.split("?", 1)[0].strip() or base_url

    dFeEmi_hex = to_hex_ascii(dFeEmiDE)
    digest_hex = to_hex_ascii(digest_b64)

    qs_core = (
        f"nVersion=150"
        f"&Id={cdc}"
        f"&dFeEmiDE={dFeEmi_hex}"
        f"&{rec_param}"
        f"&dTotGralOpe={dTotGralOpe}"
        f"&dTotIVA={dTotIVA}"
        f"&cItems={cItems}"
        f"&DigestValue={digest_hex}"
        f"&IdCSC={idcsc}"
    )

    # Hash (según doc): sha256(qs_core + CSC), en minúsculas
    cHashQR = hashlib.sha256((qs_core + csc).encode("utf-8")).hexdigest().lower()

    full = f"{base_url}?{qs_core}&cHashQR={cHashQR}"
    # Para XML: escapar &
    return full.replace("&", "&amp;")

def replace_dcarqr_in_text(xml_text: str, new_dcarqr: str) -> str:
    pattern = re.compile(r"<dCarQR>.*?</dCarQR>", re.DOTALL)
    if not pattern.search(xml_text):
        raise RuntimeError("No encontré el tag <dCarQR>...</dCarQR> para reemplazar.")
    return pattern.sub(f"<dCarQR>{new_dcarqr}</dCarQR>", xml_text, count=1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="XML firmado de entrada")
    ap.add_argument("--out", dest="out", required=True, help="XML de salida (QR corregido)")
    ap.add_argument("--env", default=None, help="Ambiente (test|prod)")
    args = ap.parse_args()

    # Load configuration safely
    try:
        config = require_config(args.env)
        idcsc = config.get_idcsc()
        csc = config.get_csc()
    except SifenConfigError as e:
        print(f"❌ Error de configuración: {e}", file=sys.stderr)
        sys.exit(1)

    inp = Path(args.inp).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()

    print("🔐 Recalculando QR con configuración segura")
    print(f"   Ambiente: {config.env}")
    print(f"   IdCSC: {idcsc}")
    print(f"   CSC: {config.mask_csc()}")

    new_dcarqr = compute_dcarqr(inp, idcsc=idcsc, csc=csc)

    xml_text = inp.read_text(encoding="utf-8", errors="strict")
    new_text = replace_dcarqr_in_text(xml_text, new_dcarqr)
    out.write_text(new_text, encoding="utf-8")

    print("\n✅ QR actualizado correctamente")
    print(f"   Entrada: {inp}")
    print(f"   Salida: {out}")
    
    # Verify without showing full QR
    if "cHashQR=" in new_text:
        import re
        match = re.search(r'cHashQR=([^&]+)', new_text)
        if match:
            print(f"   Hash: {match.group(1)[:16]}...")

if __name__ == "__main__":
    main()
