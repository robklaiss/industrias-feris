#!/usr/bin/env python3
"""
Consulta estado de documento electrónico en SIFEN
"""

import sys
import os
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.soap_client import SoapClient

def consultar_estado(cdc, env='test'):
    """Consulta el estado de un documento por CDC"""
    
    print(f"🔍 Consultando estado del documento")
    print(f"   CDC: {cdc}")
    print(f"   Ambiente: {env}")
    
    try:
        # Crear cliente SOAP
        client = SoapClient(env=env)
        
        # Construir request
        from lxml import etree
        SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
        
        # XML de consulta
        xml_req = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Body>
        <ns0:rEnviConsDe xmlns:ns0="{SIFEN_NS}">
            <ns0:dId>1</ns0:dId>
            <ns0:dProtCons>
                <ns1:dCDC xmlns:ns1="{SIFEN_NS}">{cdc}</ns1:dCDC>
            </ns0:dProtCons>
        </ns0:rEnviConsDe>
    </soap12:Body>
</soap12:Envelope>"""
        
        # Enviar consulta
        print("📡 Enviando consulta a SIFEN...")
        response = client.consulta_estado(xml_req.encode('utf-8'))
        
        # Parsear respuesta
        root = etree.fromstring(response)
        
        # Extraer datos
        ns = {'sif': SIFEN_NS, 'soap': 'http://www.w3.org/2003/05/soap-envelope'}
        
        resp = root.find('.//sif:rEnviConsDeRes', namespaces=ns)
        if resp is not None:
            cod_res = resp.find('sif:dCodRes', namespaces=ns)
            msg_res = resp.find('sif:dMsgRes', namespaces=ns)
            
            print("\n📊 Respuesta de SIFEN:")
            print(f"   Código: {cod_res.text if cod_res is not None else 'N/A'}")
            print(f"   Mensaje: {msg_res.text if msg_res is not None else 'N/A'}")
            
            # Detalles adicionales si hay
            dProtCons = resp.find('sif:dProtCons', namespaces=ns)
            if dProtCons is not None:
                print("\n📋 Detalles del documento:")
                for child in dProtCons:
                    if child.text:
                        print(f"   {child.tag.split('}')[-1]}: {child.text}")
        else:
            print("❌ No se pudo parsear la respuesta")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description="Consultar estado de documento SIFEN")
    parser.add_argument('--cdc', required=True, help='CDC del documento')
    parser.add_argument('--env', choices=['test', 'prod'], default='test', 
                       help='Ambiente (default: test)')
    
    args = parser.parse_args()
    
    # Validar formato CDC
    if len(args.cdc) != 44:
        print("❌ CDC inválido. Debe tener 44 dígitos.")
        sys.exit(1)
    
    consultar_estado(args.cdc, args.env)

if __name__ == "__main__":
    main()
