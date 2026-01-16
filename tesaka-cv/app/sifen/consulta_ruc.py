"""
Cliente consultaRUC para SIFEN

Cliente SOAP + mTLS para consultar estado y habilitación de RUCs.
Encapsula la lógica de materialización de certificados P12 a PEM y
provee una interfaz simple para uso desde la web y CLI.
"""
import os
import sys
import tempfile
import logging
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import getpass

from .config import SifenConfig, get_sifen_config
from .ruc import normalize_truc, RucFormatError
from .evidence import write_evidence

# Importar cliente SOAP existente
from app.sifen_client.soap_client import SoapClient
from app.sifen_client.config import SifenConfig as LegacySifenConfig, get_sifen_config as get_legacy_sifen_config
from app.sifen_client.exceptions import SifenClientError
from app.sifen_client.pkcs12_utils import p12_to_temp_pem_files, cleanup_pem_files, PKCS12Error

logger = logging.getLogger(__name__)


class ConsultaRucError(Exception):
    """Error durante consulta RUC"""
    pass


def materialize_cert_files_from_p12(
    p12_path: str,
    p12_password: Optional[str] = None,
    is_cli: bool = False
) -> Tuple[str, str, tempfile.TemporaryDirectory]:
    """
    Materializa certificados PEM desde P12 para uso con mTLS.
    
    Si p12_password es None:
    - En modo CLI (is_cli=True): pide interactivo usando getpass
    - En modo WEB (is_cli=False): lanza error (no se puede pedir interactivo en web)
    
    Args:
        p12_path: Ruta al archivo P12
        p12_password: Password del P12 (opcional)
        is_cli: Si True, permite pedir password interactivo si falta
        
    Returns:
        Tupla (cert_pem_path, key_pem_path, tempdir) donde tempdir debe usarse como context manager
        para cleanup automático
        
    Raises:
        ConsultaRucError: Si falta password en modo web, o si falla la conversión
    """
    # Si falta password
    if not p12_password:
        if is_cli:
            # Modo CLI: pedir interactivo
            try:
                p12_password = getpass.getpass("Ingrese password del certificado P12: ")
            except (KeyboardInterrupt, EOFError):
                raise ConsultaRucError("Password del certificado P12 requerido")
        else:
            # Modo WEB: error claro
            raise ConsultaRucError(
                "Falta password del certificado P12 (SIFEN_P12_PASS). "
                "Configure SIFEN_P12_PASS en .env o use modo CLI para entrada interactiva."
            )
    
    # Validar que el archivo existe
    if not os.path.exists(p12_path):
        raise ConsultaRucError(f"Certificado P12 no encontrado: {p12_path}")
    
    try:
        # Convertir P12 a PEM usando utilidad existente
        # (p12_to_temp_pem_files crea archivos en /tmp con permisos 600)
        cert_pem_path, key_pem_path = p12_to_temp_pem_files(
            p12_path=p12_path,
            p12_password=p12_password
        )
        
        # Retornar paths y un objeto para cleanup
        class PEMCleanup:
            def __init__(self, cert_path: str, key_path: str):
                self.cert_path = cert_path
                self.key_path = key_path
            def cleanup(self):
                cleanup_pem_files(self.cert_path, self.key_path)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.cleanup()
        
        cleanup_obj = PEMCleanup(cert_pem_path, key_pem_path)
        return (cert_pem_path, key_pem_path, cleanup_obj)
        
    except PKCS12Error as e:
        raise ConsultaRucError(f"Error al convertir certificado P12 a PEM: {e}") from e
    except Exception as e:
        raise ConsultaRucError(f"Error inesperado al materializar certificados: {e}") from e


def consulta_ruc_client(
    ruc: str,
    config: Optional[SifenConfig] = None,
    p12_password: Optional[str] = None,
    is_cli: bool = False,
    dump_http: bool = False
) -> Dict[str, Any]:
    """
    Ejecuta consultaRUC contra SIFEN.
    
    Args:
        ruc: RUC a consultar (puede venir con guión, ej: "4554737-8")
        config: Configuración SIFEN (si None, se crea desde env vars)
        p12_password: Password del P12 (opcional, se pide interactivo en CLI si falta)
        is_cli: Si True, permite entrada interactiva para password
        dump_http: Si True, incluye headers y XML enviado/recibido en la respuesta
        
    Returns:
        Dict con:
        - http_code: Código HTTP (int)
        - dCodRes: Código de respuesta SIFEN (str, ej: "0502", "0500")
        - dMsgRes: Mensaje de respuesta SIFEN (str)
        - normalized: RUC normalizado usado (str)
        - raw_xml: XML de respuesta completo (str, opcional)
        - xContRUC: Contenido del RUC encontrado (dict, opcional, solo si dCodRes=0502)
        
    Raises:
        ConsultaRucError: Si falla la normalización, conversión de certificados, o consulta
    """
    # Normalizar RUC
    try:
        ruc_normalized = normalize_truc(ruc)
    except RucFormatError as e:
        raise ConsultaRucError(f"Formato de RUC inválido: {e}") from e
    
    # Obtener configuración si no se proporciona
    if config is None:
        try:
            config = get_sifen_config()
        except Exception as e:
            raise ConsultaRucError(f"Error al cargar configuración SIFEN: {e}") from e
    
    # Obtener password si no se proporciona
    if not p12_password:
        p12_password = config.p12_password
    
    # Materializar certificados PEM
    cert_pem_path = None
    key_pem_path = None
    tempdir = None
    
    try:
        cert_pem_path, key_pem_path, tempdir = materialize_cert_files_from_p12(
            p12_path=config.p12_path,
            p12_password=p12_password,
            is_cli=is_cli
        )
        
        # Crear configuración legacy para SoapClient
        # (necesitamos adaptar nuestra nueva config a la legacy)
        legacy_config = LegacySifenConfig(env=config.env)
        legacy_config.cert_pem_path = cert_pem_path
        legacy_config.key_pem_path = key_pem_path
        
        # Crear cliente SOAP y ejecutar consulta
        request_xml_sent = None
        response_xml_received = None
        
        with SoapClient(legacy_config) as client:
            # Usar consulta_ruc_raw del cliente existente
            result = client.consulta_ruc_raw(
                ruc=ruc_normalized,
                dump_http=dump_http or True  # Siempre capturar para evidence
            )
            
            # Capturar XMLs para evidence
            if dump_http or True:
                request_xml_sent = result.get("sent_xml")
                response_xml_received = result.get("raw_xml")
        
        # Formatear respuesta
        response = {
            "http_code": result.get("http_status"),
            "dCodRes": result.get("dCodRes"),
            "dMsgRes": result.get("dMsgRes"),
            "normalized": ruc_normalized,
        }
        
        if dump_http:
            response["raw_xml"] = result.get("raw_xml")
            response["sent_xml"] = result.get("sent_xml")
            response["sent_headers"] = result.get("sent_headers")
        
        # Agregar contenido del RUC si está disponible
        if "xContRUC" in result:
            response["xContRUC"] = result["xContRUC"]
        
        # Guardar evidence
        try:
            meta = {
                "http_code": response["http_code"],
                "dCodRes": response["dCodRes"],
                "dMsgRes": response["dMsgRes"],
                "normalized_ruc": ruc_normalized,
                "endpoint": config.consulta_ruc_post_url,
                "sifen_env": config.env,
            }
            write_evidence(
                kind="consulta_ruc",
                request_xml=request_xml_sent,
                response_xml=response_xml_received,
                meta_dict=meta
            )
        except Exception as e:
            logger.warning(f"Error al guardar evidence de consulta_ruc: {e}")
        
        return response
        
    except SifenClientError as e:
        # Extraer información del error si tiene result
        error_msg = str(e)
        if hasattr(e, "result") and e.result:
            error_msg += f" (dCodRes: {e.result.get('dCodRes', 'N/A')}, dMsgRes: {e.result.get('dMsgRes', 'N/A')})"
        raise ConsultaRucError(f"Error en consultaRUC: {error_msg}") from e
    except ConsultaRucError:
        raise
    except Exception as e:
        raise ConsultaRucError(f"Error inesperado en consultaRUC: {e}") from e
    finally:
        # Limpiar archivos PEM temporales
        if tempdir:
            try:
                if hasattr(tempdir, 'cleanup'):
                    tempdir.cleanup()
            except Exception as e:
                logger.warning(f"Error al limpiar archivos PEM temporales: {e}")
