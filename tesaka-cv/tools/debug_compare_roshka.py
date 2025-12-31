#!/usr/bin/env python3
"""
Script de comparación entre nuestro envío SOAP y la implementación de Roshka.

Compara:
- Endpoint usado
- Content-Type header
- Estructura del Body (rEnviDe, namespaces)
- Presencia de action/SOAPAction
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Import lxml.etree - el linter puede no reconocerlo, pero funciona correctamente
try:
    import lxml.etree as etree  # noqa: F401
except ImportError:
    raise ImportError("lxml no está instalado. Instalá: pip install lxml")

# Agregar el path del proyecto al sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def extract_soap_info(soap_file: Path) -> Dict[str, Any]:
    """Extrae información relevante del SOAP enviado."""
    if not soap_file.exists():
        return {"error": f"Archivo no encontrado: {soap_file}"}

    try:
        with open(soap_file, "rb") as f:
            content = f.read()

        # Parsear XML
        root = etree.fromstring(content)

        # Namespaces
        nsmap = root.nsmap
        soap_ns = None
        for prefix, uri in nsmap.items():
            if uri == "http://www.w3.org/2003/05/soap-envelope":
                soap_ns = prefix
                break

        # Body
        body = None
        if soap_ns:
            body = root.find(f"{{{soap_ns}}}Body")
        else:
            # Buscar sin namespace
            body = root.find("Body")

        # rEnviDe
        r_envi_de = None
        sifen_ns = None
        if body is not None:
            for child in body:
                if "rEnviDe" in child.tag:
                    r_envi_de = child
                    # Extraer namespace SIFEN
                    if "}" in child.tag:
                        sifen_ns = child.tag.split("}")[0][1:]
                    break

        # Estructura dentro de rEnviDe
        structure = {}
        if r_envi_de is not None:
            structure["has_dId"] = any("dId" in child.tag for child in r_envi_de)
            structure["has_xDE"] = any("xDE" in child.tag for child in r_envi_de)

            # Verificar si hay rDE dentro de xDE
            x_de = None
            for child in r_envi_de:
                if "xDE" in child.tag:
                    x_de = child
                    break

            if x_de is not None:
                structure["has_rDE"] = any("rDE" in child.tag for child in x_de)
                structure["has_DE"] = any("DE" in child.tag and "rDE" not in child.tag for child in x_de)

        return {
            "file": str(soap_file),
            "size": len(content),
            "soap_ns": soap_ns,
            "sifen_ns": sifen_ns,
            "has_body": body is not None,
            "has_rEnviDe": r_envi_de is not None,
            "structure": structure,
            "xml_preview": content[:500].decode("utf-8", errors="replace"),
        }
    except Exception as e:
        return {"error": f"Error al procesar {soap_file}: {e}"}


def compare_with_roshka(our_soap: Path) -> None:
    """Compara nuestro SOAP con lo esperado de Roshka."""
    print("=" * 80)
    print("COMPARACIÓN CON IMPLEMENTACIÓN ROSHKA")
    print("=" * 80)
    print()

    # Información esperada de Roshka (según código Java)
    roshka_expected = {
        "content_type": "application/xml; charset=utf-8",
        "endpoint_pattern": ".wsdl",  # Roshka postea a la URL exacta del WSDL
        "soap_action": None,  # NO usa SOAPAction header
        "action_in_content_type": False,  # NO usa action= en Content-Type
        "body_structure": {
            "root": "rEnviDe",
            "namespace": "http://ekuatia.set.gov.py/sifen/xsd",
            "has_dId": True,
            "has_xDE": True,
            "has_rDE": True,  # Roshka usa rEnviDe->xDE->rDE->DE
            "has_DE": True,
        },
    }

    print("ESPERADO (Roshka):")
    print(f"  Content-Type: {roshka_expected['content_type']}")
    print(f"  Endpoint: debe terminar en .wsdl (ej: .../recibe.wsdl)")
    print(f"  SOAPAction: {roshka_expected['soap_action']}")
    print(f"  action= en Content-Type: {roshka_expected['action_in_content_type']}")
    print(f"  Body structure: {roshka_expected['body_structure']}")
    print()

    # Analizar nuestro SOAP
    our_info = extract_soap_info(our_soap)
    if "error" in our_info:
        print(f"ERROR: {our_info['error']}")
        return

    print("NUESTRO SOAP:")
    print(f"  Archivo: {our_info['file']}")
    print(f"  Tamaño: {our_info['size']} bytes")
    print(f"  SOAP namespace prefix: {our_info['soap_ns']}")
    print(f"  SIFEN namespace: {our_info['sifen_ns']}")
    print(f"  Tiene Body: {our_info['has_body']}")
    print(f"  Tiene rEnviDe: {our_info['has_rEnviDe']}")
    if our_info.get("structure"):
        print(f"  Estructura: {our_info['structure']}")
    print()

    # Comparaciones
    print("COMPARACIONES:")
    print("-" * 80)

    # 1. Namespace SIFEN
    expected_sifen_ns = roshka_expected["body_structure"]["namespace"]
    if our_info["sifen_ns"] == expected_sifen_ns:
        print(f"✓ Namespace SIFEN correcto: {our_info['sifen_ns']}")
    else:
        print(f"✗ Namespace SIFEN diferente:")
        print(f"    Esperado: {expected_sifen_ns}")
        print(f"    Nuestro:  {our_info['sifen_ns']}")

    # 2. Estructura
    if our_info.get("structure"):
        struct = our_info["structure"]
        expected_struct = roshka_expected["body_structure"]

        if struct.get("has_dId") == expected_struct["has_dId"]:
            print(f"✓ Tiene dId: {struct.get('has_dId')}")
        else:
            print(f"✗ dId: esperado {expected_struct['has_dId']}, nuestro {struct.get('has_dId')}")

        if struct.get("has_xDE") == expected_struct["has_xDE"]:
            print(f"✓ Tiene xDE: {struct.get('has_xDE')}")
        else:
            print(f"✗ xDE: esperado {expected_struct['has_xDE']}, nuestro {struct.get('has_xDE')}")

        # rDE es clave: Roshka lo usa, nosotros podríamos no usarlo
        if struct.get("has_rDE") == expected_struct["has_rDE"]:
            print(f"✓ Tiene rDE: {struct.get('has_rDE')}")
        else:
            print(f"✗ rDE: esperado {expected_struct['has_rDE']}, nuestro {struct.get('has_rDE')}")
            print(f"  NOTA: Roshka usa rEnviDe->xDE->rDE->DE, nosotros podríamos usar rEnviDe->xDE->DE")

        if struct.get("has_DE") == expected_struct["has_DE"]:
            print(f"✓ Tiene DE: {struct.get('has_DE')}")
        else:
            print(f"✗ DE: esperado {expected_struct['has_DE']}, nuestro {struct.get('has_DE')}")

    # 3. Preview XML
    print()
    print("Preview XML (primeros 500 chars):")
    print("-" * 80)
    print(our_info["xml_preview"])
    print()

    # Notas sobre headers (no podemos extraerlos del XML, pero los documentamos)
    print("NOTAS SOBRE HEADERS:")
    print("-" * 80)
    print("Los headers HTTP no están en el XML. Verifica manualmente:")
    print(f"  - Content-Type debe ser: {roshka_expected['content_type']}")
    print(f"  - NO debe haber header SOAPAction")
    print(f"  - NO debe haber action= en Content-Type")
    print()


def main():
    """Función principal."""
    # Buscar el último SOAP enviado
    artifacts_dir = project_root / "artifacts"
    soap_file = artifacts_dir / "soap_last_sent.xml"

    if not soap_file.exists():
        print(f"ERROR: No se encontró {soap_file}")
        print("Ejecuta primero:")
        print("  SIFEN_DEBUG_SOAP=1 python -m tools.send_sirecepde --env test --xml latest")
        sys.exit(1)

    compare_with_roshka(soap_file)


if __name__ == "__main__":
    main()

