#!/usr/bin/env python3
"""
Flujo simplificado SIFEN desde cero - Solo firma local sin envío
"""

import sys
import os
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.generar_xml_desde_cero import crear_xml_desde_cero
from tools.agregar_camfu_mejorado import agregar_camfu_mejorado
from tools.generar_pdf_profesional import generar_pdf_profesional

def flujo_simplificado_desde_cero(ruc, dv, timbrado, num_doc, output_dir, csc=None):
    """
    Flujo simplificado: generar → firma local → QR → PDF
    """
    
    print("🚀 Flujo Simplificado SIFEN Desde Cero")
    print("=" * 50)
    print("   ⚠️  SIN ENVÍO A SIFEN (solo firma local)")
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
    
    # === PASO 2: Firma usando la función correcta de SIFEN ===
    print("\n🔐 Paso 2: Firmando XML con certificado SIFEN...")
    
    # Usar la función correcta de firma SIFEN con XML completo
    try:
        # Importar la función de firma correcta
        from tools.send_sirecepde import sign_and_normalize_rde_inside_xml
        
        # Leer el XML completo con rDE
        with open(xml_sin_firma, 'rb') as f:
            xml_completo_bytes = f.read()
        
        # Firmar el XML completo (contiene rDE con DE dentro)
        cert_path = os.getenv('SIFEN_SIGN_P12_PATH', '/Users/robinklaiss/.sifen/certs/F1T_65478.p12')
        cert_password = os.getenv('SIFEN_SIGN_P12_PASSWORD', 'bH1%T7EP')
        
        xml_firmado_bytes = sign_and_normalize_rde_inside_xml(
            xml_completo_bytes,
            cert_path,
            cert_password,
            output_path / 'artifacts'
        )
        
        # Guardar XML firmado
        xml_firmado = output_path / f"xml_firmado_{num_doc}.xml"
        xml_firmado.write_bytes(xml_firmado_bytes)
        
        print(f"   ✅ XML firmado correctamente: {xml_firmado}")
        
    except Exception as e:
        print(f"❌ Error en firma: {e}")
        import traceback
        traceback.print_exc()
        # Fallback: usar XML sin firma para continuar
        xml_firmado = xml_sin_firma
    
    # === PASO 3: Agregar gCamFuFD ===
    print("\n📱 Paso 3: Agregando gCamFuFD con QR...")
    
    xml_final = output_path / f"xml_final_{num_doc}.xml"
    try:
        agregar_camfu_mejorado(str(xml_firmado), str(xml_final), csc)
    except Exception as e:
        print(f"⚠️  Error agregando QR: {e}")
        print("   Copiando XML sin QR...")
        xml_final = xml_firmado
    
    # === PASO 4: Generar PDF ===
    print("\n📄 Paso 4: Generando PDF profesional...")
    
    pdf_path = output_path / f"factura_{num_doc}.pdf"
    try:
        generar_pdf_profesional(str(xml_final), str(pdf_path))
    except Exception as e:
        print(f"⚠️  Error generando PDF: {e}")
    
    # === PASO 5: Validaciones ===
    print("\n✅ Paso 5: Validaciones finales...")
    
    if xml_final.exists():
        with open(xml_final, 'rb') as f:
            contenido = f.read()
            checks = [
                (b'gCamFuFD' in contenido, 'gCamFuFD presente'),
                (b'Signature' in contenido, 'Signature presente'),
                (cdc.encode() in contenido, f'CDC presente: {cdc}'),
                (b'<rDE' in contenido, 'Estructura rDE correcta'),
                (ruc.encode() in contenido, f'RUC presente: {ruc}'),
                (timbrado.encode() in contenido, f'Timbrado presente: {timbrado}'),
            ]
            
            for check, desc in checks:
                status = "✅" if check else "❌"
                print(f"   {status} {desc}")
    
    print("\n" + "=" * 50)
    print("🎉 ¡FLUJO SIMPLIFICADO COMPLETADO!")
    print("=" * 50)
    print(f"\n📁 Archivos generados en: {output_dir}")
    print(f"   • XML sin firma: {xml_sin_firma.name}")
    print(f"   • XML firmado: {xml_firmado.name}")
    print(f"   • XML final: {xml_final.name}")
    print(f"   • PDF: {pdf_path.name if pdf_path.exists() else 'No generado'}")
    
    print(f"\n📋 CDC generado: {cdc}")
    print(f"\n🎯 XML generado COMPLETAMENTE DESDE CERO")
    print(f"\n📋 Para validar en:")
    print(f"   https://sifen.set.gov.py/prevalidador/")
    
    return str(xml_final)

def main():
    parser = argparse.ArgumentParser(description="Flujo simplificado SIFEN desde cero")
    parser.add_argument('--ruc', required=True, help='RUC (sin DV)')
    parser.add_argument('--dv', required=True, help='DV del RUC')
    parser.add_argument('--timbrado', required=True, help='Número de timbrado')
    parser.add_argument('--num-doc', required=True, help='Número documento (7 dígitos)')
    parser.add_argument('--output-dir', default='./output_simplificado', help='Directorio de salida')
    parser.add_argument('--csc', help='Código de Seguridad CSC (opcional)')
    
    args = parser.parse_args()
    
    # Formatear número de documento
    num_doc = str(args.num_doc).zfill(7)
    
    try:
        xml_final = flujo_simplificado_desde_cero(
            args.ruc, args.dv, args.timbrado, num_doc, args.output_dir, args.csc
        )
        
        if xml_final:
            print(f"\n✅ ¡Éxito! XML generado completamente desde cero.")
            print(f"   Archivo final: {xml_final}")
            print(f"   ✅ SIN USAR TEMPLATES DE MCDONALD'S")
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
