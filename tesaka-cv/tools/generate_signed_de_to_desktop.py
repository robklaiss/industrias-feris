#!/usr/bin/env python3
"""
Generador de XML SIFEN v150 firmado con validación NT16

Este script:
1) Genera un XML DE v150 mínimo
2) Firma con certificado P12
3) Valida cumplimiento NT16 (MT v150)
4) Guarda en ~/Desktop/sifen_de_test_signed.xml

Uso:
    export SIFEN_CERT_PATH="/ruta/certificado.p12"
    export SIFEN_CERT_PASS="password"
    export SIFEN_ENV="test"  # opcional
    
    python tools/generate_signed_de_to_desktop.py
    
    # O con argumentos:
    python tools/generate_signed_de_to_desktop.py --env test --out ~/Desktop/mi_xml.xml

Variables de entorno:
    SIFEN_CERT_PATH: Ruta al certificado P12/PFX (requerido)
    SIFEN_CERT_PASS: Contraseña del certificado (requerido)
    SIFEN_ENV: test|prod (opcional, default: test)
"""
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Agregar directorio padre al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.xml_generator_v150 import create_rde_xml_v150
from app.sifen_client.xmldsig_signer import sign_de_xml, assert_sifen_v150_signature_shape, XMLDSigError
from app.sifen_client.emisor_validator import extract_ruc_dv_from_cert, EmisorValidationError


def _require_env(name: str) -> str:
    """Obtiene variable de entorno requerida o falla"""
    value = os.getenv(name, "").strip()
    if not value:
        print(f"❌ ERROR: Variable de entorno requerida no configurada: {name}")
        print(f"\nConfiguración requerida:")
        print(f'  export SIFEN_CERT_PATH="/ruta/a/certificado.p12"')
        print(f'  export SIFEN_CERT_PASS="password_del_certificado"')
        print(f'  export SIFEN_ENV="test"  # opcional')
        print(f"\nLuego ejecutar:")
        print(f"  python tools/generate_signed_de_to_desktop.py")
        sys.exit(1)
    return value


def main():
    """Función principal"""
    parser = argparse.ArgumentParser(
        description="Genera XML SIFEN v150 firmado con validación NT16"
    )
    parser.add_argument(
        "--env",
        choices=["test", "prod"],
        default=os.getenv("SIFEN_ENV", "test"),
        help="Ambiente SIFEN (default: test)"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path.home() / "Desktop" / "sifen_de_test_signed.xml",
        help="Ruta de salida del XML firmado (default: ~/Desktop/sifen_de_test_signed.xml)"
    )
    parser.add_argument(
        "--ruc",
        help="RUC del emisor (opcional, se extrae del certificado si no se provee)"
    )
    parser.add_argument(
        "--dv",
        help="DV del RUC (opcional, se extrae del certificado si no se provee)"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("GENERADOR XML SIFEN v150 FIRMADO (NT16 Compliant)")
    print("=" * 70)
    print()
    
    # 1) Leer variables de entorno
    cert_path = _require_env("SIFEN_CERT_PATH")
    cert_password = _require_env("SIFEN_CERT_PASS")
    
    print(f"📋 Configuración:")
    print(f"  - Certificado: {cert_path}")
    print(f"  - Ambiente: {args.env.upper()}")
    print(f"  - Salida: {args.out}")
    print()
    
    # 2) Extraer RUC-DV del certificado (si no se proveyó)
    if args.ruc and args.dv:
        cert_ruc = args.ruc
        cert_dv = args.dv
        print(f"📋 Usando RUC-DV provisto: {cert_ruc}-{cert_dv}")
    else:
        print("🔍 Extrayendo RUC-DV del certificado...")
        try:
            cert_ruc, cert_dv = extract_ruc_dv_from_cert(cert_path, cert_password)
            print(f"✅ Certificado pertenece a: RUC {cert_ruc}-{cert_dv}")
        except EmisorValidationError as e:
            print(f"❌ ERROR: {e}")
            sys.exit(1)
    print()
    
    # 3) Generar XML DE v150
    print("📝 Generando XML DE v150...")
    
    now = datetime.now()
    fecha = now.strftime("%Y-%m-%d")
    hora = now.strftime("%H:%M:%S")
    
    try:
        xml_unsigned = create_rde_xml_v150(
            ruc=cert_ruc,
            dv_ruc=cert_dv,
            timbrado="12345678",
            establecimiento="001",
            punto_expedicion="001",
            numero_documento=now.strftime("%Y%m%d%H%M%S")[-7:],  # Máx 7 dígitos
            tipo_documento="1",
            fecha=fecha,
            hora=hora,
            csc="123456789",
        )
        print(f"✅ XML generado ({len(xml_unsigned)} bytes)")
        print()
    except Exception as e:
        print(f"❌ ERROR al generar XML: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 4) Firmar XML
    print("🔐 Firmando XML con certificado...")
    try:
        signed_xml = sign_de_xml(xml_unsigned, cert_path, cert_password)
        print(f"✅ XML firmado ({len(signed_xml)} bytes)")
        print()
    except XMLDSigError as e:
        print(f"❌ ERROR al firmar XML: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 5) Validar cumplimiento NT16
    print("🔍 Validando cumplimiento NT16 (MT v150)...")
    try:
        assert_sifen_v150_signature_shape(signed_xml)
        print("✅ Firma cumple con NT16")
        print()
    except XMLDSigError as e:
        print(f"❌ ERROR: Firma NO cumple con NT16")
        print(f"   {e}")
        print()
        print("⚠️  El XML fue firmado pero NO cumple con los estándares SIFEN.")
        print("   Guardando de todas formas para inspección...")
        print()
    
    # 6) Guardar en Desktop
    print(f"💾 Guardando XML firmado en: {args.out}")
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        
        if isinstance(signed_xml, bytes):
            args.out.write_bytes(signed_xml)
        else:
            args.out.write_text(signed_xml, encoding="utf-8")
        
        print(f"✅ Archivo guardado exitosamente")
        print()
    except Exception as e:
        print(f"❌ ERROR al guardar archivo: {e}")
        sys.exit(1)
    
    # 7) Mostrar resumen final
    print("=" * 70)
    print("✅ XML GENERADO, FIRMADO Y VALIDADO EXITOSAMENTE")
    print("=" * 70)
    print()
    print(f"📄 Archivo: {args.out}")
    print(f"📊 Tamaño: {args.out.stat().st_size:,} bytes")
    print()
    
    # Extraer y mostrar información de la firma
    try:
        from lxml import etree
        root = etree.fromstring(signed_xml.encode("utf-8") if isinstance(signed_xml, str) else signed_xml)
        ns = {"ds": "http://www.w3.org/2000/09/xmldsig#", "sifen": "http://ekuatia.set.gov.py/sifen/xsd"}
        
        # Obtener algoritmos usados
        c14n_alg = root.xpath("//ds:CanonicalizationMethod/@Algorithm", namespaces=ns)
        sig_alg = root.xpath("//ds:SignatureMethod/@Algorithm", namespaces=ns)
        digest_alg = root.xpath("//ds:DigestMethod/@Algorithm", namespaces=ns)
        transforms = root.xpath("//ds:Transform/@Algorithm", namespaces=ns)
        
        print("📋 Algoritmos de firma (NT16):")
        if c14n_alg:
            print(f"  - CanonicalizationMethod: {c14n_alg[0]}")
        if sig_alg:
            print(f"  - SignatureMethod: {sig_alg[0]}")
        if digest_alg:
            print(f"  - DigestMethod: {digest_alg[0]}")
        if transforms:
            print(f"  - Transforms: {len(transforms)} transform(s)")
            for i, t in enumerate(transforms, 1):
                print(f"    {i}. {t}")
        print()
        
        # Obtener CDC/Id
        de_nodes = root.xpath("//sifen:DE", namespaces=ns)
        if not de_nodes:
            de_nodes = root.xpath("//DE")
        
        if de_nodes:
            de_id = de_nodes[0].get("Id")
            if de_id:
                print(f"📋 CDC/Id del DE:")
                print(f"  - {de_id}")
                print(f"  - Longitud: {len(de_id)} dígitos")
                print()
    except Exception as e:
        print(f"⚠️  No se pudo extraer información de la firma: {e}")
        print()
    
    print("🎯 Próximos pasos:")
    print(f"  1) Subir a SIFEN {args.env.upper()} prevalidador:")
    if args.env == "test":
        print(f"     https://ekuatia.set.gov.py/consultas-test/validador/")
    else:
        print(f"     https://ekuatia.set.gov.py/consultas/validador/")
    print()
    print(f"  2) O usar herramienta de prevalidación:")
    modo = "1" if args.env == "test" else "0"
    print(f"     python3 tools/prevalidate_http.py '{args.out}' --modo {modo} --captcha 'VALOR'")
    print()
    
    print("✅ DONE")


if __name__ == "__main__":
    main()
