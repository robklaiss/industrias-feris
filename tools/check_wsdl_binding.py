#!/usr/bin/env python3
"""
Check WSDL binding and QName for SIFEN siRecepLoteDE operation
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'tesaka-cv'))

from app.sifen_client import SoapClient, get_sifen_config
from zeep import Client

def check_wsdl_details():
    """Check WSDL binding and operation details"""
    config = get_sifen_config('test')
    
    # Create a SoapClient to access the zeep client
    soap_client = SoapClient(config)
    
    # Get the zeep client for the recibe_lote service
    wsdl_url = config.get_soap_service_url("recibe_lote")
    zeep_client = soap_client._get_zeep_client(wsdl_url)
    
    print("=== WSDL Binding Analysis ===\n")
    
    # Check service
    print("1. Services available:")
    for service in zeep_client.wsdl.services.values():
        print(f"   - {service.name}")
        for port in service.ports.values():
            print(f"     Port: {port.name}")
            print(f"     Binding: {port.binding.name}")
    
    print("\n2. Bindings:")
    for binding in zeep_client.wsdl.bindings.values():
        print(f"   - {binding.name}")
        # Handle different binding types
        if hasattr(binding, 'type'):
            print(f"     Type: {binding.type}")
        else:
            print(f"     Type: {type(binding).__name__}")
        if hasattr(binding, 'port_type') and binding.port_type:
            print(f"     Port Type: {binding.port_type.name}")
        print(f"     Operations:")
        for op in binding.operations.values():
            print(f"       - {op.name}")
            print(f"         Input: {op.input.signature()}")
            print(f"         Output: {op.output.signature()}")
    
    print("\n3. Port Types:")
    for port_type in zeep_client.wsdl.port_types.values():
        print(f"   - {port_type.name}")
        for op in port_type.operations.values():
            print(f"     - {op.name}")
            print(f"       Input: {op.input.signature()}")
            print(f"       Output: {op.output.signature()}")
    
    print("\n4. Specific check for siRecepLoteDE:")
    # Try to get the specific operation from the actual service
    try:
        # Use the actual service name we found
        service = zeep_client.wsdl.services['de-ws-async-recibaService']
        port = service.ports['de-ws-async-recibaSoap12']
        binding = port.binding
        
        print(f"\n   Service: de-ws-async-recibaService")
        print(f"   Port: de-ws-async-recibaSoap12")
        print(f"   Binding: {binding.name}")
        if hasattr(binding, 'type'):
            print(f"   Binding Type: {binding.type}")
        else:
            print(f"   Binding Type: {type(binding).__name__}")
        
        # Check the operation
        if 'siRecepLoteDE' in binding.operations:
            op = binding.operations['siRecepLoteDE']
            print(f"\n   Operation siRecepLoteDE:")
            print(f"     Input message: {op.input.message.text}")
            print(f"     Input parts:")
            for part in op.input.parts:
                print(f"       - {part.name}: {part.element}")
            print(f"     Output message: {op.output.message.text}")
            print(f"     Output parts:")
            for part in op.output.parts:
                print(f"       - {part.name}: {part.element}")
        else:
            print("   siRecepLoteDE not found in binding operations!")
            print(f"   Available operations: {list(binding.operations.keys())}")
            
    except KeyError as e:
        print(f"   Service/port not found: {e}")
        # Try to find the operation in any binding
        print("\n   Searching for siRecepLoteDE in all bindings:")
        found = False
        for binding_name, binding in zeep_client.wsdl.bindings.items():
            if 'siRecepLoteDE' in binding.operations:
                op = binding.operations['siRecepLoteDE']
                print(f"     Found in binding: {binding_name}")
                print(f"     Input: {op.input.signature()}")
                found = True
        if not found:
            print("     siRecepLoteDE not found in any binding!")
            
    except Exception as e:
        print(f"   Error accessing service details: {e}")
    
    print("\n5. Target namespace:")
    print(f"   WSDL Target Namespace: {zeep_client.wsdl.target_namespace}")
    
    print("\n6. XML Schema definitions:")
    for schema in zeep_client.wsdl.types.schemas:
        print(f"   Schema targetNamespace: {schema.target_namespace}")
        elements = list(schema.elements.keys())
        if elements:
            print(f"   First few elements: {elements[:5]}")
    
    # Check the actual message we're sending
    print("\n7. Checking our SOAP structure:")
    print("   We're sending:")
    print("   <sifen:rEnvioLote>")
    print("     <sifen:dId>...</sifen:dId>")
    print("     <sifen:xDE>...</sifen:xDE>")
    print("   </sifen:rEnvioLote>")
    print("\n   With namespace: xmlns:sifen=\"http://ekuatia.set.gov.py/sifen/xsd\"")
    
    # Check what the WSDL expects
    print("\n8. Checking what WSDL expects for siRecepLoteDE input:")
    try:
        # Try to find the operation in any binding
        op = None
        for binding in zeep_client.wsdl.bindings.values():
            if 'siRecepLoteDE' in binding.operations:
                op = binding.operations['siRecepLoteDE']
                break
        
        if op:
            # Get the input element
            input_part = list(op.input.parts)[0]
            print(f"   Expected input element: {input_part.element}")
            
            # Check if it's wrapped or bare
            print(f"   Input signature: {op.input.signature()}")
            
            # Get more details about the expected element
            if hasattr(input_part, 'element') and input_part.element:
                print(f"   Element namespace: {input_part.element.namespace}")
                print(f"   Element name: {input_part.element.localname}")
        else:
            print("   Operation siRecepLoteDE not found!")
        
    except Exception as e:
        print(f"   Error: {e}")
    
    soap_client.close()

if __name__ == "__main__":
    check_wsdl_details()
