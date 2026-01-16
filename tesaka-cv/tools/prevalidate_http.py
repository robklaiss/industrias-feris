#!/usr/bin/env python3
"""
Script CLI para enviar XML directamente al prevalidador SIFEN vía HTTP POST.
Replica el comportamiento del navegador para debugging y testing.

IMPORTANTE: Por defecto usa modo TEST (modo=1) si SIFEN_ENV=test.

Uso:
    python tools/prevalidate_http.py XML_PATH --captcha VALOR [--modo 0|1] [--cookie COOKIE]

Ejemplo:
    python tools/prevalidate_http.py /path/to/file.xml --captcha "abc123"
    python tools/prevalidate_http.py /path/to/file.xml --modo 1 --captcha "abc123" --cookie "session=xyz"
"""

import argparse
import os
import sys
from pathlib import Path
import requests

# Agregar directorio padre para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.env_validator import get_current_env, env_to_modo, assert_test_env


URL = "https://ekuatia.set.gov.py/validar/validar"


def main():
    ap = argparse.ArgumentParser(
        description="Envía XML al prevalidador SIFEN con captcha y cookies del navegador"
    )
    ap.add_argument("xml_path", help="Ruta al XML a validar")
    ap.add_argument(
        "--modo",
        type=int,
        choices=[0, 1],
        default=None,
        help="0=PROD, 1=TEST (default: auto según SIFEN_ENV)"
    )
    ap.add_argument(
        "--captcha",
        required=True,
        help="Valor del header 'captcha' copiado del navegador (DevTools > Network)"
    )
    ap.add_argument(
        "--cookie",
        default="",
        help="Cookie header completo (opcional) copiado del navegador"
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout en segundos (default: 60)"
    )
    args = ap.parse_args()

    xml_path = Path(args.xml_path)
    if not xml_path.exists():
        print(f"ERROR: Archivo no encontrado: {xml_path}")
        return 1

    xml = xml_path.read_text(encoding="utf-8")
    
    # Determinar modo según SIFEN_ENV si no se especificó
    current_env = get_current_env()
    if args.modo is None:
        args.modo = env_to_modo(current_env)
        print(f"ℹ️  Modo no especificado, usando modo={args.modo} según SIFEN_ENV={current_env}")
    
    # Validar coherencia de ambiente
    print()
    print("🔍 Validando coherencia de ambiente...")
    validation = assert_test_env(xml, modo=args.modo)
    
    if not validation["valid"]:
        print("❌ ERRORES DE COHERENCIA DE AMBIENTE:")
        for error in validation["errors"]:
            print(f"   {error}")
        print()
        print("💡 SOLUCIÓN:")
        print(f"   1. Verificar SIFEN_ENV={current_env}")
        print(f"   2. Regenerar XML con: python tools/generate_test_xml.py")
        print(f"   3. Usar --modo {env_to_modo(current_env)} (coherente con {current_env.upper()})")
        return 1
    
    if validation["warnings"]:
        for warning in validation["warnings"]:
            print(f"⚠️  {warning}")
    
    print(f"✅ Ambiente coherente: SIFEN_ENV={current_env}, QR={validation['qr_env']}, modo={args.modo}")
    print()

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/xml;charset=UTF-8",
        "origin": "https://ekuatia.set.gov.py",
        "referer": "https://ekuatia.set.gov.py/prevalidador/validacion",
        "captcha": args.captcha,
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    sess = requests.Session()

    if args.cookie.strip():
        headers["cookie"] = args.cookie.strip()

    print(f"POST {URL}?modo={args.modo}")
    print(f"Captcha: {args.captcha[:20]}...")
    print(f"Cookie: {'(presente)' if args.cookie else '(no)'}")
    print(f"XML size: {len(xml)} bytes")
    print("-" * 60)

    try:
        resp = sess.post(
            URL,
            params={"modo": str(args.modo)},
            headers=headers,
            data=xml.encode("utf-8"),
            timeout=args.timeout,
        )
    except requests.exceptions.Timeout:
        print(f"ERROR: Timeout después de {args.timeout}s")
        return 1
    except requests.exceptions.RequestException as e:
        print(f"ERROR: {e}")
        return 1

    ct = (resp.headers.get("content-type") or "").lower()
    print(f"HTTP {resp.status_code} {resp.reason}")
    print(f"Content-Type: {resp.headers.get('content-type')}")
    print("-" * 60)

    if "application/json" in ct:
        try:
            data = resp.json()
            import json
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            # Interpretar resultado
            if isinstance(data, dict):
                if data.get("valid") is False or data.get("errores"):
                    return 1
            return 0
        except Exception as e:
            print(f"ERROR parseando JSON: {e}")
            print(resp.text)
            return 1
    else:
        text = resp.text or ""
        print("⚠️  Respuesta NO JSON (probablemente HTML)")
        print("Primeros 600 caracteres:")
        print("-" * 60)
        print(text[:600])
        print("-" * 60)
        print("\nPosibles causas:")
        print("  - Captcha inválido o expirado")
        print("  - Cookies faltantes o expiradas")
        print("  - Endpoint cambió")
        print("  - Modo incorrecto para el ambiente del QR")
        return 1


if __name__ == "__main__":
    exit(main())
