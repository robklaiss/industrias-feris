#!/usr/bin/env python3
"""
Herramienta CLI para inspeccionar nodos QR dentro de XML SIFEN (rLoteDE/rDE).

Extrae metadatos clave y parámetros de la URL del QR para ayudar a diagnosticar
errores como el 2502 "URL de consulta de código QR es inválida".
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qsl

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.qr_inspector import extract_dcar_qr, detect_qr_env, extract_qr_params
from app.sifen_client.env_validator import get_current_env, env_to_modo, assert_test_env

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"


def _get_local_name(tag: Optional[str]) -> Optional[str]:
    if tag is None:
        return None
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _get_namespace(tag: Optional[str]) -> Optional[str]:
    if tag is None or not tag.startswith("{"):
        return None
    return tag.split("}", 1)[0][1:]


def _iter_elements(root: ET.Element, local_name: str, namespace: Optional[str] = None):
    for elem in root.iter():
        if _get_local_name(elem.tag) != local_name:
            continue
        if namespace and _get_namespace(elem.tag) != namespace:
            continue
        yield elem


def _find_first(root: ET.Element, local_name: str, namespace: Optional[str] = None) -> Optional[ET.Element]:
    for elem in _iter_elements(root, local_name, namespace):
        return elem
    return None


def _extract_text(element: Optional[ET.Element]) -> Optional[str]:
    if element is None or element.text is None:
        return None
    text = element.text.strip()
    return text or None


def _detect_env_from_url(url: Optional[str]) -> str:
    if not url:
        return "UNKNOWN"
    if "/consultas-test/qr" in url:
        return "TEST"
    if "/consultas/qr" in url:
        return "PROD"
    return "UNKNOWN"


def _parse_qr_params(url: Optional[str]) -> Tuple[Dict[str, str], Optional[str]]:
    if not url:
        return {}, None
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme and parsed.netloc else parsed.path
    return params, base


def inspect_qr(xml_path: Path) -> Dict[str, object]:
    try:
        tree = ET.parse(str(xml_path))
    except Exception as exc:  # pragma: no cover - CLI error handling
        raise SystemExit(f"Error al parsear XML '{xml_path}': {exc}")

    root = tree.getroot()

    rde = _find_first(root, "rDE", SIFEN_NS) or _find_first(root, "rDE")
    de = _find_first(root, "DE", SIFEN_NS) or _find_first(root, "DE")

    d_ver_for = _extract_text(_find_first(root if rde is None else rde, "dVerFor", SIFEN_NS) or _find_first(root, "dVerFor"))
    de_id = de.get("Id") if de is not None else None

    signature = _find_first(root, "Signature", DS_NS) or _find_first(root, "Signature")

    # ElementTree no expone getparent; buscar manualmente
    def _find_parent(target: Optional[ET.Element]) -> Optional[ET.Element]:
        if target is None:
            return None
        for elem in root.iter():
            for child in list(elem):
                if child is target:
                    return elem
        return None

    sig_parent = _find_parent(signature)
    signature_parent = _get_local_name(sig_parent.tag) if sig_parent is not None else None

    gcam = None
    if de is not None:
        gcam = _find_first(de, "gCamFuFD", SIFEN_NS) or _find_first(de, "gCamFuFD")
    dcar = None
    if gcam is not None:
        dcar = _find_first(gcam, "dCarQR", SIFEN_NS) or _find_first(gcam, "dCarQR")
    if dcar is None and rde is not None:
        dcar = _find_first(rde, "dCarQR", SIFEN_NS) or _find_first(rde, "dCarQR")

    qr_url = _extract_text(dcar)
    qr_params, base_url = _parse_qr_params(qr_url)
    env_detected = _detect_env_from_url(qr_url)

    return {
        "file": str(xml_path),
        "dVerFor": d_ver_for,
        "de_id": de_id,
        "signature_parent": signature_parent,
        "qr_url": qr_url,
        "qr_base_url": base_url,
        "qr_env": env_detected,
        "qr_params": qr_params,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspecciona el QR incrustado en un XML SIFEN.")
    parser.add_argument("xml_path", type=Path, help="Ruta al archivo XML (rLoteDE o rDE)")
    parser.add_argument("--modo", type=int, choices=[0, 1], help="Modo del validador (0=Prod, 1=Test)")
    args = parser.parse_args()

    result = inspect_qr(args.xml_path)

    env_detected = result["qr_env"]
    qr_url = result["qr_url"]
    qr_params: Dict[str, str] = result["qr_params"]  # type: ignore[assignment]

    # Validar coherencia de ambiente usando assert_test_env
    current_env = get_current_env()
    modo_to_check = args.modo if args.modo is not None else env_to_modo(current_env)
    
    xml_content = Path(args.xml_path).read_text(encoding="utf-8")
    validation = assert_test_env(xml_content, modo=modo_to_check)

    print("=== SIFEN QR Inspector ===")
    print(f"Archivo: {result['file']}")
    print(f"SIFEN_ENV : {current_env.upper()}")
    print(f"dVerFor   : {result['dVerFor'] or '(missing)'}")
    print(f"DE Id     : {result['de_id'] or '(missing)'}")
    print(f"Signature : {result['signature_parent'] or '(missing parent)'}")
    print(f"dCarQR    : {qr_url or '(missing)'}")
    print(f"QR base   : {result['qr_base_url'] or '(unknown)'}")
    print(f"QR env    : {env_detected}")
    print(f"Modo      : {modo_to_check} ({'TEST' if modo_to_check == 1 else 'PROD'})")
    print()
    
    # Mostrar resultado de validación
    if validation["valid"]:
        print("✅ COHERENCIA DE AMBIENTE: OK")
    else:
        print("❌ ERRORES DE COHERENCIA DE AMBIENTE:")
        for error in validation["errors"]:
            print(f"   {error}")
    
    if validation["warnings"]:
        for warning in validation["warnings"]:
            print(f"⚠️  {warning}")

    if qr_params:
        print("\nParámetros del QR:")
        for key in sorted(qr_params):
            print(f"  - {key}: {qr_params[key]}")
    else:
        print("\nParámetros del QR: (no se pudieron extraer)")

    summary = {
        "file": result["file"],
        "dVerFor": result["dVerFor"],
        "deId": result["de_id"],
        "signatureParent": result["signature_parent"],
        "qrUrl": qr_url,
        "qrBaseUrl": result["qr_base_url"],
        "qrEnv": env_detected,
        "qrParams": qr_params,
        "modo": args.modo,
        "mismatchWarning": mismatch,
    }

    print("\nJSON_RESULT:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
