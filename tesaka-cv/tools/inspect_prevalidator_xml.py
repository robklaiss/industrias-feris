#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import codecs
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from lxml import etree as ET

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
except ImportError:  # pragma: no cover - optional dependency
    x509 = None  # type: ignore
    NameOID = None  # type: ignore


NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NSMAP = {"ds": NS_DS}
DER_OUTPUT = Path("/tmp/preval_embedded.der")
UNDESIRED_KEYINFO_TAGS = {
    "X509SubjectName",
    "X509IssuerSerial",
    "X509IssuerName",
    "X509SKI",
    "KeyValue",
    "RSAKeyValue",
    "Modulus",
    "Exponent",
}
RUC_REGEX = re.compile(r"^RUC\d+-\d$")


def _local(tag: Optional[str]) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _read_clean_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    idx = raw.find(b"<")
    if idx == -1:
        raise ValueError("No se encontró el inicio de un XML ('<').")
    trimmed = raw[idx:]
    if trimmed.startswith(codecs.BOM_UTF8):
        trimmed = trimmed[len(codecs.BOM_UTF8) :]
    return trimmed


def _find_signature(root: ET._Element) -> Optional[ET._Element]:
    sig = root.find(".//{%s}Signature" % NS_DS)
    if sig is not None:
        return sig
    matches = root.xpath(".//*[local-name()='Signature' and namespace-uri()=$ds]", ds=NS_DS)  # type: ignore[arg-type]
    return matches[0] if matches else None


def _collect_keyinfo_flags(key_info: Optional[ET._Element]) -> List[str]:
    if key_info is None:
        return []
    hits: List[str] = []
    for elem in key_info.iter():
        local = _local(elem.tag)
        if local in UNDESIRED_KEYINFO_TAGS:
            hits.append(local)
    return hits


def _extract_certificate_bytes(signature: ET._Element) -> Optional[bytes]:
    x509_node = signature.find(".//{%s}X509Certificate" % NS_DS)
    if x509_node is None or not (x509_node.text or "").strip():
        return None
    normalized = "".join(x509_node.text.split())
    return base64.b64decode(normalized)


def _describe_signature(signature: ET._Element) -> Dict[str, Optional[str | List[str]]]:
    info: Dict[str, Optional[str | List[str]]] = {}
    def _attr(path: str) -> Optional[str]:
        node = signature.find(path)
        return node.get("Algorithm") if node is not None else None

    info["CanonicalizationMethod"] = _attr(".//{%s}CanonicalizationMethod" % NS_DS)
    info["SignatureMethod"] = _attr(".//{%s}SignatureMethod" % NS_DS)
    info["DigestMethod"] = _attr(".//{%s}DigestMethod" % NS_DS)

    transforms = [
        node.get("Algorithm")
        for node in signature.findall(".//{%s}Reference/{%s}Transforms/{%s}Transform" % (NS_DS, NS_DS, NS_DS))
        if node.get("Algorithm")
    ]
    info["Transforms"] = transforms

    reference = signature.find(".//{%s}Reference" % NS_DS)
    info["ReferenceURI"] = reference.get("URI") if reference is not None else None
    return info


def _describe_certificate(cert_der: bytes) -> Dict[str, object]:
    result: Dict[str, object] = {
        "subject": None,
        "issuer": None,
        "ruc_hits": [],
        "san_directory_serials": [],
    }
    if x509 is None or NameOID is None:  # pragma: no cover - optional dependency
        result["warning"] = (
            "cryptography no instalado; ejecuta: pip install cryptography para ver detalles del certificado"
        )
        return result

    cert = x509.load_der_x509_certificate(cert_der)
    subject_str = cert.subject.rfc4514_string()
    issuer_str = cert.issuer.rfc4514_string()
    result["subject"] = subject_str
    result["issuer"] = issuer_str

    ruc_hits: List[Tuple[str, str, bool]] = []

    subject_serial = _first_name_value(cert.subject, NameOID.SERIAL_NUMBER)
    if subject_serial:
        ruc_hits.append(("subject_serialNumber", subject_serial, bool(RUC_REGEX.match(subject_serial))))

    san_serials: List[str] = []
    try:
        san_extension = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        for directory_name in san_extension.value.get_values_for_type(x509.DirectoryName):
            value = _first_name_value(directory_name, NameOID.SERIAL_NUMBER)
            if value:
                san_serials.append(directory_name.rfc4514_string())
                ruc_hits.append(("san_directory_serialNumber", value, bool(RUC_REGEX.match(value))))
    except x509.ExtensionNotFound:
        pass

    result["san_directory_serials"] = san_serials
    result["ruc_hits"] = ruc_hits
    return result


def _first_name_value(name: Any, oid: Any) -> Optional[str]:
    for attribute in name:
        if attribute.oid == oid:
            return attribute.value.strip()
    return None


def _format_ruc_hits(hits: Sequence[Tuple[str, str, bool]]) -> str:
    if not hits:
        return "[]"
    parts = [f"({where}, {value}, {'OK' if is_ok else 'INVALID'})" for where, value, is_ok in hits]
    return "[" + "; ".join(parts) + "]"


def inspect(xml_path: Path, write_der: bool) -> None:
    data = _read_clean_bytes(xml_path)
    parser = ET.XMLParser(remove_blank_text=True)
    root = ET.fromstring(data, parser)

    print(f"ROOT={_local(root.tag)} ns={root.nsmap.get(None) or 'default'}")

    signature = _find_signature(root)
    if signature is None:
        print("Signature: NOT FOUND (xmlns ds)")
        return

    parent = signature.getparent()
    parent_local = _local(parent.tag if parent is not None else None)
    print("Signature: PRESENT")
    print(f" - Parent localname: {parent_local or 'UNKNOWN'}")

    sig_info = _describe_signature(signature)
    print(f" - CanonicalizationMethod: {sig_info.get('CanonicalizationMethod')}")
    print(f" - SignatureMethod: {sig_info.get('SignatureMethod')}")
    print(f" - DigestMethod: {sig_info.get('DigestMethod')}")
    transforms = sig_info.get("Transforms") or []
    if transforms:
        print(f" - Transforms: {', '.join(transforms)}")
    else:
        print(" - Transforms: none")
    print(f" - Reference URI: {sig_info.get('ReferenceURI')}")

    key_info = signature.find(".//{%s}KeyInfo" % NS_DS)
    undesired = _collect_keyinfo_flags(key_info)
    if undesired:
        print(f"KeyInfo undesirable tags: {', '.join(sorted(set(undesired)))}")
    else:
        print("KeyInfo undesirable tags: none")

    cert_der = _extract_certificate_bytes(signature)
    if not cert_der:
        print("Embedded X509Certificate: NOT FOUND")
        return

    cert_info = _describe_certificate(cert_der)
    warning = cert_info.get("warning")
    if warning:
        print(warning)
    subject = cert_info.get("subject")
    issuer = cert_info.get("issuer")
    print(f"Subject: {subject or 'N/A'}")
    print(f"Issuer: {issuer or 'N/A'}")

    san_dir = cert_info.get("san_directory_serials") or []
    if san_dir:
        print("SAN DirectoryName serials:")
        for entry in san_dir:
            print(f" - {entry}")
    else:
        print("SAN DirectoryName serials: none")

    ruc_hits = cert_info.get("ruc_hits") or []
    print(f"RUC_FOUND={_format_ruc_hits(ruc_hits)}")

    if write_der:
        DER_OUTPUT.write_bytes(cert_der)
        print(f"DER escrito en {DER_OUTPUT}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspector local para XML del Prevalidador SIFEN (DE / rDE / rEnviDe)."
    )
    parser.add_argument(
        "xml_path",
        help="Ruta al XML (por defecto $HOME/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml)",
        nargs="?",
        default=str(Path.home() / "Desktop" / "SIFEN_PREVALIDADOR_UPLOAD.xml"),
    )
    parser.add_argument("--write-der", action="store_true", help="Escribe el certificado DER en /tmp/preval_embedded.der")
    args = parser.parse_args(argv)

    xml_path = Path(args.xml_path).expanduser()
    if not xml_path.exists():
        print(f"ERROR: no se encontró el archivo {xml_path}", file=sys.stderr)
        return 1
    try:
        inspect(xml_path, args.write_der)
        return 0
    except Exception as exc:  # pragma: no cover - diagnostics friendly
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
