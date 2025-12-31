#!/usr/bin/env python3
"""
CLI para enviar XML siRecepLoteDE (rEnvioLote) al servicio SOAP de Recepción Lote DE (async) de SIFEN

Este script usa SoapClient del módulo sifen_client para enviar documentos
electrónicos a SIFEN usando mTLS con certificados P12/PFX.

El script construye un lote (rLoteDE) con 1 rDE, lo comprime en ZIP, lo codifica en Base64
y lo envía dentro de un rEnvioLote al servicio async recibe_lote.

Uso:
    python -m tools.send_sirecepde --env test --xml artifacts/sirecepde_20251226_233653.xml
    python -m tools.send_sirecepde --env test --xml latest
    SIFEN_DEBUG_SOAP=1 SIFEN_SOAP_COMPAT=roshka python -m tools.send_sirecepde --env test --xml artifacts/signed.xml
"""
import sys
import argparse
import os
from pathlib import Path
from typing import Optional
from datetime import datetime
from io import BytesIO
import base64
import zipfile

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Constantes de namespace SIFEN
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"

try:
    from lxml import etree
except ImportError:
    print("❌ Error: lxml no está instalado")
    print("   Instale con: pip install lxml")
    sys.exit(1)

try:
    from app.sifen_client import SoapClient, get_sifen_config, SifenClientError, SifenResponseError, SifenSizeLimitError
except ImportError as e:
    print("❌ Error: No se pudo importar módulos SIFEN")
    print(f"   Error: {e}")
    print("   Asegúrate de que las dependencias estén instaladas:")
    print("   pip install zeep lxml cryptography signxml python-dotenv")
    sys.exit(1)


def _extract_metadata_from_xml(xml_content: str) -> dict:
    """
    Extrae metadatos del XML DE para debug.
    
    Returns:
        Dict con: dId, CDC, dRucEm, dDVEmi, dNumTim
    """
    metadata = {
        "dId": None,
        "CDC": None,
        "dRucEm": None,
        "dDVEmi": None,
        "dNumTim": None
    }
    
    try:
        root = etree.fromstring(xml_content.encode("utf-8"))
        
        # Buscar dId en rEnviDe o rEnvioLote
        d_id_elem = root.find(f".//{{{SIFEN_NS}}}dId")
        if d_id_elem is not None and d_id_elem.text:
            metadata["dId"] = d_id_elem.text
        
        # Buscar CDC en atributo Id del DE
        de_elem = root.find(f".//{{{SIFEN_NS}}}DE")
        if de_elem is not None:
            metadata["CDC"] = de_elem.get("Id")
            
            # Buscar dRucEm y dDVEmi dentro de gEmis
            g_emis = de_elem.find(f".//{{{SIFEN_NS}}}gEmis")
            if g_emis is not None:
                d_ruc_elem = g_emis.find(f"{{{SIFEN_NS}}}dRucEm")
                if d_ruc_elem is not None and d_ruc_elem.text:
                    metadata["dRucEm"] = d_ruc_elem.text
                
                d_dv_elem = g_emis.find(f"{{{SIFEN_NS}}}dDVEmi")
                if d_dv_elem is not None and d_dv_elem.text:
                    metadata["dDVEmi"] = d_dv_elem.text
            
            # Buscar dNumTim dentro de gTimb
            g_timb = de_elem.find(f".//{{{SIFEN_NS}}}gTimb")
            if g_timb is not None:
                d_num_tim_elem = g_timb.find(f"{{{SIFEN_NS}}}dNumTim")
                if d_num_tim_elem is not None and d_num_tim_elem.text:
                    metadata["dNumTim"] = d_num_tim_elem.text
    
    except Exception as e:
        # Si falla la extracción, continuar con valores None
        pass
    
    return metadata


def _save_1264_debug(
    artifacts_dir: Path,
    payload_xml: str,
    zip_bytes: bytes,
    zip_base64: str,
    xml_content: str,
    wsdl_url: str,
    service_key: str,
    client: 'SoapClient'
):
    """
    Guarda archivos de debug cuando se recibe error 1264.
    
    Args:
        artifacts_dir: Directorio donde guardar archivos
        payload_xml: XML rEnvioLote completo
        zip_bytes: ZIP binario
        zip_base64: Base64 del ZIP
        xml_content: XML original (DE o siRecepDE)
        wsdl_url: URL del WSDL usado
        service_key: Clave del servicio (ej: "recibe_lote")
        client: Instancia de SoapClient (para acceder a history/debug files)
    """
    artifacts_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"debug_1264_{timestamp}"
    
    # 1. Guardar lote_payload.xml (rEnvioLote sin SOAP envelope)
    lote_payload_file = artifacts_dir / f"{prefix}_lote_payload.xml"
    lote_payload_file.write_text(payload_xml, encoding="utf-8")
    print(f"   ✓ {lote_payload_file.name}")
    
    # 2. Guardar lote.zip (binario)
    lote_zip_file = artifacts_dir / f"{prefix}_lote.zip"
    lote_zip_file.write_bytes(zip_bytes)
    print(f"   ✓ {lote_zip_file.name}")
    
    # 3. Guardar lote.zip.b64.txt (base64 string)
    lote_b64_file = artifacts_dir / f"{prefix}_lote.zip.b64.txt"
    lote_b64_file.write_text(zip_base64, encoding="utf-8")
    print(f"   ✓ {lote_b64_file.name}")
    
    # 4. Intentar leer SOAP sent/received desde artifacts (si SIFEN_DEBUG_SOAP estaba activo)
    # o desde history plugin del cliente
    soap_sent_file = artifacts_dir / f"{prefix}_soap_last_sent.xml"
    soap_received_file = artifacts_dir / f"{prefix}_soap_last_received.xml"
    
    # Intentar leer desde artifacts/soap_last_sent.xml (si existe)
    existing_sent = artifacts_dir / "soap_last_sent.xml"
    if existing_sent.exists():
        soap_sent_file.write_bytes(existing_sent.read_bytes())
        print(f"   ✓ {soap_sent_file.name} (copiado desde soap_last_sent.xml)")
    else:
        # Intentar desde history plugin si está disponible
        try:
            if hasattr(client, "_history_plugins") and service_key in client._history_plugins:
                history = client._history_plugins[service_key]
                if hasattr(history, "last_sent") and history.last_sent:
                    soap_sent_file.write_bytes(history.last_sent["envelope"].encode("utf-8"))
                    print(f"   ✓ {soap_sent_file.name} (desde history plugin)")
        except Exception as e:
            print(f"   ⚠️  No se pudo obtener SOAP enviado: {e}")
    
    existing_received = artifacts_dir / "soap_last_received.xml"
    if existing_received.exists():
        soap_received_file.write_bytes(existing_received.read_bytes())
        print(f"   ✓ {soap_received_file.name} (copiado desde soap_last_received.xml)")
    else:
        try:
            if hasattr(client, "_history_plugins") and service_key in client._history_plugins:
                history = client._history_plugins[service_key]
                if hasattr(history, "last_received") and history.last_received:
                    soap_received_file.write_bytes(history.last_received["envelope"].encode("utf-8"))
                    print(f"   ✓ {soap_received_file.name} (desde history plugin)")
        except Exception as e:
            print(f"   ⚠️  No se pudo obtener SOAP recibido: {e}")
    
    # 5. Extraer metadatos del XML
    metadata = _extract_metadata_from_xml(xml_content)
    
    # 6. Guardar meta.json
    import json
    meta_data = {
        "dId": metadata.get("dId"),
        "CDC": metadata.get("CDC"),
        "dRucEm": metadata.get("dRucEm"),
        "dDVEmi": metadata.get("dDVEmi"),
        "dNumTim": metadata.get("dNumTim"),
        "zip_size_bytes": len(zip_bytes),
        "zip_base64_length": len(zip_base64),
        "endpoint_url": wsdl_url,
        "service_key": service_key,
        "operation": "siRecepLoteDE",
        "timestamp": timestamp
    }
    
    meta_file = artifacts_dir / f"{prefix}_meta.json"
    meta_file.write_text(
        json.dumps(meta_data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8"
    )
    print(f"   ✓ {meta_file.name}")
    
    print(f"\n💾 Archivos de debug guardados con prefijo: {prefix}")


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


def _local(tag: str) -> str:
    """Extrae el nombre local de un tag (sin namespace)."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find_by_localname(root: etree._Element, name: str) -> Optional[etree._Element]:
    """Busca un elemento por nombre local (ignorando namespace) en todo el árbol."""
    for el in root.iter():
        if _local(el.tag) == name:
            return el
    return None


def extract_rde_element(xml_bytes: bytes) -> bytes:
    """
    Acepta:
      - un XML cuya raíz ya sea rDE, o
      - un XML wrapper (siRecepDE) que contenga un rDE adentro.
    Devuelve el XML del elemento rDE (bytes).
    """
    root = etree.fromstring(xml_bytes)

    # Caso 1: root es rDE (verificar por nombre local, ignorando namespace)
    if _local(root.tag) == "rDE":
        return etree.tostring(root, xml_declaration=False, encoding="utf-8")

    # Caso 2: buscar el primer rDE anidado (por nombre local, ignorando namespace)
    rde_el = _find_by_localname(root, "rDE")

    if rde_el is None:
        raise ValueError("No se encontró <rDE> en el XML (ni como raíz ni anidado).")

    return etree.tostring(rde_el, xml_declaration=False, encoding="utf-8")


def build_lote_base64_from_single_xml(xml_bytes: bytes) -> str:
    """
    Crea:
      - rLoteDE con 1 rDE
      - lo comprime en ZIP
      - lo devuelve en Base64 (string) para poner en <xDE>
    """
    rde_bytes = extract_rde_element(xml_bytes)

    lote = etree.Element(etree.QName(SIFEN_NS, "rLoteDE"), nsmap={None: SIFEN_NS})
    lote.append(etree.fromstring(rde_bytes))
    lote_xml_bytes = etree.tostring(lote, xml_declaration=True, encoding="utf-8")

    mem = BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("lote.xml", lote_xml_bytes)
    zip_bytes = mem.getvalue()

    return base64.b64encode(zip_bytes).decode("ascii")


def build_r_envio_lote_xml(did: int, xml_bytes: bytes, zip_base64: Optional[str] = None) -> str:
    """
    Construye el XML rEnvioLote con el lote comprimido en Base64.
    
    Args:
        did: ID del documento
        xml_bytes: XML original (puede ser rDE o siRecepDE)
        zip_base64: Base64 del ZIP (opcional, se calcula si no se proporciona)
        
    Returns:
        XML rEnvioLote como string
    """
    if zip_base64 is None:
        xde_b64 = build_lote_base64_from_single_xml(xml_bytes)
    else:
        xde_b64 = zip_base64

    rEnvioLote = etree.Element(etree.QName(SIFEN_NS, "rEnvioLote"), nsmap={None: SIFEN_NS})
    dId = etree.SubElement(rEnvioLote, etree.QName(SIFEN_NS, "dId"))
    dId.text = str(did)
    xDE = etree.SubElement(rEnvioLote, etree.QName(SIFEN_NS, "xDE"))
    xDE.text = xde_b64

    return etree.tostring(rEnvioLote, xml_declaration=True, encoding="utf-8").decode("utf-8")


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


def send_sirecepde(xml_path: Path, env: str = "test", artifacts_dir: Optional[Path] = None) -> dict:
    """
    Envía un XML siRecepDE al servicio SOAP de Recepción de SIFEN
    
    Args:
        xml_path: Path al archivo XML siRecepDE
        env: Ambiente ('test' o 'prod')
        artifacts_dir: Directorio para guardar respuestas (opcional)
        
    Returns:
        Diccionario con resultado del envío
    """
    # Leer XML
    print(f"📄 Cargando XML: {xml_path}")
    try:
        xml_content = xml_path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "success": False,
            "error": f"Error al leer archivo XML: {str(e)}",
            "error_type": type(e).__name__
        }
    
    # Firmar XML si hay certificado de firma disponible
    sign_p12_path = os.getenv("SIFEN_SIGN_P12_PATH")
    sign_p12_password = os.getenv("SIFEN_SIGN_P12_PASSWORD")

    if sign_p12_path and sign_p12_password:
        try:
            from app.sifen_client.xmlsec_signer import sign_de_with_p12
            print(f"🔐 Firmando XML con certificado: {Path(sign_p12_path).name}")
            xml_content = sign_de_with_p12(xml_content.encode('utf-8'), sign_p12_path, sign_p12_password).decode('utf-8')
            print("✓ XML firmado exitosamente\n")
        except Exception as e:
            return {
                "success": False,
                "error": f"Error al firmar XML: {str(e)}",
                "error_type": type(e).__name__
            }
    elif sign_p12_path or sign_p12_password:
        missing = "SIFEN_SIGN_P12_PASSWORD" if not sign_p12_password else "SIFEN_SIGN_P12_PATH"
        return {
            "success": False,
            "error": f"Falta certificado de firma para XMLDSig: {missing}",
            "error_type": "ConfigurationError"
        }
    
    xml_size = len(xml_content.encode('utf-8'))
    print(f"   Tamaño: {xml_size} bytes ({xml_size / 1024:.2f} KB)\n")
    
    # Validar RUC del emisor antes de enviar (evitar código 1264)
    try:
        from app.sifen_client.ruc_validator import validate_emisor_ruc
        from app.sifen_client.config import get_sifen_config
        
        # Obtener RUC esperado del config si está disponible
        try:
            config = get_sifen_config(env=env)
            expected_ruc = os.getenv("SIFEN_EMISOR_RUC") or getattr(config, 'test_ruc', None)
        except:
            expected_ruc = os.getenv("SIFEN_EMISOR_RUC") or os.getenv("SIFEN_TEST_RUC")
        
        is_valid, error_msg = validate_emisor_ruc(xml_content, expected_ruc=expected_ruc)
        
        if not is_valid:
            print(f"❌ RUC emisor inválido/dummy/no coincide; no se envía a SIFEN:")
            print(f"   {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "error_type": "RUCValidationError",
                "note": "Configure SIFEN_EMISOR_RUC con el RUC real del contribuyente habilitado (formato: RUC-DV, ej: 4554737-8)"
            }
        
        print("✓ RUC del emisor validado (no es dummy)\n")
    except ImportError:
        # Si no se puede importar el validador, continuar sin validación (no crítico)
        print("⚠️  No se pudo importar validador de RUC, continuando sin validación\n")
    except Exception as e:
        # Si falla la validación por otro motivo, continuar (no bloquear)
        print(f"⚠️  Error al validar RUC del emisor: {e}, continuando sin validación\n")
    
    # Validar variables de entorno requeridas
    required_vars = ['SIFEN_CERT_PATH', 'SIFEN_CERT_PASSWORD']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        return {
            "success": False,
            "error": f"Variables de entorno faltantes: {', '.join(missing_vars)}",
            "error_type": "ConfigurationError",
            "note": "Configure estas variables en .env o en el entorno"
        }
    
    # Configurar cliente SIFEN
    try:
        print(f"🔧 Configurando cliente SIFEN (ambiente: {env})")
        config = get_sifen_config(env=env)
        service_key = "recibe_lote"  # Usar servicio de lote (async)
        wsdl_url = config.get_soap_service_url(service_key)
        print(f"   WSDL (recibe_lote): {wsdl_url}")
        print(f"   Operación: siRecepLoteDE\n")
    except Exception as e:
        return {
            "success": False,
            "error": f"Error al configurar cliente SIFEN: {str(e)}",
            "error_type": type(e).__name__
        }
    
    # Construir XML de lote (rEnvioLote) desde el XML original
    try:
        print("📦 Construyendo lote desde XML individual...")
        # Obtener dId del XML original si está disponible, sino usar 1
        try:
            xml_root = etree.fromstring(xml_content.encode("utf-8"))
            d_id_elem = xml_root.find(f".//{{{SIFEN_NS}}}dId")
            if d_id_elem is not None and d_id_elem.text:
                did = int(d_id_elem.text)
            else:
                did = 1
        except:
            did = 1
        
        # Construir el ZIP base64 primero para poder loguear tamaños
        zip_base64 = build_lote_base64_from_single_xml(xml_content.encode("utf-8"))
        zip_bytes = base64.b64decode(zip_base64)
        
        # Construir el payload de lote completo (reutilizando zip_base64)
        payload_xml = build_r_envio_lote_xml(did=did, xml_bytes=xml_content.encode("utf-8"), zip_base64=zip_base64)
        
        print(f"✓ Lote construido:")
        print(f"   dId: {did}")
        print(f"   ZIP bytes: {len(zip_bytes)} ({len(zip_bytes) / 1024:.2f} KB)")
        print(f"   Base64 len: {len(zip_base64)}")
        print(f"   Payload XML total: {len(payload_xml.encode('utf-8'))} bytes ({len(payload_xml.encode('utf-8')) / 1024:.2f} KB)\n")
    except Exception as e:
        return {
            "success": False,
            "error": f"Error al construir lote: {str(e)}",
            "error_type": type(e).__name__
        }
    
    # Enviar usando SoapClient
    try:
        print("📤 Enviando lote a SIFEN (siRecepLoteDE)...\n")
        print(f"   WSDL: {wsdl_url}")
        print(f"   Servicio: {service_key}")
        print(f"   Operación: siRecepLoteDE\n")
        
        with SoapClient(config) as client:
            response = client.recepcion_lote(payload_xml)
            
            # Mostrar resultado
            print("✅ Envío completado")
            print(f"   Estado: {'OK' if response.get('ok') else 'ERROR'}")
            
            codigo_respuesta = response.get('codigo_respuesta')
            if codigo_respuesta:
                print(f"   Código respuesta: {codigo_respuesta}")
            
            if response.get('mensaje'):
                print(f"   Mensaje: {response['mensaje']}")
            
            if response.get('cdc'):
                print(f"   CDC: {response['cdc']}")
            
            if response.get('estado'):
                print(f"   Estado documento: {response['estado']}")
            
            # Extraer y guardar dProtConsLote si está presente
            d_prot_cons_lote = response.get('d_prot_cons_lote')
            if d_prot_cons_lote:
                print(f"   dProtConsLote: {d_prot_cons_lote}")
                
                # Guardar lote en base de datos
                try:
                    sys.path.insert(0, str(Path(__file__).parent.parent))
                    from web.lotes_db import create_lote
                    
                    lote_id = create_lote(
                        env=env,
                        d_prot_cons_lote=d_prot_cons_lote,
                        de_document_id=None  # TODO: relacionar con de_documents si es posible
                    )
                    print(f"   💾 Lote guardado en BD (ID: {lote_id})")
                except Exception as e:
                    print(f"   ⚠️  No se pudo guardar lote en BD: {e}")
            
            # Guardar respuesta si se especificó artifacts_dir
            if artifacts_dir:
                artifacts_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                response_file = artifacts_dir / f"response_recepcion_{timestamp}.json"
                
                import json
                response_file.write_text(
                    json.dumps(response, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8"
                )
                print(f"\n💾 Respuesta guardada en: {response_file}")
            
            # Instrumentación para debug del error 1264
            if codigo_respuesta == "1264" and artifacts_dir:
                print("\n🔍 Error 1264 detectado: Guardando archivos de debug...")
                _save_1264_debug(
                    artifacts_dir=artifacts_dir,
                    payload_xml=payload_xml,
                    zip_bytes=zip_bytes,
                    zip_base64=zip_base64,
                    xml_content=xml_content,
                    wsdl_url=wsdl_url,
                    service_key=service_key,
                    client=client
                )
        
        return {
            "success": response.get('ok', False),
            "response": response,
            "response_file": str(response_file) if artifacts_dir else None
        }
        
    except SifenSizeLimitError as e:
        print(f"❌ Error: El XML excede el límite de tamaño")
        print(f"   {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "error_type": "SifenSizeLimitError",
            "service": e.service,
            "size": e.size,
            "limit": e.limit
        }
    
    except SifenResponseError as e:
        print(f"❌ Error SIFEN en la respuesta")
        print(f"   Código: {e.code}")
        print(f"   Mensaje: {e.message}")
        return {
            "success": False,
            "error": e.message,
            "error_type": "SifenResponseError",
            "code": e.code
        }
    
    except SifenClientError as e:
        print(f"❌ Error del cliente SIFEN")
        print(f"   {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "error_type": "SifenClientError"
        }
    
    except Exception as e:
        print(f"❌ Error inesperado")
        print(f"   {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


def main():
    parser = argparse.ArgumentParser(
        description="Envía XML siRecepLoteDE (rEnvioLote) al servicio SOAP de Recepción Lote DE (async) de SIFEN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Enviar archivo específico a test
  python -m tools.send_sirecepde --env test --xml artifacts/sirecepde_20251226_233653.xml
  
  # Enviar el más reciente a test
  python -m tools.send_sirecepde --env test --xml latest
  
  # Enviar a producción
  python -m tools.send_sirecepde --env prod --xml latest
  
  # Con debug SOAP y compatibilidad Roshka
  SIFEN_DEBUG_SOAP=1 SIFEN_SOAP_COMPAT=roshka python -m tools.send_sirecepde --env test --xml artifacts/signed.xml

Configuración requerida (variables de entorno):
  SIFEN_ENV              Ambiente (test/prod) - opcional, puede usar --env
  SIFEN_CERT_PATH        Path al certificado P12/PFX (requerido)
  SIFEN_CERT_PASSWORD    Contraseña del certificado (requerido)
  SIFEN_USE_MTLS         true/false (default: true)
  SIFEN_CA_BUNDLE_PATH   Path al bundle CA (opcional)
  SIFEN_DEBUG_SOAP       1/true para guardar SOAP enviado/recibido en artifacts/
  SIFEN_SOAP_COMPAT      roshka para modo compatibilidad Roshka
        """
    )
    
    parser.add_argument(
        "--env",
        choices=["test", "prod"],
        default=None,
        help="Ambiente SIFEN (sobrescribe SIFEN_ENV)"
    )
    
    parser.add_argument(
        "--xml",
        required=True,
        help="Path al archivo XML (rDE o siRecepDE) o 'latest' para usar el más reciente"
    )
    
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Directorio para guardar respuestas (default: artifacts/)"
    )
    
    args = parser.parse_args()
    
    # Determinar ambiente
    env = args.env or os.getenv("SIFEN_ENV", "test")
    if env not in ["test", "prod"]:
        print(f"❌ Ambiente inválido: {env}. Debe ser 'test' o 'prod'")
        return 1
    
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
        import traceback
        traceback.print_exc()
        return 1
    
    # Enviar
    result = send_sirecepde(
        xml_path=xml_path,
        env=env,
        artifacts_dir=artifacts_dir
    )
    
    # Retornar código de salida
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    import sys, traceback
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print("❌ EXCEPCIÓN NO MOSTRADA:", repr(e), file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
