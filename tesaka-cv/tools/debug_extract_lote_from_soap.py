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
    parser.add_argument(
        "--zip-file",
        type=Path,
        help="Path directo al archivo ZIP (en vez de extraer desde debug-file)"
    )
    parser.add_argument(
        "--payload-file",
        type=Path,
        help="Path directo al archivo XML payload (xml_file.xml o lote.xml)"
    )
    parser.add_argument(
        "--prefer-tmp",
        action="store_true",
        help="Si existe /tmp/lote_payload.zip, usar ese en vez de debug-file"
    )
    
    args = parser.parse_args()
    
    try:
        # Determinar fuente del ZIP
        zip_bytes = None
        lote_xml_bytes = None
        
        # Prioridad 1: --payload-file (XML directo)
        if args.payload_file:
            if not args.payload_file.exists():
                print(f"❌ ERROR: Archivo no encontrado: {args.payload_file}")
                return 1
            print(f"📄 Leyendo XML payload directo: {args.payload_file}")
            lote_xml_bytes = args.payload_file.read_bytes()
            print(f"✓ XML leído: {len(lote_xml_bytes)} bytes\n")
        
        # Prioridad 2: --zip-file (ZIP directo)
        elif args.zip_file:
            if not args.zip_file.exists():
                print(f"❌ ERROR: Archivo ZIP no encontrado: {args.zip_file}")
                return 1
            print(f"📦 Leyendo ZIP directo: {args.zip_file}")
            zip_bytes = args.zip_file.read_bytes()
            print(f"✓ ZIP leído: {len(zip_bytes)} bytes\n")
        
        # Prioridad 3: --prefer-tmp (buscar /tmp/lote_payload.zip)
        elif args.prefer_tmp:
            tmp_zip = Path("/tmp/lote_payload.zip")
            if tmp_zip.exists():
                print(f"📦 Usando ZIP desde /tmp: {tmp_zip}")
                zip_bytes = tmp_zip.read_bytes()
                print(f"✓ ZIP leído: {len(zip_bytes)} bytes\n")
            else:
                print(f"⚠️  WARNING: /tmp/lote_payload.zip no encontrado, usando debug-file")
                # Caer a debug-file
                zip_bytes = None
        
        # Prioridad 4: Extraer desde debug-file (comportamiento original)
        if zip_bytes is None and lote_xml_bytes is None:
            print("🔍 Extrayendo BASE64 de xDE del SOAP debug...")
            xde_base64 = extract_xde_base64_from_soap_debug(args.debug_file)
            print(f"✓ BASE64 extraído: {len(xde_base64)} caracteres\n")
            
            print("📦 Decodificando BASE64...")
            zip_bytes = base64.b64decode(xde_base64)
            print(f"✓ ZIP decodificado: {len(zip_bytes)} bytes\n")
        
        # Si tenemos ZIP, extraer lote_xml_bytes
        if zip_bytes is not None:
            print("📂 Descomprimiendo ZIP...")
            with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
                zip_files = zf.namelist()
                print(f"✓ Archivos en ZIP: {zip_files}\n")
                
                # Soportar tanto xml_file.xml como lote.xml (compatibilidad)
                xml_file_name = None
                if "xml_file.xml" in zip_files:
                    xml_file_name = "xml_file.xml"
                elif "lote.xml" in zip_files:
                    xml_file_name = "lote.xml"
                
                if not xml_file_name:
                    print(f"❌ ERROR: 'xml_file.xml' o 'lote.xml' no encontrado en ZIP")
                    print(f"   Archivos encontrados: {zip_files}")
                    return 1
                
                print(f"📄 Extrayendo {xml_file_name}...")
                lote_xml_bytes = zf.read(xml_file_name)
                print(f"✓ {xml_file_name} extraído: {len(lote_xml_bytes)} bytes\n")
        
        # Si no tenemos lote_xml_bytes, error
        if lote_xml_bytes is None:
            print("❌ ERROR: No se pudo obtener lote_xml_bytes")
            return 1
        
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

