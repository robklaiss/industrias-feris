#!/usr/bin/env python3
"""
SIFEN Generar - Generador simple de XMLs para Prevalidador
Copia XMLs ya firmados y validados para usar en el Prevalidador SIFEN.
"""

import sys
import os
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    parser = argparse.ArgumentParser(
        description="SIFEN Generar - Copia XMLs firmados para el Prevalidador",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
XMLs disponibles:
  1 - rde_signed_01045547378001001000000112026010210000000013.xml (N° 0000001)
  2 - rde_signed_01045547378001001000000112026010211234567896.xml (N° 0000001)
  3 - rde_signed_01045547378001001000001512026011311234567898.xml (N° 0000015)
  4 - rde_signed_01045547378001001000005012026010210000000014.xml (N° 0000050)

Ejemplos:
  %(prog)s 1 --output ./facturas
  %(prog)s 2 --filename mi_factura.xml
        """
    )
    
    parser.add_argument('xml_id', type=int, choices=[1, 2, 3, 4], 
                       help='ID del XML a copiar (1, 2, 3 o 4)')
    parser.add_argument('--output', '-o', help='Directorio de salida (default: Desktop)')
    parser.add_argument('--filename', '-f', help='Nombre del archivo (default: auto)')
    parser.add_argument('--validar', action='store_true', default=True, 
                       help='Validar CDC después de copiar (default: True)')
    
    args = parser.parse_args()
    
    # Mapping de XMLs disponibles
    xml_files = {
        1: {
            'path': 'artifacts/rde_signed_01045547378001001000000112026010210000000013.xml',
            'num_doc': '0000001',
            'cdc': '01045547378001001000000112026010210000000013'
        },
        2: {
            'path': 'artifacts/rde_signed_01045547378001001000000112026010211234567896.xml',
            'num_doc': '0000001',
            'cdc': '01045547378001001000000112026010211234567896'
        },
        3: {
            'path': 'artifacts/rde_signed_01045547378001001000001512026011311234567898.xml',
            'num_doc': '0000015',
            'cdc': '01045547378001001000001512026011311234567898'
        },
        4: {
            'path': 'artifacts/rde_signed_01045547378001001000005012026010210000000014.xml',
            'num_doc': '0000050',
            'cdc': '01045547378001001000005012026010210000000014'
        }
    }
    
    xml_info = xml_files[args.xml_id]
    source_path = Path(xml_info['path'])
    
    if not source_path.exists():
        print(f"❌ Archivo no encontrado: {source_path}")
        sys.exit(1)
    
    # Determinar directorio de salida
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = Path.home() / "Desktop"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Determinar nombre del archivo
    if args.filename:
        filename = args.filename
    else:
        filename = f"prevalidador_rde_signed.xml"
    
    # Copiar archivo
    dest_path = output_dir / filename
    dest_path.write_bytes(source_path.read_bytes())
    
    print(f"✅ XML copiado exitosamente")
    print(f"   Origen: {source_path}")
    print(f"   Destino: {dest_path}")
    print(f"   N° Documento: {xml_info['num_doc']}")
    print(f"   CDC: {xml_info['cdc']}")
    
    # Validar si se solicita
    if args.validar:
        print("\n🔍 Validando CDC...")
        os.system(f".venv/bin/python tools/debug_cdc.py {dest_path}")
    
    print(f"\n🎯 Listo para usar en el Prevalidador SIFEN!")
    print(f"   Subir el archivo: {dest_path}")

if __name__ == "__main__":
    main()
