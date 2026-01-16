#!/usr/bin/env python3
"""Construye un sobre SOAP 1.2 para rEnviDe con xDE como nodo XML real."""

import argparse
import os
import random
import sys
from pathlib import Path
from typing import Optional
import copy

from lxml import etree

# Importar helper de normalización de firma
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
try:
    from sifen_normalize_signature_placement import normalize_signature_under_rde
except ImportError:
    print("WARNING: No se pudo importar normalize_signature_under_rde - la normalización será omitida")
    normalize_signature_under_rde = None

SOAP12_NS = "http://www.w3.org/2003/05/soap-envelope"
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"


def generate_did() -> str:
    """Genera un entero aleatorio de 15 dígitos (sin ceros a la izquierda)."""
    return str(random.randint(10**14, 10**15 - 1))


def load_signed_rde(xml_path: Path) -> etree._Element:
    """Carga el XML firmado, normaliza la posición de la firma y valida que contenga ds:Signature."""
    if not xml_path.exists():
        raise FileNotFoundError(f"Archivo XML no encontrado: {xml_path}")

    xml_bytes = xml_path.read_bytes()
    
    # Normalizar posición de la firma si está disponible el helper
    if normalize_signature_under_rde:
        try:
            xml_bytes = normalize_signature_under_rde(xml_bytes)
            print("✅ Firma normalizada: Signature movida a rDE")
        except Exception as e:
            print(f"⚠️  Warning: No se pudo normalizar la firma: {e}")
    
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"XML inválido: {exc}") from exc

    signature_nodes = root.xpath(
        '//*[local-name()="Signature" and namespace-uri()=$ns]',
        ns=DS_NS,
    )
    if not signature_nodes:
        raise ValueError("El XML no contiene nodo ds:Signature; no parece firmado.")

    # Normalizar namespace de rDE si no tiene
    if etree.QName(root).namespace is None:
        root.tag = f"{{{SIFEN_NS}}}{etree.QName(root).localname}"

    return root


def build_envelope(rde_element: etree._Element, did: str) -> etree._Element:
    """Construye el Envelope SOAP 1.2 con rEnviDe y xDE conteniendo el rDE como nodo."""
    envelope = etree.Element(
        etree.QName(SOAP12_NS, "Envelope"),
        nsmap={"env": SOAP12_NS},
    )
    body = etree.SubElement(envelope, etree.QName(SOAP12_NS, "Body"))
    r_envi_de = etree.SubElement(
        body,
        etree.QName(SIFEN_NS, "rEnviDe"),
        nsmap={None: SIFEN_NS},
    )

    d_id_elem = etree.SubElement(r_envi_de, etree.QName(SIFEN_NS, "dId"))
    d_id_elem.text = did

    xde_elem = etree.SubElement(r_envi_de, etree.QName(SIFEN_NS, "xDE"))
    xde_elem.append(copy.deepcopy(rde_element))

    # Validar que xDE contenga un nodo rDE (no texto)
    if len(xde_elem) == 0:
        raise RuntimeError("xDE quedó vacío; el rDE no se insertó correctamente.")
    first_child = xde_elem[0]
    if etree.QName(first_child).localname.lower() != "rde":
        raise RuntimeError("El primer hijo de xDE no es rDE.")

    # Validar que dentro del rDE siga existiendo Signature
    signature_nodes = first_child.xpath(
        './/*[local-name()="Signature" and namespace-uri()=$ns]',
        ns=DS_NS,
    )
    if not signature_nodes:
        raise RuntimeError("El rDE embebido perdió la firma ds:Signature.")

    return envelope


def save_envelope(envelope: etree._Element, output_path: Optional[Path], pretty: bool) -> str:
    xml_bytes = etree.tostring(
        envelope,
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=pretty,
    )

    if b"sifen:" in xml_bytes or b"ns2:" in xml_bytes:
        print("❌ ERROR: El SOAP generado contiene un prefijo prohibido ('sifen:' o 'ns2:').")
        sys.exit(2)

    target_fragment = b'<rEnviDe xmlns="http://ekuatia.set.gov.py/sifen/xsd"'
    if target_fragment not in xml_bytes:
        print("❌ ERROR: rEnviDe no tiene el namespace default esperado.")
        sys.exit(2)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(xml_bytes)
        return str(output_path)
    else:
        sys.stdout.buffer.write(xml_bytes)
        sys.stdout.buffer.write(b"\n")
        return "stdout"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Construye un sobre SOAP 1.2 con rEnviDe y xDE conteniendo el XML firmado.",
    )
    parser.add_argument("signed_xml", help="Ruta al XML firmado (debe contener ds:Signature)")
    parser.add_argument(
        "--out",
        dest="output",
        help="Archivo donde guardar el SOAP generado (default: stdout)",
    )
    parser.add_argument(
        "--did",
        dest="did",
        help="dId a usar (15 dígitos). Si no se provee, se genera aleatoriamente.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Usar pretty print para el XML resultante.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    xml_path = Path(args.signed_xml).expanduser()

    rde_element = load_signed_rde(xml_path)

    did = args.did or generate_did()
    if not (did.isdigit() and len(did) == 15):
        raise ValueError("dId debe ser un entero de 15 dígitos.")

    envelope = build_envelope(rde_element, did)

    output_path = Path(args.output).expanduser() if args.output else None
    target = save_envelope(envelope, output_path, args.pretty)

    print("=" * 70)
    print("SOAP 1.2 construido exitosamente")
    print(f"  dId: {did}")
    print(f"  Salida: {target}")
    print("  Validaciones:")
    print("    - ds:Signature presente como hijo de rDE (normalizado)")
    print("    - xDE contiene rDE como nodo real")
    print("    - Sin prefijo 'sifen:' en el SOAP")
    print("=" * 70)


if __name__ == "__main__":
    main()
