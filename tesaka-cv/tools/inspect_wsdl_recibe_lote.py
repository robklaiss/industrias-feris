#!/usr/bin/env python3
"""
Inspecciona el WSDL de recibe-lote y guarda el resultado en artifacts/wsdl_inspected.json

Uso:
    python -m tools.inspect_wsdl_recibe_lote [--env test|prod] [--wsdl-url URL] [--output PATH]
"""
import sys
import json
from pathlib import Path

# Agregar parent al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.wsdl_introspect import inspect_wsdl, save_wsdl_inspection
from app.sifen_client.config import get_sifen_config


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Inspecciona WSDL de recibe-lote")
    parser.add_argument("--env", choices=["test", "prod"], default="test", help="Ambiente (test/prod)")
    parser.add_argument("--wsdl-url", help="URL del WSDL (sobrescribe --env)")
    parser.add_argument("--output", type=Path, default=Path("artifacts/wsdl_inspected.json"), help="Path de salida JSON")
    parser.add_argument("--operation", help="Nombre de la operación (opcional)")
    
    args = parser.parse_args()
    
    # Obtener URL del WSDL
    if args.wsdl_url:
        wsdl_url = args.wsdl_url
    else:
        config = get_sifen_config(env=args.env)
        wsdl_url = config.get_soap_service_url("recibe_lote")
    
    print(f"🔍 Inspeccionando WSDL: {wsdl_url}")
    
    try:
        result = inspect_wsdl(wsdl_url, args.operation)
        save_wsdl_inspection(result, args.output)
        
        print(f"\n✅ Resultado guardado en: {args.output}\n")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

