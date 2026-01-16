#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOAP 1.2 Builder para SIFEN v150 - RAW BYTES VERSION
Inserta XML firmado como BYTES RAW sin reparsear para NO romper la firma

REGLA DE ORO:
- El rDE firmado se inserta como bytes raw (sin lxml parse/reserialización)
- NO cambia prefijos, NO agrega xmlns:xsi, NO altera whitespace
- Construye SOAP por concatenación de bytes
"""

import sys
import time
import subprocess
import argparse
from pathlib import Path


def generate_did() -> str:
    """Genera un dId válido (timestamp en milisegundos, <= 15 dígitos)"""
    timestamp_ms = int(time.time() * 1000)
    return str(timestamp_ms)[:15]


def normalize_xml_bytes(xml_bytes: bytes) -> bytes:
    """
    Normaliza bytes del XML firmado:
    - Remueve BOM UTF-8 si existe
    - Remueve declaración XML si existe
    - Retorna solo el contenido del elemento raíz
    """
    # Remover BOM UTF-8 (0xEF 0xBB 0xBF)
    if xml_bytes.startswith(b'\xef\xbb\xbf'):
        xml_bytes = xml_bytes[3:]
    
    # Remover declaración XML si existe
    if xml_bytes.startswith(b'<?xml'):
        end_idx = xml_bytes.find(b'?>') + 2
        xml_bytes = xml_bytes[end_idx:]
    
    # Lstrip whitespace (espacios, tabs, newlines)
    xml_bytes = xml_bytes.lstrip(b' \t\r\n')
    
    return xml_bytes


def build_soap_envelope_raw(rde_raw_bytes: bytes, d_id: str) -> bytes:
    """
    Construye envelope SOAP 1.2 insertando rDE como BYTES RAW
    NO usa lxml - concatenación pura de bytes
    """
    
    # Construir SOAP por concatenación de bytes
    soap_prefix = f"""<?xml version='1.0' encoding='UTF-8'?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
  <env:Header/>
  <env:Body>
    <s:rEnviDe xmlns:s="http://ekuatia.set.gov.py/sifen/xsd">
      <s:dId>{d_id}</s:dId>
      <s:xDE>
""".encode('utf-8')
    
    soap_suffix = b"""
      </s:xDE>
    </s:rEnviDe>
  </env:Body>
</env:Envelope>"""
    
    # Concatenar: prefix + rDE raw + suffix
    soap_bytes = soap_prefix + rde_raw_bytes + soap_suffix
    
    return soap_bytes


def selftest(soap_path: Path, original_xml_path: Path) -> bool:
    """
    Prueba de aceptación: verifica que el SOAP no alteró la firma
    Retorna True si OK, False si falló
    """
    print("\n🧪 SELFTEST: Verificando que SOAP no alteró la firma...")
    
    # 1. Extraer rDE del SOAP
    extract_script = Path(__file__).parent / "sifen_extract_xde_from_soap.py"
    extracted_path = Path("/tmp/extracted_rDE_selftest.xml")
    
    try:
        result = subprocess.run([
            sys.executable,
            str(extract_script),
            str(soap_path),
            "--out", str(extracted_path)
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            print(f"❌ SELFTEST FAIL: No se pudo extraer rDE del SOAP")
            print(result.stdout)
            print(result.stderr)
            return False
    except Exception as e:
        print(f"❌ SELFTEST FAIL: Error extrayendo rDE: {e}")
        return False
    
    # 2. Verificar firma del rDE extraído
    verify_script = Path(__file__).parent / "sifen_signature_crypto_verify.py"
    
    try:
        result = subprocess.run([
            sys.executable,
            str(verify_script),
            str(extracted_path)
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"❌ SELFTEST FAIL: SOAP builder alteró el XML firmado (firma inválida tras extracción)")
            print(f"   Exit code: {result.returncode}")
            print(f"   Stdout: {result.stdout[-500:]}")
            return False
        
        print("✅ SELFTEST OK: Firma preservada correctamente")
        return True
        
    except Exception as e:
        print(f"❌ SELFTEST FAIL: Error verificando firma: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="SOAP 1.2 Builder para SIFEN v150 (raw bytes, no altera firma)"
    )
    parser.add_argument("in_xml", help="Path al XML firmado (rDE)")
    parser.add_argument("out_soap", nargs='?', help="Path de salida para SOAP")
    parser.add_argument("--out", help="Path de salida alternativo")
    parser.add_argument("--selftest", action="store_true", 
                       help="Ejecutar prueba de aceptación (verifica que no se alteró la firma)")
    
    args = parser.parse_args()
    
    # Determinar output path (prioridad: posicional > --out > default)
    if args.out_soap:
        output_path = Path(args.out_soap)
    elif args.out:
        output_path = Path(args.out)
    else:
        output_path = Path("/tmp/sifen_rEnviDe_soap12.xml")
    
    # Validar input
    input_path = Path(args.in_xml)
    if not input_path.exists():
        print(f"❌ ERROR: No existe {input_path}")
        sys.exit(1)
    
    print("=== SOAP 1.2 BUILDER SIFEN v150 (RAW BYTES) ===")
    print(f"📂 XML firmado: {input_path}")
    print(f"📦 SOAP output: {output_path}")
    
    try:
        # 1. Leer XML firmado como bytes raw
        print("📖 Leyendo XML firmado como bytes raw...")
        xml_bytes = input_path.read_bytes()
        
        # 2. Normalizar (remover BOM, declaración XML)
        print("🔧 Normalizando bytes (remover BOM/declaración XML)...")
        rde_raw_bytes = normalize_xml_bytes(xml_bytes)
        
        # 3. Generar dId
        d_id = generate_did()
        print(f"🔑 dId generado: {d_id}")
        
        # 4. Construir SOAP por concatenación de bytes
        print("🔨 Construyendo SOAP envelope (concatenación raw, sin lxml)...")
        soap_bytes = build_soap_envelope_raw(rde_raw_bytes, d_id)
        
        # 5. Guardar SOAP
        output_path.write_bytes(soap_bytes)
        print(f"✅ SOAP guardado: {output_path}")
        print(f"📊 Tamaño: {len(soap_bytes)} bytes")
        
        # 6. Preview
        soap_text = soap_bytes.decode('utf-8')
        lines = soap_text.split('\n')
        print("\n📋 SOAP preview (primeras 10 líneas):")
        print("="*60)
        for i, line in enumerate(lines[:10]):
            print(f"{i+1:2d}: {line[:80]}")
        if len(lines) > 10:
            print("...")
        print("="*60)
        
        # 7. Selftest si se solicitó
        if args.selftest:
            if not selftest(output_path, input_path):
                print("\n❌ SELFTEST FALLÓ - SOAP alteró la firma")
                sys.exit(2)
        
        print("\n🚀 SOAP listo para enviar a SIFEN v150")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


# PRUEBA DE ACEPTACIÓN (A/B/C/D):
# 
# A) Verificar XML original firmado:
#    python tools/sifen_signature_crypto_verify.py <xml_real_firmado>
#    Debe dar: EXIT 0 (firma válida)
#
# B) Construir SOAP:
#    python tools/sifen_build_soap12_envelope.py <xml_real_firmado> /tmp/sifen_rEnviDe_soap12.xml
#    Debe generar SOAP sin errores
#
# C) Extraer rDE desde SOAP:
#    python tools/sifen_extract_xde_from_soap.py /tmp/sifen_rEnviDe_soap12.xml --out /tmp/extracted_rDE.xml
#    Debe extraer rDE sin errores
#
# D) Verificar rDE extraído:
#    python tools/sifen_signature_crypto_verify.py /tmp/extracted_rDE.xml
#    Debe dar: EXIT 0 (firma válida, SIN "Digest mismatch")
#
# Si D da EXIT 0 => SOAP builder NO alteró la firma ✅
# Si D da EXIT 2 con "Digest mismatch" => SOAP builder ROMPIÓ la firma ❌
#
# SELFTEST AUTOMÁTICO:
#    python tools/sifen_build_soap12_envelope.py <xml_real_firmado> /tmp/test.xml --selftest
#    Ejecuta A/B/C/D automáticamente y falla con exit 2 si D falla
