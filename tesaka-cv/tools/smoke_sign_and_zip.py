#!/usr/bin/env python3
"""
Smoke test local para validar firma y ZIP sin enviar a SIFEN.

Uso:
    python -m tools.smoke_sign_and_zip --xml artifacts/algun_de.xml
    python -m tools.smoke_sign_and_zip --xml latest

Este comando:
- Normaliza el XML a rDE
- Firma con xmlsec (rsa-sha256/sha256)
- Crea ZIP con lote.xml correcto
- Ejecuta preflight
- Guarda artifacts: last_xde.zip, last_lote.xml
- NO envía a SIFEN (solo valida localmente)
"""
import sys
import argparse
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from tools.send_sirecepde import (
    build_and_sign_lote_from_xml,
    preflight_soap_request,
    build_r_envio_lote_xml,
    _check_signing_dependencies
)
from app.sifen_client.config import get_mtls_cert_path_and_password


def find_latest_de_xml(artifacts_dir: Path) -> Path:
    """Busca el archivo DE más reciente en artifacts."""
    pattern = "*de*.xml"
    files = list(artifacts_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No se encontró ningún archivo *de*.xml en {artifacts_dir}")
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


def main():
    parser = argparse.ArgumentParser(
        description="Smoke test local: validar firma y ZIP sin enviar a SIFEN"
    )
    parser.add_argument(
        "--xml",
        type=str,
        help="Path al XML DE o 'latest' para usar el más reciente"
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("artifacts"),
        help="Directorio de artifacts (default: artifacts)"
    )
    
    args = parser.parse_args()
    
    # 1. Verificar dependencias críticas
    print("🔍 Verificando dependencias críticas...")
    try:
        _check_signing_dependencies()
        print("✅ Dependencias OK (lxml + xmlsec)\n")
    except RuntimeError as e:
        print(f"❌ {e}")
        print("\nEjecutar: scripts/bootstrap_env.sh")
        return 1
    
    # 2. Resolver XML
    if args.xml and args.xml.lower() == "latest":
        xml_path = find_latest_de_xml(args.artifacts_dir)
        print(f"📄 Usando archivo más reciente: {xml_path}")
    elif args.xml:
        xml_path = Path(args.xml)
        if not xml_path.exists():
            print(f"❌ Archivo no encontrado: {xml_path}")
            return 1
    else:
        # Intentar usar latest si no se especifica
        try:
            xml_path = find_latest_de_xml(args.artifacts_dir)
            print(f"📄 Usando archivo más reciente: {xml_path}")
        except FileNotFoundError as e:
            print(f"❌ {e}")
            print("   Especifique --xml <path> o coloque un archivo *de*.xml en artifacts/")
            return 1
    
    # 3. Leer XML
    try:
        xml_bytes = xml_path.read_bytes()
        print(f"   Tamaño: {len(xml_bytes)} bytes\n")
    except Exception as e:
        print(f"❌ Error al leer XML: {e}")
        return 1
    
    # 4. Obtener certificado de firma
    print("🔐 Obteniendo certificado de firma...")
    try:
        cert_path, cert_password = get_mtls_cert_path_and_password()
        print(f"   Certificado: {Path(cert_path).name}\n")
    except Exception as e:
        print(f"❌ Error al obtener certificado: {e}")
        print("   Configure SIFEN_MTLS_P12_PATH y SIFEN_MTLS_P12_PASSWORD")
        return 1
    
    # 5. Construir y firmar lote
    print("📦 Construyendo y firmando lote...")
    try:
        zip_base64, lote_xml_bytes, zip_bytes, _ = build_and_sign_lote_from_xml(
            xml_bytes=xml_bytes,
            cert_path=cert_path,
            cert_password=cert_password,
            return_debug=True
        )
        print("✅ Lote construido y firmado exitosamente\n")
    except Exception as e:
        print(f"❌ Error al construir/firmar lote: {e}")
        print("\nArtifacts guardados en artifacts/ para debugging")
        return 1
    
    # 6. Construir payload SOAP (solo para preflight, no se envía)
    print("🔧 Construyendo payload SOAP para preflight...")
    try:
        payload_xml = build_r_envio_lote_xml(did=1, xml_bytes=xml_bytes, zip_base64=zip_base64)
        print("✅ Payload SOAP construido\n")
    except Exception as e:
        print(f"❌ Error al construir payload SOAP: {e}")
        return 1
    
    # 7. Ejecutar preflight
    print("🔍 Ejecutando preflight...")
    preflight_success, preflight_error = preflight_soap_request(
        payload_xml=payload_xml,
        zip_bytes=zip_bytes,
        lote_xml_bytes=lote_xml_bytes,
        artifacts_dir=args.artifacts_dir
    )
    
    if not preflight_success:
        print(f"❌ Preflight falló: {preflight_error}")
        print("\nArtifacts guardados en artifacts/preflight_*.xml y artifacts/preflight_zip.zip")
        return 1
    
    print("✅ Preflight OK: todas las validaciones pasaron\n")
    
    # 8. Resumen final
    print("=" * 60)
    print("✅ SMOKE TEST EXITOSO")
    print("=" * 60)
    print(f"📄 XML procesado: {xml_path}")
    print(f"📦 ZIP creado: {len(zip_bytes)} bytes")
    print(f"📝 lote.xml: {len(lote_xml_bytes)} bytes")
    print(f"💾 Artifacts guardados:")
    print(f"   - artifacts/last_xde.zip")
    print(f"   - artifacts/last_lote.xml")
    print()
    print("✅ Firma: rsa-sha256 / sha256")
    print("✅ ZIP: estructura correcta (sin dId/xDE)")
    print("✅ Preflight: todas las validaciones pasaron")
    print()
    print("NOTA: Este test NO envió nada a SIFEN (solo validación local)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

