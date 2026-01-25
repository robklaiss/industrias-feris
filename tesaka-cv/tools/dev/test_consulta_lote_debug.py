#!/usr/bin/env python3
"""
Script para depurar consulta_lote_raw
"""
import sys
from pathlib import Path

# Agregar paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.sifen_client.soap_client import build_consulta_lote_raw_envelope

def test_consulta_lote_debug():
    """Genera y muestra el SOAP de consulta_lote"""
    print("🔍 Generando SOAP para consulta_lote_raw...")
    
    d_id = "test123456789"
    d_prot = "123456789012345"
    
    soap_bytes = build_consulta_lote_raw_envelope(d_id, d_prot)
    soap_str = soap_bytes.decode("utf-8")
    
    print("\n📋 SOAP generado:")
    print("=" * 60)
    print(soap_str)
    print("=" * 60)
    
    # Validaciones
    print("\n🔍 Validaciones:")
    
    if "<rEnviConsLoteDe" in soap_str:
        print("✅ rEnviConsLoteDe presente")
    else:
        print("❌ rEnviConsLoteDe NO encontrado")
    
    if "<dId>test123456789</dId>" in soap_str:
        print("✅ dId presente")
    else:
        print("❌ dId incorrecto")
    
    if "<dProtConsLote>123456789012345</dProtConsLote>" in soap_str:
        print("✅ dProtConsLote presente")
    else:
        print("❌ dProtConsLote incorrecto")
    
    if 'xmlns="http://ekuatia.set.gov.py/sifen/xsd"' in soap_str:
        print("✅ Namespace SIFEN correcto")
    else:
        print("❌ Namespace SIFEN incorrecto")
    
    # Guardar para análisis
    output_path = Path("/tmp/consulta_lote_debug.xml")
    output_path.write_text(soap_str, encoding="utf-8")
    print(f"\n💾 SOAP guardado en: {output_path}")
    
    return 0

if __name__ == "__main__":
    sys.exit(test_consulta_lote_debug())
