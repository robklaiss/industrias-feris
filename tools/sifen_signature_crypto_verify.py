#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SIFEN - Verificación criptográfica de XMLDSig (RSA-SHA256) para rDE/DE.

Uso:
  .venv/bin/python tools/sifen_signature_crypto_verify.py /path/al.xml

Exit codes:
  0 = OK
  2 = FAIL
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

from lxml import etree

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
except Exception as e:
    print("❌ Falta cryptography. Instalá: pip install cryptography")
    raise

DUMMY_RE = re.compile(r"dummy_(digest|signature|certificate)", re.IGNORECASE)

NS = {
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _parse_xml(path: str) -> etree._ElementTree:
    parser = etree.XMLParser(
        remove_blank_text=False,  # NO tocar whitespace
        resolve_entities=False,
        no_network=True,
        huge_tree=True,
        recover=False,
    )
    return etree.parse(path, parser)

def _string_xpath(doc: etree._ElementTree, xp: str) -> str:
    return str(doc.xpath(f"string({xp})", namespaces=NS)).strip()

def _find_signature(doc: etree._ElementTree) -> etree._Element | None:
    sigs = doc.xpath("//ds:Signature", namespaces=NS)
    return sigs[0] if sigs else None

def _b64_clean(s: str) -> str:
    # quita whitespace/newlines dentro del base64
    return re.sub(r"\s+", "", s)

def _cert_from_embedded_b64(x509_b64: str) -> x509.Certificate:
    x509_b64 = _b64_clean(x509_b64)
    der = base64.b64decode(x509_b64, validate=False)
    return x509.load_der_x509_certificate(der)

def _extract_cert_pem(doc: etree._ElementTree) -> str:
    """Extrae el certificado embebido y lo devuelve en formato PEM"""
    xc = _string_xpath(doc, "//ds:X509Certificate")
    xc_clean = _b64_clean(xc)
    
    # Formatear con saltos cada 64 caracteres
    lines = []
    for i in range(0, len(xc_clean), 64):
        lines.append(xc_clean[i:i+64])
    
    pem = "-----BEGIN CERTIFICATE-----\n"
    pem += "\n".join(lines)
    pem += "\n-----END CERTIFICATE-----\n"
    return pem

def _print_basic_report(doc: etree._ElementTree, xml_text: str) -> None:
    sig = _find_signature(doc)
    if sig is None:
        print("❌ No se encontró <ds:Signature> en el XML.")
        raise SystemExit(2)

    parent = sig.getparent().tag if sig.getparent() is not None else None
    print(f"Signature parent: {parent}")

    dv = _string_xpath(doc, "//ds:DigestValue")
    sv = _string_xpath(doc, "//ds:SignatureValue")
    xc = _string_xpath(doc, "//ds:X509Certificate")

    print(f"DigestValue len:    {len(_b64_clean(dv))}  starts: {dv[:12]}")
    print(f"SignatureValue len: {len(_b64_clean(sv))}  starts: {sv[:12]}")
    print(f"X509Certificate len:{len(_b64_clean(xc))}  starts: {xc[:12]}")

    # hard fail dummy
    if DUMMY_RE.search(xml_text) or DUMMY_RE.search(dv) or DUMMY_RE.search(sv) or DUMMY_RE.search(xc):
        print("❌ Detectado dummy_* (esto NO es una firma real).")
        raise SystemExit(2)

    # chequeo rápido "parece real"
    if len(_b64_clean(dv)) < 20 or len(_b64_clean(sv)) < 200 or not _b64_clean(xc).startswith("MI"):
        print("❌ La firma parece incompleta/placeholder (tamaños o certificado no parecen reales).")
        raise SystemExit(2)

    # validez temporal del certificado embebido
    try:
        cert = _cert_from_embedded_b64(xc)
        # Usar not_valid_before_utc y not_valid_after_utc para evitar deprecation warnings
        nb = cert.not_valid_before_utc
        na = cert.not_valid_after_utc
        now = _now_utc()
        print(f"Cert subject: {cert.subject.rfc4514_string()}")
        print(f"Cert issuer:  {cert.issuer.rfc4514_string()}")
        print(f"Cert valid:   {nb}  ->  {na}")
        if not (nb <= now <= na):
            print("❌ Certificado embebido está fuera de vigencia (fecha/hora).")
            raise SystemExit(2)
    except SystemExit:
        raise
    except Exception as e:
        print(f"❌ No se pudo parsear/validar el certificado embebido: {e}")
        raise SystemExit(2)

def _verify_with_signxml(xml_path: str) -> bool:
    try:
        from signxml import XMLVerifier  # type: ignore
    except Exception:
        return False

    try:
        # Signxml verifica SignatureValue vs datos canónicos + cert embebido (X509Data)
        XMLVerifier().verify(xml_path)
        print("✅ signxml: verificación criptográfica OK")
        return True
    except Exception as e:
        print(f"❌ signxml: firma inválida -> {e}")
        return True  # fue posible intentar; devolvemos True para no caer a otro método "sin necesidad"

def _verify_with_xmlsec1(xml_path: str) -> bool:
    if shutil.which("xmlsec1") is None:
        return False

    # xmlsec necesita saber qué atributo es ID para las referencias URI="#..."
    # En SIFEN el atributo es Id del elemento DE.
    cmd = ["xmlsec1", "--verify", "--id-attr:Id", "DE", xml_path]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0:
            print("✅ xmlsec1: verificación criptográfica OK")
            return True
        else:
            print("❌ xmlsec1: firma inválida")
            if p.stdout.strip():
                print("xmlsec1 stdout:\n" + p.stdout.strip())
            if p.stderr.strip():
                print("xmlsec1 stderr:\n" + p.stderr.strip())
            return True  # se intentó
    except Exception as e:
        print(f"❌ xmlsec1: error ejecutando verificación: {e}")
        return True  # se intentó

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("xml_path", help="Ruta al XML a verificar (firmado)")
    ap.add_argument("--debug", action="store_true", help="Modo debug (muestra comandos y paths)")
    args = ap.parse_args()

    xml_path = os.path.abspath(os.path.expanduser(args.xml_path))
    if not os.path.isfile(xml_path):
        print(f"❌ No existe el archivo: {xml_path}")
        return 2

    xml_text = open(xml_path, "rb").read().decode("utf-8", errors="ignore")
    if DUMMY_RE.search(xml_text):
        print("❌ Detectado dummy_* en el XML (hard fail).")
        return 2

    try:
        doc = _parse_xml(xml_path)
    except Exception as e:
        print(f"❌ XML mal formado / no se pudo parsear: {e}")
        return 2

    try:
        _print_basic_report(doc, xml_text)
    except SystemExit as se:
        return int(se.code)

    # Extraer certificado PEM embebido
    cert_pem = _extract_cert_pem(doc)
    
    # 1) signxml (preferido)
    signxml_available = False
    try:
        from signxml import XMLVerifier  # type: ignore
        signxml_available = True
    except Exception:
        pass
    
    if signxml_available:
        try:
            # Serializar XML a bytes (sin pretty_print)
            xml_bytes = etree.tostring(doc, encoding="utf-8", xml_declaration=True, pretty_print=False)
            
            if args.debug:
                print(f"[DEBUG] signxml: xml_bytes len={len(xml_bytes)}")
                print(f"[DEBUG] signxml: cert_pem len={len(cert_pem)}")
            
            # Verificar con signxml usando el certificado embebido
            XMLVerifier().verify(
                xml_bytes,
                x509_cert=cert_pem,
                id_attribute="Id",
            )
            print("✅ signxml: verificación criptográfica OK")
            print("✅ VERIFICACIÓN CRIPTOGRÁFICA COMPLETA OK")
            return 0
        except Exception as e:
            print(f"❌ signxml: firma inválida -> {e}")
            print("⚠️  Intentando con xmlsec1...")
    
    # 2) xmlsec1 (alternativa)
    if shutil.which("xmlsec1") is None:
        print("❌ No puedo verificar criptográficamente porque falta signxml y falta xmlsec1.")
        print("   Instalá UNO de estos:")
        print("   - pip install signxml")
        print("   - brew install xmlsec1  (en mac)")
        return 2
    
    # Escribir certificado PEM a archivo temporal
    cert_pem_path = "/tmp/sifen_embedded_cert.pem"
    with open(cert_pem_path, "w") as f:
        f.write(cert_pem)
    
    try:
        cmd = [
            "xmlsec1", "--verify",
            "--enabled-key-data", "x509",
            "--pubkey-cert-pem", cert_pem_path,
            "--id-attr:Id", "DE",
            xml_path
        ]
        
        if args.debug:
            print(f"[DEBUG] xmlsec1 command: {' '.join(cmd)}")
            print(f"[DEBUG] cert_pem_path: {cert_pem_path}")
        
        p = subprocess.run(cmd, capture_output=True, text=True)
        
        if p.returncode == 0:
            print("✅ xmlsec1: verificación criptográfica OK")
            print("✅ VERIFICACIÓN CRIPTOGRÁFICA COMPLETA OK")
            return 0
        else:
            print("❌ xmlsec1: firma inválida")
            if p.stdout.strip():
                print("xmlsec1 stdout:")
                print(p.stdout.strip())
            if p.stderr.strip():
                print("xmlsec1 stderr:")
                print(p.stderr.strip())
            print("❌ VERIFICACIÓN CRIPTOGRÁFICA COMPLETA FAIL")
            return 2
    finally:
        # Limpiar archivo temporal
        if os.path.exists(cert_pem_path):
            os.unlink(cert_pem_path)

if __name__ == "__main__":
    raise SystemExit(main())
