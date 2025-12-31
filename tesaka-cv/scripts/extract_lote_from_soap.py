#!/usr/bin/env python3
"""
Extrae el ZIP base64 del elemento <xDE> en un SOAP XML y lo descomprime.

Uso:
    python scripts/extract_lote_from_soap.py input_soap.xml output.xml
"""

import base64
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path


def extract_lote_from_soap(soap_path: Path, output_path: Path) -> None:
    """
    Extrae el ZIP base64 del <xDE> en el SOAP y guarda el XML descomprimido.
    
    Args:
        soap_path: Path al archivo SOAP XML
        output_path: Path donde guardar el XML extraído
    """
    # Leer SOAP
    soap_content = soap_path.read_text(encoding="utf-8", errors="replace")
    
    # Buscar <xDE>...</xDE>
    match = re.search(r"<xDE[^>]*>(.*?)</xDE>", soap_content, re.DOTALL)
    if not match:
        raise ValueError(f"No se encontró <xDE>...</xDE> en {soap_path}")
    
    # Extraer base64 (eliminar whitespace)
    b64_content = re.sub(r"\s+", "", match.group(1))
    
    if not b64_content:
        raise ValueError("Contenido de <xDE> está vacío")
    
    # Decodificar base64
    try:
        zip_bytes = base64.b64decode(b64_content)
    except Exception as e:
        raise ValueError(f"Error al decodificar base64: {e}")
    
    # Descomprimir ZIP
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), mode="r") as zf:
            # Buscar lote.xml o el primer archivo XML
            xml_files = [name for name in zf.namelist() if name.endswith(".xml")]
            if not xml_files:
                raise ValueError("No se encontró ningún archivo XML en el ZIP")
            
            # Usar el primer XML encontrado (típicamente lote.xml)
            xml_name = xml_files[0]
            xml_content = zf.read(xml_name)
    except zipfile.BadZipFile as e:
        raise ValueError(f"Error al descomprimir ZIP: {e}")
    except Exception as e:
        raise ValueError(f"Error al leer ZIP: {e}")
    
    # Guardar XML
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(xml_content)
    
    print(f"✓ Extraído: {xml_name} ({len(xml_content)} bytes)")
    print(f"✓ Guardado en: {output_path}")


def main() -> int:
    """Función principal."""
    if len(sys.argv) != 3:
        print("Uso: python scripts/extract_lote_from_soap.py <input_soap.xml> <output.xml>", file=sys.stderr)
        return 1
    
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    
    if not input_path.exists():
        print(f"❌ Error: Archivo no encontrado: {input_path}", file=sys.stderr)
        return 1
    
    try:
        extract_lote_from_soap(input_path, output_path)
        return 0
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

