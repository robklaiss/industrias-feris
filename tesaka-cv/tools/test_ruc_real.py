#!/usr/bin/env python3
"""
Test rápido: Verificar que el XML generado use RUC real del emisor (no dummy)

Uso:
    export SIFEN_EMISOR_RUC="4554737-8"
    python -m tools.test_ruc_real
"""
import sys
import os
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

def main():
    # Verificar que SIFEN_EMISOR_RUC esté configurado
    emisor_ruc = os.getenv("SIFEN_EMISOR_RUC")
    if not emisor_ruc:
        print("❌ Error: SIFEN_EMISOR_RUC no está configurado.")
        print("   Configure con: export SIFEN_EMISOR_RUC='4554737-8'")
        return 1
    
    print(f"✓ SIFEN_EMISOR_RUC configurado: {emisor_ruc}")
    
    # Separar RUC y DV
    if '-' in emisor_ruc:
        ruc_expected, dv_expected = emisor_ruc.split('-', 1)
        ruc_expected = ruc_expected.strip()
        dv_expected = dv_expected.strip()
    else:
        print(f"❌ Error: SIFEN_EMISOR_RUC debe tener formato RUC-DV (ej: 4554737-8)")
        return 1
    
    print(f"   RUC esperado: {ruc_expected}")
    print(f"   DV esperado: {dv_expected}\n")
    
    # Cargar XML smoke existente
    artifacts_dir = Path(__file__).parent.parent / "artifacts"
    smoke_xml_path = artifacts_dir / "sirecepde_smoke_20251227_011729.xml"
    
    if not smoke_xml_path.exists():
        print(f"⚠️  XML smoke no encontrado: {smoke_xml_path}")
        print("   Generando nuevo DE con RUC real...\n")
        
        # Generar nuevo DE con RUC real
        from tools.build_de import build_de_xml
        de_xml = build_de_xml(
            ruc=ruc_expected,
            timbrado="12345678",
            dv_ruc=dv_expected
        )
        
        de_path = artifacts_dir / "de_real_test.xml"
        de_path.write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n{de_xml}', encoding="utf-8")
        print(f"✓ DE generado: {de_path}")
        
        # Generar siRecepDE
        from tools.build_sirecepde import build_sirecepde_xml
        sirecepde_xml = build_sirecepde_xml(de_xml, d_id="1")
        
        sirecepde_path = artifacts_dir / "sirecepde_real_test.xml"
        sirecepde_path.write_bytes(sirecepde_xml.encode('utf-8'))
        print(f"✓ siRecepDE generado: {sirecepde_path}\n")
        
        xml_to_check = sirecepde_path
    else:
        print(f"📄 Verificando XML existente: {smoke_xml_path}\n")
        xml_to_check = smoke_xml_path
    
    # Verificar RUC en el XML
    xml_content = xml_to_check.read_text(encoding="utf-8")
    
    # Buscar dRucEm y dDVEmi
    import re
    ruc_match = re.search(r'<dRucEm>([^<]+)</dRucEm>', xml_content)
    dv_match = re.search(r'<dDVEmi>([^<]+)</dDVEmi>', xml_content)
    
    if not ruc_match:
        print("❌ Error: No se encontró <dRucEm> en el XML")
        return 1
    
    if not dv_match:
        print("❌ Error: No se encontró <dDVEmi> en el XML")
        return 1
    
    ruc_found = ruc_match.group(1).strip()
    dv_found = dv_match.group(1).strip()
    
    print(f"📋 RUC encontrado en XML:")
    print(f"   <dRucEm>{ruc_found}</dRucEm>")
    print(f"   <dDVEmi>{dv_found}</dDVEmi>\n")
    
    # Validar
    if ruc_found == "80012345":
        print("❌ ERROR: El XML todavía contiene RUC dummy (80012345)")
        print("   El XML debe usar el RUC real del emisor.")
        return 1
    
    if ruc_found != ruc_expected:
        print(f"⚠️  ADVERTENCIA: RUC en XML ({ruc_found}) no coincide con SIFEN_EMISOR_RUC ({ruc_expected})")
        print("   Regenerar el XML con: python -m tools.build_de --output de_real.xml")
        return 1
    
    if dv_found != dv_expected:
        print(f"⚠️  ADVERTENCIA: DV en XML ({dv_found}) no coincide con SIFEN_EMISOR_RUC ({dv_expected})")
        return 1
    
    print("✅ ÉXITO: El XML usa el RUC real del emisor")
    print(f"   RUC: {ruc_found}-{dv_found}")
    print(f"   Coincide con SIFEN_EMISOR_RUC: {emisor_ruc}\n")
    
    # Mostrar comando para verificar con grep
    print("📋 Verificar con grep:")
    print(f"   grep -nE '<dRucEm>|<dDVEmi>' {xml_to_check}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

