#!/usr/bin/env python3
"""
Utilidad de debug para extraer y analizar lote.xml del SOAP enviado a SIFEN.

Extrae el BASE64 de <xDE> del último SOAP debug, lo decodifica, descomprime el ZIP,
y analiza el contenido de lote.xml.
"""
import sys
import base64
import zipfile
import re
from pathlib import Path
from io import BytesIO

try:
    import lxml.etree as etree
except ImportError:
    print("❌ Error: lxml no está instalado")
    print("   Instale con: pip install lxml")
    sys.exit(1)


def extract_xde_base64_from_soap_debug(debug_file: Path) -> str:
    """
    Extrae el BASE64 de <xDE> del archivo de debug SOAP.
    
    Args:
        debug_file: Path al archivo artifacts/soap_last_http_debug.txt
        
    Returns:
        String BASE64 del contenido de xDE
    """
    if not debug_file.exists():
        raise FileNotFoundError(f"Archivo de debug no encontrado: {debug_file}")
    
    content = debug_file.read_text(encoding="utf-8")
    
    # Buscar en la sección SOAP BEGIN
    soap_match = re.search(r'---- SOAP BEGIN ----\s*(.*?)\s*---- SOAP END ----', content, re.DOTALL)
    if not soap_match:
        raise ValueError("No se encontró sección SOAP en el archivo de debug")
    
    soap_xml = soap_match.group(1)
    
    # Buscar <xsd:xDE> o <xDE> con contenido BASE64
    xde_match = re.search(r'<xsd:xDE[^>]*>(.*?)</xsd:xDE>', soap_xml, re.DOTALL)
    if not xde_match:
        # Fallback: buscar sin prefijo
        xde_match = re.search(r'<xDE[^>]*>(.*?)</xDE>', soap_xml, re.DOTALL)
    
    if not xde_match:
        raise ValueError("No se encontró elemento <xDE> en el SOAP")
    
    xde_content = xde_match.group(1).strip()
    
    # Limpiar whitespace/newlines del BASE64
    xde_content = re.sub(r'\s+', '', xde_content)
    
    return xde_content


def analyze_lote_xml(lote_xml_bytes: bytes, output_file: Path = None) -> dict:
    """
    Analiza el contenido de lote.xml.
    
    Args:
        lote_xml_bytes: Contenido del archivo lote.xml
        output_file: Path opcional para guardar el XML extraído
        
    Returns:
        Dict con información del análisis
    """
    result = {
        "size": len(lote_xml_bytes),
        "has_bom": lote_xml_bytes.startswith(b'\xef\xbb\xbf'),
        "encoding": None,
        "root_tag": None,
        "root_namespace": None,
        "first_200_bytes": lote_xml_bytes[:200].decode("utf-8", errors="replace"),
        "xml_declaration": None
    }
    
    # Detectar BOM y removerlo si existe
    if result["has_bom"]:
        lote_xml_bytes = lote_xml_bytes[3:]
    
    # Detectar encoding declaration
    xml_str = lote_xml_bytes.decode("utf-8", errors="replace")
    encoding_match = re.search(r'<\?xml[^>]*encoding=["\']([^"\']+)["\']', xml_str)
    if encoding_match:
        result["encoding"] = encoding_match.group(1)
        result["xml_declaration"] = re.search(r'<\?xml[^>]*\?>', xml_str).group(0)
    
    # Parsear XML
    try:
        root = etree.fromstring(lote_xml_bytes)
        result["root_tag"] = root.tag
        # Extraer namespace
        if "}" in root.tag:
            result["root_namespace"] = root.tag.split("}", 1)[0][1:]
        else:
            result["root_namespace"] = root.nsmap.get(None, "NONE")
    except Exception as e:
        result["parse_error"] = str(e)
    
    # Guardar archivo si se especifica
    if output_file:
        output_file.write_bytes(lote_xml_bytes)
        result["saved_to"] = str(output_file)
    
    return result


def main():
    """Función principal."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extrae y analiza lote.xml del último SOAP enviado a SIFEN"
    )
    parser.add_argument(
        "--debug-file",
        type=Path,
        default=Path("artifacts/soap_last_http_debug.txt"),
        help="Path al archivo de debug SOAP (default: artifacts/soap_last_http_debug.txt)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/lote_extracted.xml"),
        help="Path donde guardar lote.xml extraído (default: /tmp/lote_extracted.xml)"
    )
    
    args = parser.parse_args()
    
    try:
        print("🔍 Extrayendo BASE64 de xDE del SOAP debug...")
        xde_base64 = extract_xde_base64_from_soap_debug(args.debug_file)
        print(f"✓ BASE64 extraído: {len(xde_base64)} caracteres\n")
        
        print("📦 Decodificando BASE64...")
        zip_bytes = base64.b64decode(xde_base64)
        print(f"✓ ZIP decodificado: {len(zip_bytes)} bytes\n")
        
        print("📂 Descomprimiendo ZIP...")
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
            zip_files = zf.namelist()
            print(f"✓ Archivos en ZIP: {zip_files}\n")
            
            if "lote.xml" not in zip_files:
                print(f"❌ ERROR: 'lote.xml' no encontrado en ZIP")
                print(f"   Archivos encontrados: {zip_files}")
                return 1
            
            print("📄 Extrayendo lote.xml...")
            lote_xml_bytes = zf.read("lote.xml")
            print(f"✓ lote.xml extraído: {len(lote_xml_bytes)} bytes\n")
            
            print("🔬 Analizando lote.xml...")
            analysis = analyze_lote_xml(lote_xml_bytes, args.output)
            
            print("=" * 60)
            print("ANÁLISIS DE lote.xml")
            print("=" * 60)
            print(f"Tamaño: {analysis['size']} bytes")
            print(f"Tiene BOM: {analysis['has_bom']}")
            print(f"Encoding: {analysis['encoding'] or 'NO DETECTADO'}")
            if analysis.get("xml_declaration"):
                print(f"XML Declaration: {analysis['xml_declaration']}")
            print(f"Root tag: {analysis['root_tag']}")
            print(f"Root namespace: {analysis['root_namespace']}")
            if analysis.get("parse_error"):
                print(f"❌ Error al parsear: {analysis['parse_error']}")
            print(f"\nPrimeros 200 bytes:")
            print("-" * 60)
            print(analysis['first_200_bytes'])
            print("-" * 60)
            
            if analysis.get("saved_to"):
                print(f"\n💾 lote.xml guardado en: {analysis['saved_to']}")
            
            # Verificar estructura básica
            if analysis.get("root_tag"):
                root_local = analysis['root_tag'].split("}", 1)[-1] if "}" in analysis['root_tag'] else analysis['root_tag']
                if root_local != "rLoteDE":
                    print(f"\n⚠️  WARNING: Root esperado 'rLoteDE', encontrado '{root_local}'")
                else:
                    print(f"\n✅ Root correcto: rLoteDE")
            
            return 0
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

