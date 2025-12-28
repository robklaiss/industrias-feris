#!/usr/bin/env python3
"""
CLI para enviar XML siRecepDE (rEnviDe) al servicio SOAP de Recepción de SIFEN

Uso:
    python -m tools.send_sirecepde --env test --xml artifacts/sirecepde_20251226_233653.xml
    python -m tools.send_sirecepde --env test --xml latest
"""
import sys
import argparse
import os
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
import base64
import json

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from zeep import Client, Settings
    from zeep.transports import Transport
    from requests import Session
    from requests.auth import HTTPBasicAuth
except ImportError as e:
    print("❌ Error: zeep no está instalado")
    print("   Instala con: pip install zeep")
    print()
    print(f"   Error detallado: {e}")
    sys.exit(1)

from dotenv import load_dotenv

load_dotenv()


def find_latest_sirecepde(artifacts_dir: Path) -> Optional[Path]:
    """
    Encuentra el archivo sirecepde más reciente en artifacts/
    
    Args:
        artifacts_dir: Directorio donde buscar archivos
        
    Returns:
        Path al archivo más reciente o None
    """
    if not artifacts_dir.exists():
        return None
    
    sirecepde_files = list(artifacts_dir.glob("sirecepde_*.xml"))
    if not sirecepde_files:
        return None
    
    # Ordenar por fecha de modificación (más reciente primero)
    sirecepde_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return sirecepde_files[0]


def resolve_xml_path(xml_arg: str, artifacts_dir: Path) -> Path:
    """
    Resuelve el path al XML (puede ser 'latest' o un path específico)
    
    Args:
        xml_arg: Argumento XML ('latest' o path)
        artifacts_dir: Directorio de artifacts
        
    Returns:
        Path al archivo XML
    """
    if xml_arg.lower() == "latest":
        xml_path = find_latest_sirecepde(artifacts_dir)
        if not xml_path:
            raise FileNotFoundError(
                f"No se encontró ningún archivo sirecepde_*.xml en {artifacts_dir}"
            )
        return xml_path
    
    xml_path = Path(xml_arg)
    if not xml_path.exists():
        # Intentar como path relativo a artifacts
        artifacts_xml = artifacts_dir / xml_arg
        if artifacts_xml.exists():
            return artifacts_xml
        raise FileNotFoundError(f"Archivo XML no encontrado: {xml_arg}")
    
    return xml_path


def load_certificate_config() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Carga configuración de certificados desde variables de entorno
    
    Returns:
        Tupla (cert_pem, key_pem, p12_path, p12_password, ca_bundle)
    """
    cert_pem = os.getenv("SIFEN_CERT_PEM")
    key_pem = os.getenv("SIFEN_KEY_PEM")
    p12_path = os.getenv("SIFEN_P12_PATH")
    p12_password = os.getenv("SIFEN_P12_PASSWORD")
    ca_bundle = os.getenv("SIFEN_CA_BUNDLE")
    
    return cert_pem, key_pem, p12_path, p12_password, ca_bundle


def setup_mtls_session(cert_pem: Optional[str] = None,
                       key_pem: Optional[str] = None,
                       p12_path: Optional[str] = None,
                       p12_password: Optional[str] = None,
                       ca_bundle: Optional[str] = None) -> Session:
    """
    Configura una sesión requests con mTLS (mutual TLS)
    
    Args:
        cert_pem: Path al certificado PEM
        key_pem: Path a la clave privada PEM
        p12_path: Path al certificado P12
        p12_password: Contraseña del P12
        ca_bundle: Path al bundle CA para verificación
        
    Returns:
        Session configurada con mTLS
    """
    session = Session()
    
    # Verificar que tenemos certificados
    if not (cert_pem and key_pem) and not p12_path:
        raise ValueError(
            "❌ No hay certificados configurados para mTLS.\n\n"
            "   Configura una de estas opciones:\n"
            "   1. SIFEN_CERT_PEM y SIFEN_KEY_PEM (archivos .pem)\n"
            "   2. SIFEN_P12_PATH y SIFEN_P12_PASSWORD (archivo .p12)\n\n"
            "   Ejemplo en .env:\n"
            "   SIFEN_CERT_PEM=/ruta/a/cert.pem\n"
            "   SIFEN_KEY_PEM=/ruta/a/key.pem\n"
            "   SIFEN_CA_BUNDLE=/ruta/a/ca-bundle.pem\n\n"
            "   O para P12:\n"
            "   SIFEN_P12_PATH=/ruta/a/cert.p12\n"
            "   SIFEN_P12_PASSWORD=tu_password\n"
        )
    
    # Configurar certificados
    if cert_pem and key_pem:
        # Verificar que existen
        if not Path(cert_pem).exists():
            raise FileNotFoundError(f"Certificado PEM no encontrado: {cert_pem}")
        if not Path(key_pem).exists():
            raise FileNotFoundError(f"Clave PEM no encontrada: {key_pem}")
        
        session.cert = (cert_pem, key_pem)
    elif p12_path:
        if not Path(p12_path).exists():
            raise FileNotFoundError(f"Certificado P12 no encontrado: {p12_path}")
        
        # Para P12, necesitamos convertirlo a PEM temporalmente
        # Por ahora, requerimos que el usuario lo convierta manualmente
        raise NotImplementedError(
            "❌ Soporte para P12 no implementado aún.\n\n"
            "   Convierte tu P12 a PEM/KEY:\n"
            "   openssl pkcs12 -in cert.p12 -out cert.pem -clcerts -nokeys -password pass:TU_PASSWORD\n"
            "   openssl pkcs12 -in cert.p12 -out key.pem -nocerts -nodes -password pass:TU_PASSWORD\n\n"
            "   Luego usa SIFEN_CERT_PEM y SIFEN_KEY_PEM"
        )
    
    # Configurar verificación CA
    if ca_bundle:
        if not Path(ca_bundle).exists():
            raise FileNotFoundError(f"CA bundle no encontrado: {ca_bundle}")
        session.verify = ca_bundle
    else:
        session.verify = True  # Verificar certificados SSL por defecto
    
    return session


def get_wsdl_url(env: str) -> str:
    """
    Obtiene la URL del WSDL según el ambiente
    
    Args:
        env: Ambiente ('test' o 'prod')
        
    Returns:
        URL del WSDL
    """
    if env == "test":
        return os.getenv(
            "SIFEN_WSDL_RECEPCION_TEST",
            "https://sifen-test.set.gov.py/de/ws/recepcion/DERecepcion.wsdl"
        )
    elif env == "prod":
        return os.getenv(
            "SIFEN_WSDL_RECEPCION_PROD",
            "https://sifen.set.gov.py/de/ws/recepcion/DERecepcion.wsdl"
        )
    else:
        raise ValueError(f"Ambiente inválido: {env}. Debe ser 'test' o 'prod'")


def send_sirecepde(xml_path: Path,
                   env: str = "test",
                   cert_pem: Optional[str] = None,
                   key_pem: Optional[str] = None,
                   p12_path: Optional[str] = None,
                   p12_password: Optional[str] = None,
                   ca_bundle: Optional[str] = None,
                   artifacts_dir: Optional[Path] = None) -> dict:
    """
    Envía un XML siRecepDE al servicio SOAP de Recepción de SIFEN
    
    Args:
        xml_path: Path al archivo XML siRecepDE
        env: Ambiente ('test' o 'prod')
        cert_pem: Path al certificado PEM (opcional)
        key_pem: Path a la clave PEM (opcional)
        p12_path: Path al certificado P12 (opcional)
        p12_password: Contraseña del P12 (opcional)
        ca_bundle: Path al bundle CA (opcional)
        artifacts_dir: Directorio para guardar respuestas (opcional)
        
    Returns:
        Diccionario con resultado del envío
    """
    # Leer XML
    print(f"📄 Cargando XML: {xml_path}")
    xml_content = xml_path.read_text(encoding="utf-8")
    print(f"   Tamaño: {len(xml_content)} bytes\n")
    
    # Configurar mTLS
    try:
        session = setup_mtls_session(
            cert_pem=cert_pem,
            key_pem=key_pem,
            p12_path=p12_path,
            p12_password=p12_password,
            ca_bundle=ca_bundle
        )
    except (ValueError, FileNotFoundError, NotImplementedError) as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }
    
    # Obtener WSDL URL
    wsdl_url = get_wsdl_url(env)
    print(f"🔗 Conectando a WSDL: {wsdl_url}")
    print(f"   Ambiente: {env}\n")
    
    # Crear transporte con sesión mTLS
    transport = Transport(session=session, timeout=30)
    
    # Crear cliente SOAP
    settings = Settings(strict=False, xml_huge_tree=True)
    try:
        client = Client(wsdl_url, transport=transport, settings=settings)
    except Exception as e:
        return {
            "success": False,
            "error": f"Error al cargar WSDL: {str(e)}",
            "error_type": type(e).__name__,
            "wsdl_url": wsdl_url
        }
    
    # Mostrar operaciones disponibles
    print("📋 Operaciones disponibles en el servicio:")
    all_ops = []
    ops_by_name = {}
    for service in client.wsdl.services.values():
        for port in service.ports.values():
            print(f"   Servicio: {service.name}")
            print(f"   Puerto: {port.name}")
            for op_name, operation in port.binding._operations.items():
                all_ops.append(op_name)
                ops_by_name[op_name] = operation
                print(f"      - {op_name}")
                # Mostrar firma si es informativa
                try:
                    if hasattr(operation, 'input') and operation.input:
                        input_type = operation.input.signature()
                        print(f"        Entrada: {input_type}")
                except:
                    pass
                try:
                    if hasattr(operation, 'output') and operation.output:
                        output_type = operation.output.signature()
                        print(f"        Salida: {output_type}")
                except:
                    pass
    print()
    
    # Detectar operación correcta
    # Generalmente será algo como "recibirDE" o "recepcionDE" o "enviarDE"
    # Buscar operaciones que tengan "DE" o "recepcion" en el nombre
    target_operation = None
    operation_name = None
    
    for op_name, operation in ops_by_name.items():
        op_lower = op_name.lower()
        if any(keyword in op_lower for keyword in ['de', 'recepcion', 'enviar', 'recibir', 'lote']):
            target_operation = operation
            operation_name = op_name
            print(f"✅ Operación detectada: {op_name}")
            break
    
    if not target_operation:
        # Si no encontramos automáticamente
        if len(all_ops) == 1:
            # Solo hay una, usar esa
            operation_name = all_ops[0]
            target_operation = ops_by_name[operation_name]
            print(f"✅ Usando única operación disponible: {operation_name}")
        elif len(all_ops) == 0:
            return {
                "success": False,
                "error": "No se encontraron operaciones en el WSDL",
                "wsdl_url": wsdl_url
            }
        else:
            return {
                "success": False,
                "error": "Múltiples operaciones encontradas. No se puede determinar automáticamente cuál usar.",
                "available_operations": all_ops,
                "wsdl_url": wsdl_url,
                "note": "Revisa el WSDL para identificar la operación correcta para enviar siRecepDE"
            }
    
    # Leer el tipo de entrada esperado
    input_sig = target_operation.input.signature() if hasattr(target_operation.input, 'signature') else None
    print(f"📤 Enviando XML usando operación: {operation_name}")
    if input_sig:
        print(f"   Firma de entrada: {input_sig}")
    print()
    
    # Intentar enviar
    try:
        # El XML puede necesitar ser Base64 o string directo
        # Intentaremos ambas formas si es necesario
        # Primero, intentar como string directo
        try:
            response = client.service[operation_name](xml_content)
        except Exception as e1:
            # Si falla, intentar como Base64
            try:
                xml_base64 = base64.b64encode(xml_content.encode('utf-8')).decode('utf-8')
                response = client.service[operation_name](xml_base64)
            except Exception as e2:
                # Ambos fallaron
                return {
                    "success": False,
                    "error": f"Error al enviar XML: {str(e1)}",
                    "error_trying_base64": str(e2),
                    "error_type": type(e1).__name__,
                    "operation": operation_name
                }
        
        # Convertir respuesta a diccionario serializable
        response_dict = {}
        if hasattr(response, '__dict__'):
            response_dict = {k: str(v) for k, v in response.__dict__.items()}
        elif isinstance(response, (str, int, float, bool)):
            response_dict = {"value": response}
        else:
            response_dict = {"response": str(response)}
        
        # Guardar respuesta
        if artifacts_dir:
            artifacts_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            response_file = artifacts_dir / f"response_{operation_name}_{timestamp}.json"
            response_file.write_text(json.dumps(response_dict, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"💾 Respuesta guardada en: {response_file}\n")
        
        return {
            "success": True,
            "operation": operation_name,
            "response": response_dict,
            "response_file": str(response_file) if artifacts_dir else None
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "operation": operation_name
        }


def main():
    parser = argparse.ArgumentParser(
        description="Envía XML siRecepDE al servicio SOAP de Recepción de SIFEN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Enviar archivo específico a test
  python -m tools.send_sirecepde --env test --xml artifacts/sirecepde_20251226_233653.xml
  
  # Enviar el más reciente a test
  python -m tools.send_sirecepde --env test --xml latest
  
  # Enviar a producción
  python -m tools.send_sirecepde --env prod --xml latest

Configuración de certificados (variables de entorno):
  SIFEN_CERT_PEM      Path al certificado PEM
  SIFEN_KEY_PEM       Path a la clave privada PEM
  SIFEN_P12_PATH      Path al certificado P12 (no soportado aún)
  SIFEN_P12_PASSWORD  Contraseña del P12
  SIFEN_CA_BUNDLE     Path al bundle CA (opcional)
        """
    )
    
    parser.add_argument(
        "--env",
        choices=["test", "prod"],
        default="test",
        help="Ambiente SIFEN (default: test)"
    )
    
    parser.add_argument(
        "--xml",
        required=True,
        help="Path al archivo XML siRecepDE o 'latest' para usar el más reciente"
    )
    
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Directorio para guardar respuestas (default: artifacts/)"
    )
    
    args = parser.parse_args()
    
    # Resolver artifacts dir
    if args.artifacts_dir is None:
        artifacts_dir = Path(__file__).parent.parent / "artifacts"
    else:
        artifacts_dir = args.artifacts_dir
    
    # Resolver XML path
    try:
        xml_path = resolve_xml_path(args.xml, artifacts_dir)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1
    
    # Cargar configuración de certificados
    cert_pem, key_pem, p12_path, p12_password, ca_bundle = load_certificate_config()
    
    # Enviar
    result = send_sirecepde(
        xml_path=xml_path,
        env=args.env,
        cert_pem=cert_pem,
        key_pem=key_pem,
        p12_path=p12_path,
        p12_password=p12_password,
        ca_bundle=ca_bundle,
        artifacts_dir=artifacts_dir
    )
    
    # Mostrar resultado
    if result["success"]:
        print("✅ Envío exitoso!")
        print(f"   Operación: {result['operation']}")
        if result.get("response_file"):
            print(f"   Respuesta guardada en: {result['response_file']}")
        return 0
    else:
        print("❌ Error en el envío:")
        print(f"   {result['error']}")
        if result.get("error_type"):
            print(f"   Tipo: {result['error_type']}")
        if result.get("available_operations"):
            print("\n   Operaciones disponibles:")
            for op in result["available_operations"]:
                print(f"      - {op}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

