#!/usr/bin/env python3
"""
Inspecciona el WSDL de siRecepLoteDE usando zeep y muestra:
- Servicios/puertos/operaciones disponibles
- QName esperado para el body de siRecepLoteDE
- Envelope SOAP que zeep generaría para un payload dummy (sin enviar)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from zeep import Client, Settings
    from zeep.transports import Transport
except ImportError as exc:  # pragma: no cover - friendly CLI error
    raise SystemExit(
        "❌ zeep no está instalado. Instale dependencias con: pip install zeep"
    ) from exc

try:
    import lxml.etree as etree
except ImportError as exc:
    raise SystemExit(
        "❌ lxml no está instalado. Instale dependencias con: pip install lxml"
    ) from exc

import json
import requests

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"


def _default_wsdl() -> str:
    return os.getenv(
        "SIFEN_WSDL_RECIBE_LOTE",
        "https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl",
    )


def _build_dummy_payload(root_name: str) -> etree._Element:
    root = etree.Element(etree.QName(SIFEN_NS, root_name), nsmap={None: SIFEN_NS})
    etree.SubElement(root, etree.QName(SIFEN_NS, "dId")).text = "202401010000001"
    etree.SubElement(root, etree.QName(SIFEN_NS, "xDE")).text = "__BASE64_PLACEHOLDER__"
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug rápido de shape del WSDL recibe-lote.")
    parser.add_argument("--wsdl", default=_default_wsdl(), help="URL/archivo WSDL a inspeccionar")
    parser.add_argument(
        "--operation",
        default="siRecepLoteDE",
        help="Operación a detallar (default: siRecepLoteDE)",
    )
    parser.add_argument(
        "--root",
        default=os.getenv("SIFEN_ENVIOLOTE_ROOT", "rEnvioLoteDe"),
        help="Root usado para el payload dummy (default: env SIFEN_ENVIOLOTE_ROOT o rEnvioLoteDe)",
    )
    args = parser.parse_args()

    print(f"📡 Cargando WSDL: {args.wsdl}")
    settings = Settings(strict=False, xml_huge_tree=True)
    session = requests.Session()
    transport = Transport(session=session, cache=None)
    client = Client(args.wsdl, settings=settings, transport=transport)

    print("\n=== Servicios / Puertos / Operaciones ===")
    service = None
    port = None
    for service in client.wsdl.services.values():
        print(f"Servicio: {service.name}")
        for port in service.ports.values():
            print(f"  Puerto: {port.name}")
            binding = port.binding
            for op_name, operation in binding._operations.items():
                soap_action = operation.soapaction or "(sin action)"
                print(f"    • {op_name} (action={soap_action})")
            if port and not port.binding:
                continue

    # Seleccionar primer binding del client service
    binding = client.service._binding
    service = client.wsdl.services[list(client.wsdl.services.keys())[0]]
    port = list(service.ports.values())[0]
    if args.operation not in binding._operations:
        print(f"\n❌ Operación {args.operation} no encontrada en el binding del primer puerto")
        return 1

    operation = binding._operations[args.operation]
    input_message = operation.input.message if operation.input else None
    body_element = None
    if input_message and input_message.parts:
        # Para document/literal hay un único part con element QName
        first_part = list(input_message.parts.values())[0]
        body_element = getattr(first_part, "element", None)

    print("\n=== Detalle Operación ===")
    print(f"Nombre: {args.operation}")
    print(f"SOAPAction: {operation.soapaction or '(sin action)'}")
    if input_message:
        print(f"Input QName: {{{input_message.namespace}}}{input_message.name}")
    if body_element is not None:
        print(f"Body element: {body_element.qname}")
    print(f"Style: {operation.style}")
    if hasattr(operation, "body") and operation.body:
        body = operation.body
        print(f"Body use: {body.use} (namespace={body.namespace})")

    payload = _build_dummy_payload(args.root)
    envelope = None
    envelope_str = ""
    try:
        envelope = client.create_message(client.service, args.operation, _value_1=payload)
        envelope_str = etree.tostring(envelope, pretty_print=True, encoding="unicode")
    except Exception as exc:
        print(f"\n❌ No se pudo generar envelope con payload dummy: {exc}")
    redacted = envelope_str.replace("__BASE64_PLACEHOLDER__", "__BASE64_REDACTED__")

    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out_json = {
        "operation": args.operation,
        "service": service.name if service else None,
        "port": port.name if port else None,
        "binding": binding.name.text if binding else None,
        "expected_qname": {
            "namespace": body_element.qname.namespace if body_element is not None else None,
            "localname": body_element.qname.localname if body_element is not None else None,
        }
        if body_element is not None
        else None,
        "message_qname": {
            "namespace": input_message.namespace if input_message else None,
            "localname": input_message.name if input_message else None,
        }
        if input_message
        else None,
        "soap_version": getattr(binding, "soap_version", None),
        "action": operation.soapaction,
        "target_namespace": client.wsdl.tns,
    }
    (artifacts_dir / "wsdl_expected_shape.json").write_text(
        json.dumps(out_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if redacted:
        (artifacts_dir / "wsdl_sample_envelope.xml").write_text(
            redacted, encoding="utf-8"
        )
        print(f"\n💾 Envelope generado guardado en: {artifacts_dir / 'wsdl_sample_envelope.xml'}")

    print("\n=== Envelope generado por zeep (redactado) ===")
    print(redacted or "(no envelope generado)")
    print(f"\nWSDL shape JSON: {artifacts_dir / 'wsdl_expected_shape.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
