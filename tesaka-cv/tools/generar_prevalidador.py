#!/usr/bin/env python3
"""
Genera XML rDE firmado para Prevalidador SIFEN
Uso: python generar_prevalidador.py [--json data.json] [--out output.xml]
"""
import sys
import json
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.flujo_simplificado_desde_cero import flujo_simplificado_desde_cero

def main():
    parser = argparse.ArgumentParser(description="Genera XML para Prevalidador SIFEN")
    parser.add_argument("--json", help="Archivo JSON con datos del DE")
    parser.add_argument("--out", help="Archivo de salida XML")
    args = parser.parse_args()
    
    print("🎯 Generando XML para Prevalidador SIFEN...")
    
    # Valores por defecto si no se usa JSON
    ruc = "4554737"
    dv = "8"
    timbrado = "12345678"
    num_doc = "0000029"
    
    # Si se proporciona JSON, extraer datos
    if args.json:
        try:
            with open(args.json, 'r') as f:
                data = json.load(f)
            
            # Extraer datos del emisor
            emisor = data.get('emisor', {})
            ruc = emisor.get('ruc', ruc)
            dv = emisor.get('dv', dv)
            
            # Extraer datos del timbrado
            timbrado_data = data.get('timbrado', {})
            timbrado = timbrado_data.get('numero', timbrado)
            num_doc = timbrado_data.get('numero_documento', num_doc)
            
            print(f"📋 Usando datos desde {args.json}")
            print(f"   Emisor: {ruc}-{dv}")
            print(f"   Timbrado: {timbrado}")
            print(f"   Documento: {num_doc}")
            
        except Exception as e:
            print(f"❌ Error leyendo JSON: {e}")
            sys.exit(1)
    
    # Determinar directorio de salida
    if args.out:
        output_path = Path(args.out)
        output_dir = output_path.parent
        output_file = output_path.name
    else:
        output_dir = Path.home() / "Desktop"
        output_file = f"xml_final_{num_doc}.xml"
    
    try:
        result = flujo_simplificado_desde_cero(
            ruc=ruc,
            dv=dv,
            timbrado=timbrado,
            num_doc=num_doc,
            output_dir=str(output_dir)
        )
        
        # Mover al nombre final si se especificó
        final_xml = output_dir / f"xml_final_{num_doc}.xml"
        if args.out and final_xml.name != output_file:
            final_xml.rename(output_dir / output_file)
            final_xml = output_dir / output_file
        
        print(f"\n✅ XML generado:")
        print(f"   Archivo: {final_xml}")
        print(f"   CDC: 000{ruc}{dv}02901000002912026011410000000011")
        print(f"\n📋 Subir este archivo a: https://sifen.set.gov.py/prevalidador/")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
