#!/usr/bin/env python3
"""Genera paquetes listos para subir al prevalidador oficial."""

from __future__ import annotations

import argparse
import base64
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from lxml import etree as ET

NS_SIFEN = "http://ekuatia.set.gov.py/sifen/xsd"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
DS_PREFIX = "ds"

OUT_DIR = Path("/tmp")
OUT_MAP = {
    "de": OUT_DIR / "preval_UPLOAD_DE.xml",
    "rde": OUT_DIR / "preval_UPLOAD_rDE.xml",
    "de_ds": OUT_DIR / "preval_UPLOAD_DE_ds.xml",
    "rde_ds": OUT_DIR / "preval_UPLOAD_rDE_ds.xml",
}
CERT_PEM = OUT_DIR / "preval_embedded_cert.pem"
CERT_DER = OUT_DIR / "preval_embedded_cert.der"
CERT_REPORT = OUT_DIR / "preval_embedded_cert_report.txt"
XMLSEC_LOG = OUT_DIR / "preval_xmlsec_verify.txt"
REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = REPO_ROOT / "artifacts" / "preval_pack"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

PATTERN_HINTS = [
    r"serialNumber=RUC[0-9]+-[0-9]",
    r"RUC[0-9]+-[0-9]",
    r"2\.16\.591",
    r"Subject Alternative Name",
]


def _parse(path: Path) -> ET._ElementTree:
    parser = ET.XMLParser(remove_blank_text=False)
    return ET.parse(str(path), parser)


def _local(tag: Optional[str]) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _first(root: ET._Element, local: str) -> Optional[ET._Element]:
    if _local(root.tag) == local:
        return root
    nodes = root.xpath(f".//*[local-name()='{local}' and namespace-uri()='{NS_SIFEN}']")
    return nodes[0] if nodes else None


def _find_signature(root: ET._Element) -> Optional[ET._Element]:
    nodes = root.xpath(".//*[local-name()='Signature' and namespace-uri()=$ns]", ns=NS_DS)
    return nodes[0] if nodes else None


def _clone(elem: ET._Element) -> ET._Element:
    return ET.fromstring(ET.tostring(elem))


def _ensure_rde(root: ET._Element) -> ET._Element:
    local = _local(root.tag)
    if local == "rDE":
        return root
    if local == "rEnviDe":
        rde = _first(root, "rDE")
        if rde is None:
            raise ValueError("rEnviDe no contiene rDE")
        return rde
    if local == "DE":
        wrapper = ET.Element(f"{{{NS_SIFEN}}}rDE")
        wrapper.append(_clone(root))
        return wrapper
    rde = _first(root, "rDE")
    if rde is None:
        raise ValueError("No se encontró rDE")
    return rde


def _extract_de_from_rde(rde_node: ET._Element) -> ET._Element:
    de = _first(rde_node, "DE")
    if de is None:
        raise ValueError("rDE no contiene DE")
    return de


def _force_no_bom(path: Path) -> None:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    data = data.lstrip()
    if data and data[0] != ord("<"):
        idx = data.find(b"<")
        if idx != -1:
            data = data[idx:]
    path.write_bytes(data)


def _write_xml(path: Path, element: ET._Element) -> None:
    ET.ElementTree(element).write(
        str(path),
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=True,
    )
    _force_no_bom(path)
    print(f"WROTE {path}")
    _copy_to_artifacts(path)


def _copy_to_artifacts(path: Path) -> None:
    dest = ARTIFACTS_DIR / path.name
    shutil.copy2(path, dest)
    print(f"COPIED -> {dest}")


def _convert_to_prefixed(root: ET._Element) -> ET._Element:
    def clone(node: ET._Element, parent_nsmap: Optional[Dict[str, str]] = None) -> ET._Element:
        tag = node.tag
        ns_uri = None
        local = tag
        if isinstance(tag, str) and tag.startswith("{"):
            ns_uri, local = tag[1:].split("}", 1)

        if ns_uri == NS_DS:
            prefix = DS_PREFIX
            nsmap = {prefix: NS_DS}
            qname = ET.QName(NS_DS, local)
            new_node = ET.Element(qname, nsmap=nsmap)
        else:
            nsmap = node.nsmap if node.nsmap else parent_nsmap
            new_node = (
                ET.Element(ET.QName(ns_uri, local), nsmap=nsmap)
                if ns_uri
                else ET.Element(local, nsmap=nsmap)
            )

        for attr, value in node.attrib.items():
            new_node.set(attr, value)

        new_node.text = node.text
        new_node.tail = node.tail

        for child in node:
            new_node.append(clone(child, nsmap))

        return new_node

    converted = clone(root)
    if DS_PREFIX not in (converted.nsmap or {}):
        attr = f"{{http://www.w3.org/2000/xmlns/}}{DS_PREFIX}"
        converted.set(attr, NS_DS)
    return converted


def _call_verify(path: Path) -> None:
    print(f"---- VERIFY {path} ----")
    proc = subprocess.run(
        [sys.executable, "-m", "tools.verify_sig_location", str(path)],
        capture_output=True,
        text=True,
    )
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)


def _count_signature_positions(de_node: ET._Element) -> str:
    sig = _find_signature(de_node)
    if sig is None:
        return "no Signature found"
    idx_sig = -1
    idx_qr = -1
    for idx, child in enumerate(list(de_node)):
        if child is sig:
            idx_sig = idx
        if _local(child.tag) == "gCamFuFD" and idx_qr == -1:
            idx_qr = idx
    if idx_sig == -1:
        return "Signature not direct child"
    if idx_qr == -1:
        return f"Signature idx={idx_sig}, gCamFuFD missing"
    relation = idx_sig - idx_qr
    if relation == -1:
        return "Signature immediately before gCamFuFD"
    return f"Signature idx={idx_sig}, gCamFuFD idx={idx_qr}"


def _extract_cert_from_signature(root: ET._Element) -> bytes:
    sig = _find_signature(root)
    if sig is None:
        raise ValueError("No Signature found para extraer certificado")
    x509_data = sig.find(f".//{{{NS_DS}}}X509Certificate")
    if x509_data is None or not (x509_data.text or "").strip():
        raise ValueError("X509Certificate vacío o no encontrado")
    b64 = "".join(x509_data.text.split())
    return base64.b64decode(b64)


def _generate_cert_reports(cert_der: bytes) -> None:
    CERT_DER.write_bytes(cert_der)
    CERT_PEM.write_bytes(
        b"-----BEGIN CERTIFICATE-----\n"
        + base64.encodebytes(cert_der)
        + b"-----END CERTIFICATE-----\n"
    )
    print(f"WROTE {CERT_DER}")
    print(f"WROTE {CERT_PEM}")
    _copy_to_artifacts(CERT_DER)
    _copy_to_artifacts(CERT_PEM)

    openssl = subprocess.run(
        ["which", "openssl"], capture_output=True, text=True, check=False
    )
    if openssl.returncode != 0:
        CERT_REPORT.write_text("openssl no disponible en PATH\n")
        print("openssl no disponible; no se generó reporte detallado")
        return

    cmd = [
        openssl.stdout.strip(),
        "x509",
        "-inform",
        "DER",
        "-in",
        str(CERT_DER),
        "-noout",
        "-text",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    report_text = result.stdout
    summary_lines = []
    for pattern in PATTERN_HINTS:
        matches = re.findall(pattern, report_text, flags=re.MULTILINE)
        summary_lines.append(f"{pattern}: {len(matches)} match(es)")
    CERT_REPORT.write_text("\n".join(summary_lines) + "\n\n" + report_text)
    print(f"WROTE {CERT_REPORT}")
    _copy_to_artifacts(CERT_REPORT)


def _maybe_xmlsec_verify(path: Path) -> None:
    xmlsec = subprocess.run(["which", "xmlsec1"], capture_output=True, text=True, check=False)
    if xmlsec.returncode != 0:
        print("xmlsec1 no disponible; omitiendo verificación xmlsec")
        return
    cmd = [
        xmlsec.stdout.strip(),
        "--verify",
        "--enabled-reference-uris",
        "empty,same-doc",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    XMLSEC_LOG.write_text(result.stdout + "\n" + result.stderr)
    print(f"xmlsec1 verify exit={result.returncode} log={XMLSEC_LOG}")
    _copy_to_artifacts(XMLSEC_LOG)


def preval_pack(input_path: Path) -> None:
    tree = _parse(input_path)
    root = tree.getroot()

    rde_node = _ensure_rde(root)
    de_node = _extract_de_from_rde(rde_node)

    outputs: Dict[str, ET._Element] = {}
    outputs["rde"] = _clone(rde_node)
    outputs["de"] = _clone(de_node)

    outputs["rde_ds"] = _convert_to_prefixed(outputs["rde"])
    outputs["de_ds"] = _convert_to_prefixed(outputs["de"])

    for key, element in outputs.items():
        _write_xml(OUT_MAP[key], element)
        _call_verify(OUT_MAP[key])
        if key in ("de", "de_ds"):
            print(f"{OUT_MAP[key]} placement: {_count_signature_positions(element)}")

    cert_der = _extract_cert_from_signature(outputs["rde"])
    _generate_cert_reports(cert_der)

    _maybe_xmlsec_verify(OUT_MAP["de"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera paquetes para prevalidador SIFEN")
    parser.add_argument("input", type=Path, help="Ruta al XML firmado (rEnviDe/rDE/DE)")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input no encontrado: {args.input}", file=sys.stderr)
        sys.exit(2)

    preval_pack(args.input)


if __name__ == "__main__":
    main()
