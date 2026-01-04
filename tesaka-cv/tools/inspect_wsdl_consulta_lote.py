#!/usr/bin/env python3
"""
Script para inspeccionar el WSDL de consulta-lote y mostrar
el formato exacto esperado del SOAP request.
"""
import sys
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app.sifen_client.config import get_sifen_config
    from app.sifen_client.wsdl_introspect import inspect_wsdl
except ImportError as e:
    print(f"❌ Error: No se pudo importar módulos SIFEN: {e}")
    sys.exit(1)


def main():
    import argparse
    import json
    
    parser = argparse.ArgumentParser(
        description="Inspecciona el WSDL de consulta-lote (siConsLoteDE)"
    )
    parser.add_argument(
        '--env',
        choices=['test', 'prod'],
        default='test',
        help='Ambiente (default: test)'
    )
    
    args = parser.parse_args()
    
    # Obtener URL del WSDL desde config
    config = get_sifen_config(env=args.env)
    wsdl_url = config.get_soap_service_url("consulta_lote")
    
    # Asegurar que tenga ?wsdl
    if not wsdl_url.endswith("?wsdl") and not wsdl_url.endswith(".wsdl"):
        wsdl_url = wsdl_url + "?wsdl"
    
    print(f"📡 Inspeccionando WSDL: {wsdl_url}")
    print(f"🌍 Ambiente: {args.env}\n")
    
    try:
        wsdl_info = inspect_wsdl(wsdl_url, operation_name=None)
        
        print("=" * 80)
        print("RESUMEN DE INSPECCIÓN WSDL (consulta-lote)")
        print("=" * 80)
        print(f"\n🌐 targetNamespace: {wsdl_info['target_namespace']}")
        print(f"📦 Servicio: consulta-lote")
        print(f"🔌 Operación: {wsdl_info['operation_name']}")
        print(f"📋 SOAP Version: {wsdl_info['soap_version']}")
        print(f"📍 POST URL: {wsdl_info['url_post']}")
        print(f"\n📝 Body Root Element:")
        if wsdl_info['body_root_qname']:
            print(f"   Localname: {wsdl_info['body_root_qname']['localname']}")
            print(f"   Namespace: {wsdl_info['body_root_qname']['namespace']}")
        print(f"\n🎯 SOAP Action:")
        print(f"   soapAction: '{wsdl_info['soap_action']}'")
        print(f"   actionRequired: {wsdl_info['action_required']}")
        print(f"\n📐 Style/Use:")
        print(f"   style: {wsdl_info['style']}")
        print(f"   use: {wsdl_info['use']}")
        print(f"   is_wrapped: {wsdl_info['is_wrapped']}")
        
        # Mostrar estructura esperada
        print(f"\n📄 Estructura SOAP Body esperada:")
        if wsdl_info['body_root_qname']:
            root_local = wsdl_info['body_root_qname']['localname']
            root_ns = wsdl_info['body_root_qname']['namespace']
            
            if wsdl_info['is_wrapped']:
                print(f"   <soap:Body>")
                print(f"     <tns:{wsdl_info['operation_name']} xmlns:tns=\"{wsdl_info['target_namespace']}\">")
                print(f"       <xsd:{root_local} xmlns:xsd=\"{root_ns}\">")
                print(f"         <xsd:dProtConsLote>...</xsd:dProtConsLote>")
                print(f"       </xsd:{root_local}>")
                print(f"     </tns:{wsdl_info['operation_name']}>")
                print(f"   </soap:Body>")
            else:
                print(f"   <soap:Body>")
                print(f"     <xsd:{root_local} xmlns:xsd=\"{root_ns}\">")
                print(f"       <xsd:dProtConsLote>...</xsd:dProtConsLote>")
                print(f"     </xsd:{root_local}>")
                print(f"   </soap:Body>")
        
        print("\n" + "=" * 80)
        
        # Guardar JSON para referencia
        artifacts_dir = Path(__file__).parent.parent / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        json_path = artifacts_dir / "wsdl_inspected_consulta_lote.json"
        json_path.write_text(json.dumps(wsdl_info, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"💾 Información completa guardada en: {json_path}")
        
    except Exception as e:
        print(f"❌ Error al inspeccionar WSDL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

