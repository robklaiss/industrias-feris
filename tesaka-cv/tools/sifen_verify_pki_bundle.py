#!/usr/bin/env python3
"""
Verificador PKI completo para SIFEN:
1) Compara fingerprint del cert embebido en XML vs leaf del P12
2) Valida cadena con openssl verify (si disponible)
3) Ejecuta verificación criptográfica con sifen_signature_crypto_verify.py

Output mínimo a stdout, todo el detalle va a archivos en outdir.
"""
import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree


DS_NS = "http://www.w3.org/2000/09/xmldsig#"


def get_fingerprint_sha256(cert: x509.Certificate) -> str:
    """Calcula fingerprint SHA256 de un certificado."""
    der = cert.public_bytes(serialization.Encoding.DER)
    digest = hashlib.sha256(der).hexdigest()
    return digest.upper()


def extract_leaf_from_p12(p12_path: Path, password: bytes) -> x509.Certificate:
    """Extrae el certificado leaf del P12."""
    data = p12_path.read_bytes()
    key, cert, extras = pkcs12.load_key_and_certificates(
        data, password, backend=default_backend()
    )
    if cert is None:
        raise ValueError("No se encontró certificado leaf en el P12")
    return cert


def extract_embedded_cert_from_xml(xml_path: Path) -> x509.Certificate:
    """Extrae el certificado embebido en ds:X509Certificate del XML."""
    tree = etree.parse(str(xml_path))
    ns = {"ds": DS_NS}
    certs = tree.xpath("//ds:X509Certificate", namespaces=ns)
    if not certs:
        raise ValueError("No se encontró ds:X509Certificate en el XML")
    cert_b64 = certs[0].text.strip()
    cert_der = base64.b64decode(cert_b64)
    cert = x509.load_der_x509_certificate(cert_der, backend=default_backend())
    return cert


def save_cert_pem(cert: x509.Certificate, path: Path) -> None:
    """Guarda certificado en formato PEM."""
    pem = cert.public_bytes(serialization.Encoding.PEM)
    path.write_bytes(pem)


def run_openssl_verify(leaf_pem: Path, ca_pem: Path, outfile: Path) -> Tuple[bool, str]:
    """Ejecuta openssl verify y retorna (success, mensaje)."""
    if shutil.which("openssl") is None:
        msg = "openssl no disponible en PATH"
        outfile.write_text(msg)
        return False, msg
    
    cmd = ["openssl", "verify", "-CAfile", str(ca_pem), str(leaf_pem)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = f"Command: {' '.join(cmd)}\n"
        output += f"Exit code: {result.returncode}\n"
        output += f"Stdout:\n{result.stdout}\n"
        output += f"Stderr:\n{result.stderr}\n"
        outfile.write_text(output)
        
        success = result.returncode == 0 and "OK" in result.stdout
        msg = "OK" if success else "FAIL"
        return success, msg
    except Exception as e:
        msg = f"Error ejecutando openssl: {e}"
        outfile.write_text(msg)
        return False, msg


def run_crypto_verify(xml_path: Path, outfile: Path) -> Tuple[bool, str]:
    """Ejecuta sifen_signature_crypto_verify.py y retorna (success, mensaje)."""
    script = Path(__file__).parent / "sifen_signature_crypto_verify.py"
    if not script.exists():
        msg = f"Script no encontrado: {script}"
        outfile.write_text(msg)
        return False, msg
    
    python = sys.executable
    cmd = [python, str(script), str(xml_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = f"Command: {' '.join(cmd)}\n"
        output += f"Exit code: {result.returncode}\n"
        output += f"Stdout:\n{result.stdout}\n"
        output += f"Stderr:\n{result.stderr}\n"
        outfile.write_text(output)
        
        success = result.returncode == 0
        msg = "OK" if success else "FAIL"
        return success, msg
    except Exception as e:
        msg = f"Error ejecutando crypto_verify: {e}"
        outfile.write_text(msg)
        return False, msg


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verificador PKI completo para SIFEN"
    )
    parser.add_argument(
        "--xml",
        type=Path,
        default=Path("/tmp/sifen_preval/smoke_python_de_preval_signed.xml"),
        help="Path al XML firmado (default: /tmp/sifen_preval/smoke_python_de_preval_signed.xml)"
    )
    parser.add_argument(
        "--p12",
        type=Path,
        default=Path.home() / ".sifen/certs/F1T_65478.p12",
        help="Path al P12 (default: ~/.sifen/certs/F1T_65478.p12)"
    )
    parser.add_argument(
        "--password",
        type=str,
        help="Password del P12 (si no se provee, lee SIFEN_CERT_PASS)"
    )
    parser.add_argument(
        "--ca",
        type=Path,
        default=Path.home() / ".sifen/certs/ca-documenta.crt",
        help="Path al certificado CA (default: ~/.sifen/certs/ca-documenta.crt)"
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("/tmp/sifen_verify_run"),
        help="Directorio de salida (default: /tmp/sifen_verify_run)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Más logs a archivo (no a stdout)"
    )
    
    args = parser.parse_args()
    
    # Resolver password
    password = args.password
    if password is None:
        password = os.environ.get("SIFEN_CERT_PASS")
    if password is None:
        print("❌ ERROR: No se proveyó password del P12.")
        print("   Usar --password PASS o setear SIFEN_CERT_PASS")
        sys.exit(1)
    
    password_bytes = password.encode("utf-8")
    
    # Validar inputs
    if not args.xml.exists():
        print(f"❌ ERROR: XML no encontrado: {args.xml}")
        sys.exit(1)
    if not args.p12.exists():
        print(f"❌ ERROR: P12 no encontrado: {args.p12}")
        sys.exit(1)
    if not args.ca.exists():
        print(f"❌ ERROR: CA no encontrado: {args.ca}")
        sys.exit(1)
    
    # Crear outdir
    args.outdir.mkdir(parents=True, exist_ok=True)
    
    # Paths de salida
    p12_leaf_pem = args.outdir / "p12_leaf.pem"
    xml_embedded_pem = args.outdir / "xml_embedded.pem"
    fingerprints_txt = args.outdir / "fingerprints.txt"
    openssl_verify_txt = args.outdir / "openssl_verify.txt"
    crypto_verify_txt = args.outdir / "crypto_verify.txt"
    summary_json = args.outdir / "summary.json"
    
    results = {
        "xml": str(args.xml),
        "p12": str(args.p12),
        "ca": str(args.ca),
        "outdir": str(args.outdir),
        "fingerprint_match": False,
        "openssl_verify": "SKIP",
        "crypto_verify": "SKIP",
        "exit_code": 2
    }
    
    try:
        # 1) Extraer leaf del P12
        if args.debug:
            print(f"[DEBUG] Extrayendo leaf de P12: {args.p12}")
        p12_cert = extract_leaf_from_p12(args.p12, password_bytes)
        save_cert_pem(p12_cert, p12_leaf_pem)
        p12_fp = get_fingerprint_sha256(p12_cert)
        
        # 2) Extraer cert embebido del XML
        if args.debug:
            print(f"[DEBUG] Extrayendo cert embebido de XML: {args.xml}")
        xml_cert = extract_embedded_cert_from_xml(args.xml)
        save_cert_pem(xml_cert, xml_embedded_pem)
        xml_fp = get_fingerprint_sha256(xml_cert)
        
        # 3) Comparar fingerprints
        fingerprints_content = f"P12 leaf SHA256:    {p12_fp}\n"
        fingerprints_content += f"XML embedded SHA256: {xml_fp}\n"
        fingerprints_content += f"Match: {p12_fp == xml_fp}\n"
        fingerprints_txt.write_text(fingerprints_content)
        
        results["fingerprint_match"] = (p12_fp == xml_fp)
        results["p12_fingerprint"] = p12_fp
        results["xml_fingerprint"] = xml_fp
        
        # 4) Verificar con openssl
        if args.debug:
            print(f"[DEBUG] Ejecutando openssl verify")
        openssl_ok, openssl_msg = run_openssl_verify(p12_leaf_pem, args.ca, openssl_verify_txt)
        results["openssl_verify"] = openssl_msg
        
        # 5) Verificar firma criptográfica
        if args.debug:
            print(f"[DEBUG] Ejecutando crypto_verify")
        crypto_ok, crypto_msg = run_crypto_verify(args.xml, crypto_verify_txt)
        results["crypto_verify"] = crypto_msg
        
        # Determinar exit code
        if results["fingerprint_match"] and openssl_ok and crypto_ok:
            results["exit_code"] = 0
        else:
            results["exit_code"] = 2
        
    except Exception as e:
        results["error"] = str(e)
        results["exit_code"] = 1
        print(f"❌ ERROR: {e}")
    
    # Guardar summary
    summary_json.write_text(json.dumps(results, indent=2))
    
    # Imprimir resumen corto
    print("=" * 60)
    print("VERIFICACIÓN PKI SIFEN - RESUMEN")
    print("=" * 60)
    print(f"XML:     {args.xml}")
    print(f"P12:     {args.p12}")
    print(f"CA:      {args.ca}")
    print(f"Outdir:  {args.outdir}")
    print()
    print("Resultados:")
    print(f"  Fingerprint match: {'✅ OK' if results['fingerprint_match'] else '❌ FAIL'}")
    print(f"  OpenSSL verify:    {results['openssl_verify']}")
    print(f"  Crypto verify:     {results['crypto_verify']}")
    print()
    print("Archivos generados:")
    print(f"  - {p12_leaf_pem}")
    print(f"  - {xml_embedded_pem}")
    print(f"  - {fingerprints_txt}")
    print(f"  - {openssl_verify_txt}")
    print(f"  - {crypto_verify_txt}")
    print(f"  - {summary_json}")
    print()
    
    if results["exit_code"] == 0:
        print("✅ TODAS LAS VERIFICACIONES PASARON")
    else:
        print("❌ ALGUNAS VERIFICACIONES FALLARON")
        print(f"   Ver detalles en: {args.outdir}")
    
    sys.exit(results["exit_code"])


if __name__ == "__main__":
    main()
