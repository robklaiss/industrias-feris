#!/usr/bin/env python3
"""
Debug script para probar el passthrough de XML ya firmado.

Este script:
1. Lee un XML firmado de artifacts (o del parámetro)
2. Extrae el rDE bytes sin re-serializar
3. Construye lote.xml en memoria
4. Verifica que el hash del rDE se mantenga intacto
 se genera artifacts de debug para diff manual
"""
import sys
import hashlib
from pathlib import Path

# Agregar el path del proyecto para importar
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    import argparse
    from tesaka_cv.tools.send_sirecepde import (
        _extract_rde_bytes_passthrough,
        _is_xml_already_signed,
        build_lote_passthrough_signed
    )
    
    parser = argparse.ArgumentParser(
        description="Debug script para probar passthrough de XML firmado",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Probar con último XML firmado en artifacts
  python tools/debug_passthrough_signed.py
  
  # Probar con archivo específico
  python tools/debug_passthrough_signed.py --xml artifacts/last_sent.xml
  python tools/debug_passthrough_signed.py --xml test_signed.xml
        """
    )
    
    parser.add_argument(
        "--xml",
        type=str,
        help="Path al archivo XML firmado (si no se especifica, busca en artifacts)"
    )
    
    args = parser.parse_args()
    
    # Determinar qué archivo leer
    if args.xml:
        xml_path = Path(args.xml)
        if not xml_path.exists():
            print(f"❌ El archivo no existe: {xml_path}")
            sys.exit(1)
    else:
        # Buscar el último XML en artifacts
        artifacts_dir = Path("artifacts")
        if not artifacts_dir.exists():
            print("❌ No existe directorio artifacts y no se especificó --xml")
            sys.exit(1)
        
        # Buscar archivos XML que puedan estar firmados
        xml_files = list(artifacts_dir.glob("*.xml"))
        if not xml_files:
            print("❌ No se encontraron archivos XML en artifacts")
            sys.exit(1)
        
        # Elegir el más reciente
        xml_path = max(xml_files, key=lambda p: p.stat().st_mtime)
        print(f"🔍 Usando archivo más reciente: {xml_path}")
    
    # Leer XML
    print(f"📄 Leyendo XML: {xml_path}")
    xml_bytes = xml_path.read_bytes()
    print(f"   Tamaño: {len(xml_bytes)} bytes")
    
    # Verificar si está firmado
    is_signed = _is_xml_already_signed(xml_bytes)
    print(f"   ¿Está firmado? {'Sí' if is_signed else 'No'}")
    
    if not is_signed:
        print("⚠️  El XML no parece estar firmado (no contiene <Signature>)")
        response = input("¿Continuar de todas formas? [y/N]: ")
        if response.lower() != 'y':
            sys.exit(0)
    
    # Extraer rDE bytes
    print("\n🔧 Extrayendo rDE bytes (passthrough)...")
    try:
        rde_bytes = _extract_rde_bytes_passthrough(xml_bytes)
        print(f"   rDE extraído: {len(rde_bytes)} bytes")
        
        # Calcular hash
        rde_hash = hashlib.sha256(rde_bytes).hexdigest()
        print(f"   SHA256: {rde_hash[:32]}...")
        
        # Guardar rDE extraído
        debug_dir = Path("artifacts")
        debug_dir.mkdir(parents=True, exist_ok=True)
        rde_file = debug_dir / "_debug_rde_extracted.xml"
        rde_file.write_bytes(rde_bytes)
        print(f"💾 Guardado: {rde_file}")
        
    except Exception as e:
        print(f"❌ Error extrayendo rDE: {e}")
        sys.exit(1)
    
    # Constr Construir lote.xml
    print("\n📦 Construyendo lote.xml...")
    try:
        result = build_lote_passthrough_signed(xml_bytes, return_debug=True)
        zip_base64, lote_xml_bytes, zip_bytes = result
        print(f"   ZIP base64: {len(zip_base64)} chars")
        print(f"   lote.xml: {len(lote_xml_bytes)} bytes")
        
        # Guardar lote.xml
        lote_file = debug_dir / "_debug_lote_generated.xml"
        lote_file.write_bytes(lote_xml_bytes)
        print(f"💾 Guardado: {lote_file}")
        
        # Verificar que el rDE dentro del lote sea igual
        rde_from_lote = _extract_rde_bytes_passthrough(lote_xml_bytes)
        rde_from_lote_hash = hashlib.sha256(rde_from_lote).hexdigest()
        
        print("\n🔍 Verificación de integridad:")
        print(f"   Hash rDE original:  {rde_hash[:32]}...")
        print(f"   Hash rDE del lote:  {rde_from_lote_hash[:32]}...")
        
        if rde_hash == rde_from_lote_hash:
            print("✅ ¡OK! El rDE se mantuvo intacto sin re-serialización")
        else:
            print("❌ ERROR: Los hashes no coinciden - el rDE fue modificado")
            sys.exit(1)
        
        # Guardar ZIP para inspección
        zip_file = debug_dir / "_debug_lote.zip"
        zip_file.write_bytes(zip_bytes)
        print(f"💾 Guardado: {zip_file}")
        
        # Mostrar estructura del lote
        print("\n📋 Estructura del lote.xml generado:")
        from xml.etree import ElementTree as ET
        try:
            root = ET.fromstring(lote_xml_bytes)
            print(f"   Root: {root.tag}")
            for i, child in enumerate(root):
                print(f"   Hijo {i}: {child.tag}")
                if child.tag.endswith('rDE'):
                    # Contar hijos del rDE
                    rde_children = list(child)
                    print(f"      rDE tiene {len(rde_children)} hijos:")
                    for j, rc in enumerate(rde_children[:5]):  # Primeros 5
                        print(f"         - {rc.tag}")
                    if len(rde_children) > 5:
                        print(f"         ... y {len(rde_children) - 5} más")
        except Exception as e:
            print(f"   Error al parsear: {e}")
        
        print("\n✅ Debug completado exitosamente")
        print(f"📁 Revisa los archivos en artifacts/ con prefijo _debug_")
        
    except Exception as e:
        print(f"❌ Error construyendo lote: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
