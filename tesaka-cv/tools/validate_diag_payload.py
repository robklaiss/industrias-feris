from __future__ import annotations
from pathlib import Path
from lxml import etree
import base64, io, zipfile, sys, re

SOAP12_NS = "http://www.w3.org/2003/05/soap-envelope"

def ln(tag): return etree.QName(tag).localname
def ns(tag): return etree.QName(tag).namespace

def get_payload_root(doc_root):
    # Caso A: SOAP Envelope
    if ln(doc_root.tag) == "Envelope" and ns(doc_root.tag) == SOAP12_NS:
        body = doc_root.find(f".//{{{SOAP12_NS}}}Body")
        if body is None:
            raise SystemExit("❌ SOAP Envelope sin Body")
        # primer hijo elemento dentro del Body
        for ch in body:
            if isinstance(ch.tag, str):
                return ch
        raise SystemExit("❌ SOAP Body sin payload")
    # Caso B: ya es payload
    return doc_root

def safe_b64decode(s: str) -> bytes:
    b64 = "".join(s.split())
    # auto-padding si falta
    missing = (-len(b64)) % 4
    if missing:
        b64 += "=" * missing
    return base64.b64decode(b64)

def main():
    if len(sys.argv) < 2:
        raise SystemExit("Uso: .venv/bin/python tools/validate_diag_payload.py <xml>")
    p = Path(sys.argv[1])
    if not p.exists():
        raise SystemExit(f"❌ No existe: {p}")

    root = etree.fromstring(p.read_bytes())
    payload = get_payload_root(root)

    print(f"✅ Archivo: {p}")
    print(f"✅ Payload root: {payload.tag} (local={ln(payload.tag)})")

    if ln(payload.tag) != "rEnvioLote":
        print("⚠️  No es rEnvioLote. Igual continúo buscando xDE/dId si existen.")

    SIFEN_NS = ns(payload.tag)

    # soporta xsd: prefijo o default ns
    def find_child(local):
        # intenta con namespace
        if SIFEN_NS:
            el = payload.find(f"{{{SIFEN_NS}}}{local}")
            if el is not None:
                return el
        # fallback por localname
        for ch in payload:
            if isinstance(ch.tag, str) and ln(ch.tag) == local:
                return ch
        return None

    dId = find_child("dId")
    xDE = find_child("xDE")

    if dId is None or not (dId.text or "").strip():
        raise SystemExit("❌ Falta dId o está vacío")
    print(f"✅ dId: {dId.text.strip()}")

    if xDE is None or not (xDE.text or "").strip():
        raise SystemExit("❌ Falta xDE o está vacío")

    xde_txt = (xDE.text or "").strip()

    # Si está redacted, NO decodificar
    if "REDACTED" in xde_txt or "[" in xde_txt or "]" in xde_txt:
        print("⚠️  xDE está REDACTADO (no es Base64 real).")
        print("✅ Validación estructural OK. (Para validar ZIP real, usar el request NO redacted).")
        return

    # Si no está redacted: validar base64 -> zip
    try:
        raw = safe_b64decode(xde_txt)
    except Exception as e:
        raise SystemExit(f"❌ xDE no pudo decodificarse como Base64: {type(e).__name__}: {e}")

    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise SystemExit("❌ xDE decodifica pero NO es un ZIP válido")

    names = z.namelist()
    print(f"✅ ZIP OK. Entries: {names}")

    if "lote.xml" in names:
        lote = z.read("lote.xml")
        lote_root = etree.fromstring(lote)
        print(f"✅ lote.xml root: {lote_root.tag} (local={ln(lote_root.tag)})")
    else:
        print("⚠️  No existe lote.xml dentro del ZIP (revisar si el nombre es distinto).")

if __name__ == "__main__":
    main()
