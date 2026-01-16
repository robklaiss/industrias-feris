#!/usr/bin/env python3
"""
Extrae identidad (RUC/CI) desde un certificado P12 para ajustar el emisor del DE.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives.serialization import pkcs12


def calculate_dv(number: str) -> int:
    """Calcula DV paraguayo usando módulo 11 (pesos 2..11 cíclicos)."""
    if not number.isdigit():
        raise ValueError(f"Número inválido para DV: {number}")

    total = 0
    multiplier = 2
    for digit in reversed(number):
        total += int(digit) * multiplier
        multiplier += 1
        if multiplier > 11:
            multiplier = 2

    remainder = total % 11
    if remainder > 1:
        dv = 11 - remainder
    else:
        dv = 0
    return dv


def load_certificate(p12_path: Path, password: str):
    data = p12_path.read_bytes()
    key, cert, _ = pkcs12.load_key_and_certificates(data, password.encode("utf-8"))
    if cert is None:
        raise SystemExit("❌ El archivo P12 no contiene certificado.")
    return cert


def extract_identity_from_subject(subject_str: str) -> tuple[str, int, str]:
    """
    Analiza el subject y retorna (numero, dv, fuente) usando solo SUBJECT.
    """
    def search_ruc(text: str):
        patterns = [
            r"2\.5\.4\.5=RUC(\d+)-(\d)",
            r"\bRUC(\d+)-(\d)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                num, dv_str = match.group(1), match.group(2)
                return num, int(dv_str), "subject-ruc"
        return None

    ruc_result = search_ruc(subject_str)
    if ruc_result:
        return ruc_result

    def search_ci(text: str):
        match = re.search(r"\bCI(\d+)\b", text, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    maybe_ci = search_ci(subject_str)
    if maybe_ci:
        dv = calculate_dv(maybe_ci)
        return maybe_ci, dv, "subject-ci"

    raise ValueError("No se pudo extraer RUC/CI del subject del certificado.")


def find_ruc_info(cert) -> tuple[str, int, str]:
    """Devuelve (numero, dv, fuente) donde numero no incluye DV (solo SUBJECT)."""
    subject_str = cert.subject.rfc4514_string()
    try:
        return extract_identity_from_subject(subject_str)
    except ValueError as exc:
        raise SystemExit(f"❌ {exc}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extrae RUC/CI desde un certificado P12.")
    parser.add_argument("--p12", required=True, help="Ruta al certificado .p12/.pfx")
    parser.add_argument("--password", required=True, help="Password del P12")
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Solo imprime el JSON (sin mensajes informativos).",
    )
    return parser.parse_args()


def get_identity_from_cert(p12_path: str | Path, password: str) -> dict:
    """Retorna dict con ci/dv/ruc usando el subject del certificado."""
    p12 = Path(p12_path).expanduser()
    if not p12.exists():
        raise FileNotFoundError(f"No existe el certificado: {p12}")
    cert = load_certificate(p12, password)
    number, dv, source = find_ruc_info(cert)
    return {
        "ci": number,
        "dv": dv,
        "ruc": f"{number}-{dv}",
        "source": source,
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
    }


def main() -> int:
    args = parse_args()
    try:
        info = get_identity_from_cert(args.p12, args.password)
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        return 2
    except SystemExit as exc:
        return int(exc.code)

    if not args.json_only:
        print("=== Identidad del certificado ===")
        print(f"Subject: {info['subject']}")
        print(f"Issuer : {info['issuer']}")
        print(f"Identidad usada ({info['source']}): {info['ci']}-{info['dv']} (desde SUBJECT)")
        print("===============================")

    print(json.dumps({"ci": info["ci"], "dv": info["dv"], "ruc": info["ruc"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
