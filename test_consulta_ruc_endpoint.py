#!/usr/bin/env python3
"""
Script para probar el endpoint correcto de consulta RUC.
Según SIFEN, el endpoint correcto es: /de/ws/consultas/consulta-ruc.wsdl
"""

import requests
from lxml import etree

# URLs para probar
ENDPOINTS = [
    "https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl",
    "https://sifen-test.set.gov.py/de/ws/consultas-ruc/consulta-ruc.wsdl",  # Alternativa
]

# XML de prueba para consulta RUC
SOAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
    <soap:Header/>
    <soap:Body>
        <rEnviConsRUC xmlns="http://ekuatia.set.gov.py/sifen/xsd">
            <dId>202601171340000</dId>
            <dRUCCons>4554737</dRUCCons>
        </rEnviConsRUC>
    </soap:Body>
</soap:Envelope>"""

headers = {
    "Content-Type": "application/xml; charset=utf-8",
    "Accept": "application/xml, text/xml, */*",
    "Connection": "close"
}

def test_endpoint(endpoint):
    print(f"\n🔍 Probando endpoint: {endpoint}")
    try:
        # Extraer URL del WSDL para el POST
        post_url = endpoint.replace("?wsdl", "").replace(".wsdl", "")
        print(f"   POST URL: {post_url}")
        
        response = requests.post(post_url, data=SOAP_XML, headers=headers, timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                root = etree.fromstring(response.content)
                # Verificar tipo de respuesta
                body = root.find(".//{http://www.w3.org/2003/05/soap-envelope}Body")
                if body is not None:
                    first_child = body[0] if len(body) > 0 else None
                    if first_child is not None:
                        tag = first_child.tag
                        print(f"   Respuesta: {tag}")
                        if "rResEnviConsRUC" in tag:
                            print("   ✅ Endpoint correcto (responde con rResEnviConsRUC)")
                            # Extraer código de respuesta
                            cod_res = first_child.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dCodRes")
                            msg_res = first_child.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dMsgRes")
                            if cod_res is not None:
                                print(f"   Código: {cod_res.text}")
                            if msg_res is not None:
                                print(f"   Mensaje: {msg_res.text}")
                        elif "rRetEnviDe" in tag:
                            print("   ❌ Endpoint incorrecto (responde con rRetEnviDe - servicio de recibe)")
                        else:
                            print(f"   ⚠️ Respuesta inesperada")
            except Exception as e:
                print(f"   Error parseando respuesta: {e}")
                print(f"   Raw response: {response.text[:200]}...")
        else:
            print(f"   Error HTTP: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
            
    except Exception as e:
        print(f"   Error: {e}")

if __name__ == "__main__":
    print("🧪 Test de endpoints para consulta RUC")
    print("=" * 50)
    
    for endpoint in ENDPOINTS:
        test_endpoint(endpoint)
    
    print("\n" + "=" * 50)
    print("Conclusión:")
    print("- El endpoint que responde con rResEnviConsRUC es el correcto")
    print("- El endpoint que responde con rRetEnviDe es incorrecto (es de recibe DE)")
