#!/usr/bin/env python3
"""
Simple script to check WSDL structure
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'tesaka-cv'))

from app.sifen_client import SoapClient, get_sifen_config

def check_wsdl_structure():
    """Check WSDL structure"""
    config = get_sifen_config('test')
    soap_client = SoapClient(config)
    wsdl_url = config.get_soap_service_url("recibe_lote")
    zeep_client = soap_client._get_zeep_client(wsdl_url)
    
    print("=== WSDL Structure ===\n")
    
    # List services
    print("Services:")
    for name, service in zeep_client.wsdl.services.items():
        print(f"  {name}:")
        for port_name, port in service.ports.items():
            print(f"    Port: {port_name}")
            print(f"    Binding: {port.binding}")
            print(f"    Binding type: {type(port.binding)}")
    
    # Check port types
    print("\nPort Types:")
    for name, port_type in zeep_client.wsdl.port_types.items():
        print(f"  {name}:")
        if hasattr(port_type, 'operations'):
            for op_name, op in port_type.operations.items():
                print(f"    Operation: {op_name}")
    
    # Check what we're actually sending
    print("\nChecking our actual SOAP request structure...")
    print("From recent artifacts, we're sending:")
    print("  <sifen:rEnvioLote> with xmlns:sifen=\"http://ekuatia.set.gov.py/sifen/xsd\"")
    
    soap_client.close()

if __name__ == "__main__":
    check_wsdl_structure()
