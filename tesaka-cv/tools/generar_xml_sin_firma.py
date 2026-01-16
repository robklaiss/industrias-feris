#!/usr/bin/env python3
"""
Generador de XML SIFEN v150 FIRMADO con validación emisor vs certificado

Este script:
1) Lee el certificado P12 y extrae su RUC-DV
2) Genera un XML DE v150 con ese RUC-DV
3) Firma el XML con el certificado usando signxml
4) Guarda el resultado en ~/Desktop/sifen_firmado_v150.xml

Uso:
    export SIFEN_CERT_PATH="/ruta/certificado.p12"
    export SIFEN_CERT_PASS="password"
    python tools/generar_xml_sin_firma.py
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# Agregar directorio padre al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.xml_generator_v150 import create_rde_xml_v150
from app.sifen_client.xmldsig_signer import sign_de_xml, XMLDSigError
from app.sifen_client.emisor_validator import (
    extract_ruc_dv_from_cert,
    validate_emisor_in_xml,
    EmisorValidationError
)


def _require_env(name: str) -> str:
    """Obtiene variable de entorno requerida o falla"""
    value = os.getenv(name, "").strip()
    if not value:
        print(f"❌ ERROR: Variable de entorno requerida no configurada: {name}")
        print(f"\nConfiguración requerida:")
        print(f'  export SIFEN_CERT_PATH="/ruta/a/certificado.p12"')
        print(f'  export SIFEN_CERT_PASS="password_del_certificado"')
        print(f"\nLuego ejecutar:")
        print(f"  python tools/generar_xml_sin_firma.py")
        sys.exit(1)
    return value


def main():
    """Función principal"""
    print("=" * 70)
    print("GENERADOR XML SIFEN v150 FIRMADO con validación emisor vs certificado")
    print("=" * 70)
    print()
    
    # 1) Leer variables de entorno
    cert_path = _require_env("SIFEN_CERT_PATH")
    cert_password = _require_env("SIFEN_CERT_PASS")
    
    codseg = os.getenv("SIFEN_CODSEG", "123456789").strip()
    
    print(f"📋 Configuración:")
    print(f"  - Certificado: {cert_path}")
    print()
    
    # 2) Extraer RUC-DV del certificado
    print("🔍 Extrayendo RUC-DV del certificado...")
    try:
        cert_ruc, cert_dv = extract_ruc_dv_from_cert(cert_path, cert_password)
        print(f"✅ Certificado pertenece a: RUC {cert_ruc}-{cert_dv}")
        print()
    except EmisorValidationError as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)
    
    # 3) Generar XML con el RUC-DV del certificado
    print("📝 Generando XML DE v150...")
    
    now = datetime.now()
    fecha = now.strftime("%Y-%m-%d")
    hora = now.strftime("%H:%M:%S")
    
    try:
        xml_str = create_rde_xml_v150(
            ruc=cert_ruc,
            dv_ruc=cert_dv,
            timbrado="12345678",
            establecimiento="001",
            punto_expedicion="001",
            numero_documento="0000001",
            tipo_documento="1",
            fecha=fecha,
            hora=hora,
            csc=codseg
        )
        print(f"✅ XML generado ({len(xml_str)} bytes)")
        print()
    except Exception as e:
        print(f"❌ ERROR al generar XML: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 4) Validar consistencia emisor vs certificado
    print("🔍 Validando consistencia emisor vs certificado en XML...")
    try:
        validate_emisor_in_xml(xml_str, cert_path, cert_password)
        print("✅ Validación OK")
        print()
    except EmisorValidationError as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)
    
    # 5) Firmar el XML
    print("🔐 Firmando XML con certificado (usando signxml)...")
    try:
        signed_xml = sign_de_xml(xml_str, cert_path, cert_password)
        print(f"✅ XML firmado ({len(signed_xml)} bytes)")
        print()
    except XMLDSigError as e:
        print(f"❌ ERROR al firmar XML: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 6) Guardar en Desktop
    output_path = Path.home() / "Desktop" / "sifen_firmado_v150.xml"
    print(f"💾 Guardando XML firmado en: {output_path}")
    try:
        if isinstance(signed_xml, bytes):
            output_path.write_bytes(signed_xml)
        else:
            output_path.write_text(signed_xml, encoding="utf-8")
        print(f"✅ Archivo guardado exitosamente")
        print()
    except Exception as e:
        print(f"❌ ERROR al guardar archivo: {e}")
        sys.exit(1)
    
    # 7) Mostrar resumen final
    print("=" * 70)
    print("✅ XML GENERADO Y FIRMADO EXITOSAMENTE")
    print("=" * 70)
    print()
    print(f"📄 Archivo: {output_path}")
    print()
    print(f"📋 Datos del emisor en el XML:")
    print(f"  - dRucEm: {cert_ruc}")
    print(f"  - dDVEmi: {cert_dv}")
    print(f"  - Match con certificado: ✅ OK")
    print()
    
    # Extraer y mostrar el CDC/Id del XML
    try:
        from lxml import etree
        if isinstance(signed_xml, bytes):
            root = etree.fromstring(signed_xml)
        else:
            root = etree.fromstring(signed_xml.encode("utf-8"))
        
        ns = {"sifen": "http://ekuatia.set.gov.py/sifen/xsd"}
        de_nodes = root.xpath("//sifen:DE", namespaces=ns)
        if not de_nodes:
            de_nodes = root.xpath("//DE")
        
        if de_nodes:
            de_id = de_nodes[0].get("Id")
            if de_id:
                print(f"📋 CDC/Id del DE:")
                print(f"  - {de_id}")
                print(f"  - Longitud: {len(de_id)} dígitos")
                print(f"  - DV final: {de_id[-1]}")
                print()
                
                # Verificar que el CDC contiene el RUC correcto
                # Formato CDC: TT + RUC(8) + DV + ...
                # Posiciones 2-9: RUC con padding
                # Posición 10: DV del RUC
                ruc_en_cdc = de_id[2:10].lstrip("0") or "0"
                dv_en_cdc = de_id[10]
                
                print(f"📋 Verificación CDC:")
                print(f"  - RUC en CDC (pos 2-9): {ruc_en_cdc}")
                print(f"  - DV en CDC (pos 10): {dv_en_cdc}")
                
                if ruc_en_cdc == cert_ruc and dv_en_cdc == cert_dv:
                    print(f"  - ✅ CDC contiene RUC-DV correcto del certificado")
                else:
                    print(f"  - ⚠️  ADVERTENCIA: CDC no coincide con certificado")
                    print(f"     Certificado: {cert_ruc}-{cert_dv}")
                    print(f"     CDC: {ruc_en_cdc}-{dv_en_cdc}")
                print()
    except Exception as e:
        print(f"⚠️  No se pudo extraer CDC del XML: {e}")
        print()
    
    print("🎯 Próximos pasos:")
    print(f"  1) Subir a SIFEN TEST prevalidador:")
    print(f"     https://ekuatia.set.gov.py/consultas-test/validador/")
    print()
    print(f"  2) O usar herramienta de prevalidación:")
    print(f"     python3 tools/prevalidate_http.py '{output_path}' --modo 1 --captcha 'VALOR'")
    print()


if __name__ == "__main__":
    main()
