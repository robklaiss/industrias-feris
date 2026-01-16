#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import subprocess
import sys
from pathlib import Path
from typing import Optional

from lxml import etree as ET

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
XMLSEC_LOG = Path("/tmp/prevalidator_xmlsec_verify.log")


def _local(tag: Optional[str]) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_de_id(root: ET._Element) -> str:
    ns = {"sifen": SIFEN_NS}
    de_nodes = root.xpath("//sifen:DE", namespaces=ns)
    if not de_nodes:
        de_nodes = root.xpath("//DE")
    if not de_nodes:
        raise ValueError("No se encontró DE")
    de = de_nodes[0]
    de_id = de.get("Id") or de.get("id")
    if not de_id:
        raise ValueError("DE no tiene atributo Id")
    return de_id


def _extract_x509_pem(root: ET._Element) -> Optional[bytes]:
    ns = {"ds": DS_NS}
    cert_nodes = root.xpath("//*[local-name()='X509Certificate' and namespace-uri()=$ds]", ds=DS_NS)
    if not cert_nodes:
        return None
    b64 = (cert_nodes[0].text or "").strip()
    if not b64:
        return None
    b64 = "".join(b64.split())
    der = base64.b64decode(b64)
    pem_body = base64.encodebytes(der).replace(b"\n", b"\n")
    return b"-----BEGIN CERTIFICATE-----\n" + pem_body + b"-----END CERTIFICATE-----\n"


def _which_xmlsec1() -> Optional[str]:
    proc = subprocess.run(["which", "xmlsec1"], capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def verify_xmlsec(xml_path: Path) -> int:
    xmlsec1 = _which_xmlsec1()
    if not xmlsec1:
        print("xmlsec1 no está instalado.")
        print("Instalá en macOS:")
        print("  brew install libxml2 libxslt xmlsec1")
        return 2

    data = xml_path.read_bytes()
    parser = ET.XMLParser(remove_blank_text=False)
    root = ET.fromstring(data, parser=parser)
    root_local = _local(root.tag)

    de_id = _extract_de_id(root)
    pem = _extract_x509_pem(root)

    cert_path = None
    if pem:
        cert_path = Path("/tmp/prevalidator_xmlsec_pubkey.pem")
        cert_path.write_bytes(pem)

    # Use explicit cert pubkey when possible to avoid KEY-NOT-FOUND.
    # NOTE: xmlsec1 expects the node name as it appears in the XML (QName),
    # not Clark notation. Our DE is typically in the default namespace, so it
    # appears as "<DE ...>".
    cmd = [
        xmlsec1,
        "--verify",
        "--enabled-reference-uris",
        "empty,same-doc",
        "--enabled-key-data",
        "x509",
        "--id-attr:Id",
        "DE",
    ]
    if cert_path:
        cmd += ["--pubkey-cert-pem", str(cert_path)]
    cmd += [str(xml_path)]

    result = subprocess.run(cmd, capture_output=True, text=True)

    try:
        XMLSEC_LOG.write_text(
            "CMD: " + " ".join(cmd) + "\n\nSTDOUT:\n" + (result.stdout or "") + "\n\nSTDERR:\n" + (result.stderr or ""),
            encoding="utf-8",
        )
    except Exception:
        pass

    print(f"ROOT={root_local}")
    print(f"DE Id={de_id}")
    print(f"xmlsec1 cmd={' '.join(cmd)}")

    if result.returncode == 0:
        print("SIGNATURE OK (xmlsec1)")
        return 0

    print("SIGNATURE FAIL (xmlsec1)")
    print(f"log: {XMLSEC_LOG}")
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return 1


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Verifica firma XMLDSig usando xmlsec1 (registro de Id y cert embebido).")
    ap.add_argument("xml_path", help="Ruta al XML firmado")
    args = ap.parse_args(argv)

    xml_path = Path(args.xml_path).expanduser()
    if not xml_path.exists():
        print(f"ERROR: no existe {xml_path}", file=sys.stderr)
        return 1

    try:
        return verify_xmlsec(xml_path)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
