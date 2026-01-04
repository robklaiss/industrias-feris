#!/usr/bin/env python3
"""
Script para inspeccionar el WSDL de siRecepLoteDE (recibe-lote) y mostrar
el formato exacto esperado del SOAP request.
"""
from lxml import etree
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from zeep import Client
    from zeep.wsdl.utils import etree_to_string
except ImportError:
    print("❌ Error: zeep no está instalado")
    print("   Instale con: pip install zeep")
    sys.exit(1)

try:
    from app.sifen_client.config import get_sifen_config
except ImportError as e:
    print(f"❌ Error: No se pudo importar módulos SIFEN: {e}")
    sys.exit(1)


def inspect_wsdl_local(wsdl_path: Path):
    """Inspecciona un WSDL local."""
    print(f"📄 Leyendo WSDL local: {wsdl_path}")
    
    if not wsdl_path.exists():
        print(f"❌ Error: WSDL no encontrado: {wsdl_path}")
        return
    
    try:
        tree = ET.parse(wsdl_path)
        root = tree.getroot()
        
        # Namespaces
        ns = {
            'wsdl': 'http://schemas.xmlsoap.org/wsdl/',
            'soap12': 'http://schemas.xmlsoap.org/wsdl/soap12/',
            'soap11': 'http://schemas.xmlsoap.org/wsdl/soap/',
        }
        
        # Target namespace
        target_ns = root.get('targetNamespace', '')
        print(f"\n🌐 targetNamespace: {target_ns}")
        
        # Buscar operación rEnvioLote
        operations = root.findall('.//wsdl:operation', ns)
        print(f"\n🔍 Operaciones encontradas: {len(operations)}")
        
        for op in operations:
            op_name = op.get('name')
            print(f"\n  📌 Operación: {op_name}")
            
            # Buscar message del input
            input_elem = op.find('wsdl:input', ns)
            input_name = input_elem.get('name') if input_elem is not None else None
            if input_name:
                message = root.find(f'.//wsdl:message[@name="{input_name}"]', ns)
                if message is not None:
                    part = message.find('wsdl:part', ns)
                    if part is not None:
                        element = part.get('element', '')
                        # Extraer namespace y localname del element
                        if ':' in element:
                            prefix, localname = element.split(':', 1)
                            # Buscar namespace del prefix
                            ns_uri = root.get(f'xmlns:{prefix}', '')
                            if not ns_uri:
                                ns_uri = target_ns  # Fallback
                        else:
                            localname = element
                            ns_uri = target_ns
                        print(f"    Message part element: {element}")
                        print(f"      → localname: {localname}")
                        print(f"      → namespace: {ns_uri}")
            
            # Buscar binding para esta operación
            bindings = root.findall(f'.//wsdl:binding/wsdl:operation[@name="{op_name}"]', ns)
            for binding_op in bindings:
                # SOAP 12
                soap12_op = binding_op.find('soap12:operation', ns)
                if soap12_op is not None:
                    soap_action = soap12_op.get('soapAction', '')
                    soap_action_required = soap12_op.get('soapActionRequired', 'false')
                    style = soap12_op.get('style', 'document')
                    print(f"    SOAP 1.2 Binding:")
                    print(f"      soapAction: '{soap_action}' {'(VACÍO)' if soap_action == '' else ''}")
                    print(f"      soapActionRequired: {soap_action_required}")
                    print(f"      style: {style}")
                    if soap_action_required == 'false':
                        print(f"      ⚠️  IMPORTANTE: NO incluir action= en Content-Type")
                
                # Input
                input_elem = binding_op.find('wsdl:input', ns)
                if input_elem is not None:
                    soap12_body = input_elem.find('soap12:body', ns)
                    if soap12_body is not None:
                        use = soap12_body.get('use', 'literal')
                        print(f"      input body use: {use}")
                        if use == 'literal':
                            print(f"      → Body contiene DIRECTAMENTE el elemento del schema (document/literal)")
                            print(f"      → NO hay wrapper de operación")
        
        # Buscar service y port
        services = root.findall('.//wsdl:service', ns)
        for service in services:
            service_name = service.get('name')
            print(f"\n📦 Servicio: {service_name}")
            
            ports = service.findall('.//wsdl:port', ns)
            for port in ports:
                port_name = port.get('name')
                print(f"  🔌 Puerto: {port_name}")
                
                soap12_address = port.find('soap12:address', ns)
                if soap12_address is not None:
                    location = soap12_address.get('location', '')
                    print(f"    location: {location}")
                    # Normalizar endpoint (quitar .wsdl si está)
                    if location.endswith('.wsdl'):
                        endpoint = location[:-5]  # Quitar .wsdl
                        print(f"    → POST endpoint (sin .wsdl): {endpoint}")
        
    except Exception as e:
        print(f"❌ Error al parsear WSDL: {e}")
        import traceback
        traceback.print_exc()


def inspect_wsdl_remote(wsdl_url: str):
    """Inspecciona un WSDL remoto usando Zeep."""
    print(f"📡 Cargando WSDL remoto: {wsdl_url}")
    
    try:
        client = Client(wsdl_url)
        
        # Buscar servicio
        for service_name, service in client.wsdl.services.items():
            print(f"\n📦 Servicio: {service_name}")
            
            for port_name, port in service.ports.items():
                print(f"  🔌 Puerto: {port_name}")
                
                # Buscar operación rEnvioLote
                for operation_name, operation in port.binding._operations.items():
                    if 'rEnvioLote' in operation_name or 'EnvioLote' in operation_name:
                        print(f"\n  📌 Operación: {operation_name}")
                        print(f"    soapAction: '{operation.soap_action}'")
                        print(f"    style: {operation.style}")
                        print(f"    input: {operation.input.signature()}")
                        print(f"    output: {operation.output.signature()}")
        
        # Target namespace desde el documento WSDL
        try:
            # Intentar obtener targetNamespace de diferentes formas
            target_ns = None
            if hasattr(client.wsdl, 'target_namespace'):
                target_ns = client.wsdl.target_namespace  # type: ignore
            elif hasattr(client.wsdl, 'types') and hasattr(client.wsdl.types, 'doc'):
                doc = client.wsdl.types.doc  # type: ignore
                if hasattr(doc, 'targetNamespace'):
                    target_ns = doc.targetNamespace  # type: ignore
            print(f"\n🌐 targetNamespace: {target_ns or '(no encontrado)'}")
        except Exception:
            print(f"\n🌐 targetNamespace: (no disponible)")
        
    except Exception as e:
        print(f"❌ Error al cargar WSDL remoto: {e}")
        import traceback
        traceback.print_exc()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Inspecciona el WSDL de siRecepLoteDE (recibe-lote)"
    )
    parser.add_argument(
        '--env',
        choices=['test', 'prod'],
        default='test',
        help='Ambiente (default: test)'
    )
    parser.add_argument(
        '--local',
        type=Path,
        help='Ruta al WSDL local (opcional)'
    )
    
    args = parser.parse_args()
    
    if args.local:
        inspect_wsdl_local(args.local)
    else:
        # Usar WSDL local del repo
        repo_root = Path(__file__).parent.parent.parent
        wsdl_local = repo_root / "rshk-jsifenlib" / "docs" / "set" / "test" / "v150" / "wsdl" / "async" / "recibe-lote.wsdl"
        
        if wsdl_local.exists():
            inspect_wsdl_local(wsdl_local)
        else:
            print(f"⚠️  WSDL local no encontrado: {wsdl_local}")
            print("   Intentando cargar WSDL remoto...")
            
            config = get_sifen_config(env=args.env)
            wsdl_url = config.get_soap_service_url("recibe_lote")
            if not wsdl_url.endswith("?wsdl"):
                wsdl_url += "?wsdl"
            
            inspect_wsdl_remote(wsdl_url)


if __name__ == "__main__":
    main()

