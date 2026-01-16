#!/usr/bin/env python3
"""
Flujo completo SIFEN desde cero - Sin templates existentes
"""

import sys
import os
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.generar_xml_desde_cero import crear_xml_desde_cero
from tools.agregar_camfu_mejorado import agregar_camfu_mejorado
from tools.generar_pdf_profesional import generar_pdf_profesional

def flujo_completo_desde_cero(ruc, dv, timbrado, num_doc, output_dir, csc=None):
    """
    Flujo completo: generar → firmar → agregar QR → PDF
    """
    
    print("🚀 Flujo Completo SIFEN Desde Cero")
    print("=" * 50)
    print(f"   RUC: {ruc}-{dv}")
    print(f"   Timbrado: {timbrado}")
    print(f"   Documento: {num_doc}")
    print(f"   Directorio: {output_dir}")
    print("=" * 50)
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # === PASO 1: Generar XML desde cero ===
    print("\n📝 Paso 1: Generando XML desde cero...")
    
    xml_sin_firma = output_path / f"xml_sin_firma_{num_doc}.xml"
    xml_path, cdc = crear_xml_desde_cero(ruc, dv, timbrado, num_doc, str(xml_sin_firma))
    
    # === PASO 2: Firmar XML ===
    print("\n🔐 Paso 2: Firmando XML...")
    
    import subprocess
    
    # Firmar con send_sirecepde
    cmd_firma = [
        '.venv/bin/python', 'tools/send_sirecepde.py',
        '--xml', str(xml_sin_firma),
        '--env', 'test',
        '--artifacts-dir', str(output_path / 'artifacts'),
        '--skip-ruc-gate'
    ]
    
    result_firma = subprocess.run(cmd_firma, capture_output=True, text=True, 
                                  cwd=str(Path(__file__).parent.parent))
    
    if result_firma.returncode != 0:
        print(f"❌ Error firmando: {result_firma.stderr}")
        return None
    
    # Buscar XML firmado
    artifacts_dir = output_path / 'artifacts'
    xml_firmado = None
    for file in artifacts_dir.glob('rde_signed_*.xml'):
        xml_firmado = file
        break
    
    if not xml_firmado:
        print("❌ No se encontró XML firmado")
        return None
    
    print(f"   ✅ XML firmado: {xml_firmado}")
    
    # === PASO 3: Agregar gCamFuFD ===
    print("\n📱 Paso 3: Agregando gCamFuFD con QR...")
    
    xml_final = output_path / f"xml_final_{num_doc}.xml"
    agregar_camfu_mejorado(str(xml_firmado), str(xml_final), csc)
    
    # === PASO 4: Generar PDF ===
    print("\n📄 Paso 4: Generando PDF profesional...")
    
    pdf_path = output_path / f"factura_{num_doc}.pdf"
    generar_pdf_profesional(str(xml_final), str(pdf_path))
    
    # === PASO 5: Validaciones ===
    print("\n✅ Paso 5: Validaciones finales...")
    
    # Verificar estructura
    with open(xml_final, 'rb') as f:
        contenido = f.read()
        checks = [
            ('gCamFuFD' in contenido, 'gCamFuFD presente'),
            ('Signature' in contenido, 'Signature presente'),
            (cdc.encode() in contenido, f'CDC presente: {cdc}'),
            ('<rDE' in contenido, 'Estructura rDE correcta'),
        ]
        
        for check, desc in checks:
            status = "✅" if check else "❌"
            print(f"   {status} {desc}")
    
    print("\n" + "=" * 50)
    print("🎉 ¡FLUJO COMPLETADO EXITOSAMENTE!")
    print("=" * 50)
    print(f"\n📁 Archivos generados en: {output_dir}")
    print(f"   • XML sin firma: {xml_sin_firma.name}")
    print(f"   • XML firmado: {xml_firmado.name}")
    print(f"   • XML final: {xml_final.name}")
    print(f"   • PDF: {pdf_path.name}")
    
    print(f"\n📋 CDC generado: {cdc}")
    print(f"\n🎯 XML listo para validar en:")
    print(f"   https://sifen.set.gov.py/prevalidador/")
    
    return str(xml_final)

def main():
    parser = argparse.ArgumentParser(description="Flujo completo SIFEN desde cero")
    parser.add_argument('--ruc', required=True, help='RUC (sin DV)')
    parser.add_argument('--dv', required=True, help='DV del RUC')
    parser.add_argument('--timbrado', required=True, help='Número de timbrado')
    parser.add_argument('--num-doc', required=True, help='Número documento (7 dígitos)')
    parser.add_argument('--output-dir', default='./output_desde_cero', help='Directorio de salida')
    parser.add_argument('--csc', help='Código de Seguridad CSC (opcional)')
    
    args = parser.parse_args()
    
    # Formatear número de documento
    num_doc = str(args.num_doc).zfill(7)
    
    try:
        xml_final = flujo_completo_desde_cero(
            args.ruc, args.dv, args.timbrado, num_doc, args.output_dir, args.csc
        )
        
        if xml_final:
            print(f"\n✅ ¡Éxito! XML generado completamente desde cero.")
            print(f"   Archivo final: {xml_final}")
        else:
            print("\n❌ Error en el flujo.")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
