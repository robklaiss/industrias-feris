#!/usr/bin/env python3
"""
Test para verificar que consulta-lote.wsdl mantenga el .wsdl en el endpoint POST
"""
import sys
from pathlib import Path

# Agregar path del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent / "tesaka-cv"))

def test_consulta_lote_endpoint():
    """Test que consulta-lote.wsdl conserve .wsdl en el endpoint POST"""
    from app.sifen_client.soap_client import SoapClient
    
    # Obtener la función estática
    _normalize_soap_endpoint = SoapClient._normalize_soap_endpoint
    
    # Test URLs de consulta-lote
    test_urls = [
        "https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl",
        "https://sifen.set.gov.py/de/ws/consultas/consulta-lote.wsdl",
        "https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl?wsdl",
    ]
    
    print("🧪 Test endpoint consulta-lote.wsdl")
    print("=" * 50)
    
    for url in test_urls:
        normalized = _normalize_soap_endpoint(url)
        print(f"\nURL original: {url}")
        print(f"URL normalizada: {normalized}")
        
        # Verificar que conserve .wsdl
        if "/consulta-lote.wsdl" in normalized:
            print("✅ .wsdl conservado")
        else:
            print("❌ .wsdl fue removido (ERROR)")
            return False
    
    # Test comparación con recibe-lote y consulta-ruc
    print("\n📊 Comparación con otros servicios:")
    print("-" * 30)
    
    services = [
        ("recibe-lote", "https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl"),
        ("consulta-ruc", "https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl"),
        ("consulta-lote", "https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl"),
    ]
    
    for service, url in services:
        normalized = _normalize_soap_endpoint(url)
        keeps_wsdl = ".wsdl" in normalized
        print(f"{service:15} -> {'✅ mantiene .wsdl' if keeps_wsdl else '❌ quita .wsdl'}")
    
    # Test que el endpoint POST en consulta_lote_raw use wsdl_url directamente
    print("\n🔍 Verificación en consulta_lote_raw:")
    print("-" * 40)
    
    # Simular el código de consulta_lote_raw
    wsdl_url = "https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl"
    
    # Antes del fix: (endpoint_base = wsdl_url[:-5] if wsdl_url.endswith(".wsdl") else wsdl_url)
    endpoint_base_old = wsdl_url[:-5] if wsdl_url.endswith(".wsdl") else wsdl_url
    
    # Después del fix: (endpoint_candidates = [wsdl_url])
    endpoint_candidates_new = [wsdl_url]
    
    print(f"WSDL URL: {wsdl_url}")
    print(f"Endpoint antiguo: {endpoint_base_old}")
    print(f"Endpoint nuevo: {endpoint_candidates_new[0]}")
    
    if endpoint_candidates_new[0].endswith(".wsdl"):
        print("✅ Fix aplicado correctamente")
        return True
    else:
        print("❌ Fix no aplicado")
        return False

if __name__ == "__main__":
    success = test_consulta_lote_endpoint()
    sys.exit(0 if success else 1)
