#!/usr/bin/env python3
"""
Smoke test para emitir facturas electrónicas

Usage:
    python3 -m tools.emit_smoke.py --ruc 4554737-8 --timbrado 12345678
"""
import sys
import argparse
import json
import re
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional


def main():
    parser = argparse.ArgumentParser(description="Smoke test para emitir facturas")
    parser.add_argument("--ruc", type=str, default="4554737-8", help="RUC del emisor (default: 4554737-8)")
    parser.add_argument("--timbrado", type=str, default="12345678", help="Timbrado (default: 12345678)")
    parser.add_argument("--establecimiento", type=str, default="001", help="Establecimiento (default: 001)")
    parser.add_argument("--punto-expedicion", dest="punto_expedicion", type=str, default="001", help="Punto de expedición (default: 001)")
    parser.add_argument("--numero-documento", type=str, default="0000001", help="Número de documento (default: 0000001)")
    parser.add_argument("--host", type=str, default="127.0.0.1:8000", help="Host del servidor (default: 127.0.0.1:8000)")
    
    args = parser.parse_args()
    
    # URL base
    base_url = f"http://{args.host}"
    
    # Payload para emitir
    payload = {
        "env": "test",
        "ruc": args.ruc,
        "timbrado": args.timbrado,
        "establecimiento": args.establecimiento,
        "punto_expedicion": args.punto_expedicion,
        "numero_documento": args.numero_documento
    }
    
    try:
        # 1. Emitir factura
        print("Enviando a /api/v1/emitir...")
        response = requests.post(
            f"{base_url}/api/v1/emitir",
            json=payload,
            timeout=20
        )
        response.raise_for_status()
        
        resp_data = response.json()
        did = resp_data.get("dId")
        
        if not did:
            print("❌ Error: No se recibió dId en la respuesta")
            print(json.dumps(resp_data, indent=2))
            return 1
            
        # Guardar respuesta JSON
        with open("/tmp/emitir_resp.json", "w") as f:
            json.dump(resp_data, f, indent=2)
        
        print(f"DID={did}")
        
        # 2. Descargar DE XML
        print("Descargando DE XML...")
        de_response = requests.get(
            f"{base_url}/api/v1/artifacts/{did}/de",
            timeout=20
        )
        de_response.raise_for_status()
        
        # Guardar DE XML
        de_path = f"/tmp/DE_TAL_CUAL_{did}.xml"
        with open(de_path, "w", encoding="utf-8") as f:
            f.write(de_response.text)
        
        print(f"OUT={de_path}")
        
        # 3. Validar firma placeholder
        signature_issues = []
        
        # Buscar patrones de firma placeholder
        if re.search(r'rsa-sha1', de_response.text, re.IGNORECASE):
            signature_issues.append("rsa-sha1")
        if re.search(r'xmldsig#sha1', de_response.text, re.IGNORECASE):
            signature_issues.append("xmldsig#sha1")
        if re.search(r'dGhpcy', de_response.text):
            signature_issues.append("dGhpcy (base64 placeholder)")
        
        if signature_issues:
            print("Firma: FAIL")
            print("Issues encontrados:")
            for issue in signature_issues:
                print(f"  - {issue}")
            # Mostrar líneas relevantes
            for issue in signature_issues[:3]:  # Máximo 3 issues
                for line in de_response.text.split('\n'):
                    if issue.lower() in line.lower():
                        print(f"  {line.strip()[:100]}")
                        break
        else:
            print("Firma: OK")
        
        # 4. Validar dRucEm sin cero inicial
        ruc_match = re.search(r'<dRucEm>([^<]+)</dRucEm>', de_response.text)
        if ruc_match:
            ruc_em = ruc_match.group(1)
            if ruc_em.startswith('0') and len(ruc_em) > 1:
                print("RUC: FAIL")
                print(f"dRucEm tiene cero inicial: {ruc_em}")
                # Mostrar línea
                for line in de_response.text.split('\n'):
                    if '<dRucEm>' in line:
                        print(f"  {line.strip()}")
                        break
            else:
                print("RUC: OK")
        else:
            print("RUC: FAIL (no encontrado)")
        
        # 5. Exit code basado en validaciones
        if signature_issues or (ruc_match and ruc_match.group(1).startswith('0') and len(ruc_match.group(1)) > 1):
            return 1
        
        return 0
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error de conexión: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
