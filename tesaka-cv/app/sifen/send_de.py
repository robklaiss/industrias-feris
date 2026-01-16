"""
Cliente para envío de Documento Electrónico (DE) a SIFEN

Encapsula la lógica de generación, firma y envío de DE a SIFEN.
REUTILIZA módulos existentes del repo:
- tools.build_de.build_de_xml() para generar XML DE crudo
- app.sifen_client.xmlsec_signer.sign_de_with_p12() para firmar rDE
- tools.build_sirecepde.build_sirecepde_xml() para wrappear en siRecepDE
- app.sifen_client.soap_client.SoapClient.recepcion_de() para enviar

Maneja materialización de certificados P12→PEM para mTLS.
"""
import os
import logging
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime
import random

from .config import SifenConfig, get_sifen_config
from .consulta_ruc import materialize_cert_files_from_p12
from .evidence import write_evidence

# Importar módulos existentes del repo (funciones exactas)
from tools.build_de import build_de_xml
from app.sifen_client.xmlsec_signer import sign_de_with_p12
from tools.build_sirecepde import build_sirecepde_xml, strip_xml_declaration
from app.sifen_client.soap_client import SoapClient
from app.sifen_client.config import SifenConfig as LegacySifenConfig
from app.sifen_client.exceptions import SifenClientError
from lxml import etree

logger = logging.getLogger(__name__)

# Constantes de namespace SIFEN
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


class SendDeError(Exception):
    """Error durante envío de DE"""
    pass


def _truncate_string(s: str, max_bytes: int = 100 * 1024) -> str:
    """
    Trunca un string a un máximo de bytes (para no guardar requests/responses muy grandes).
    
    Args:
        s: String a truncar
        max_bytes: Máximo de bytes (default: 100KB)
        
    Returns:
        String truncado (si es necesario) con indicador
    """
    if not s:
        return s
    
    encoded = s.encode('utf-8')
    if len(encoded) <= max_bytes:
        return s
    
    # Truncar y agregar indicador
    truncated = encoded[:max_bytes].decode('utf-8', errors='ignore')
    return f"{truncated}... [TRUNCATED {len(encoded)} bytes → {max_bytes} bytes]"


def send_de_client(
    invoice_data: Dict[str, Any],
    config: Optional[SifenConfig] = None,
    p12_password: Optional[str] = None,
    is_cli: bool = False,
    dump_http: bool = False
) -> Dict[str, Any]:
    """
    Envía un Documento Electrónico a SIFEN.
    
    REUTILIZA módulos existentes del repo:
    - tools.build_de.build_de_xml() para generar XML DE crudo
    - app.sifen_client.xmlsec_signer.sign_de_with_p12() para firmar rDE
    - tools.build_sirecepde.build_sirecepde_xml() para wrappear en siRecepDE
    - app.sifen_client.soap_client.SoapClient.recepcion_de() para enviar
    
    Args:
        invoice_data: Datos de la factura en formato interno del sistema
        config: Configuración SIFEN (si None, se crea desde env vars)
        p12_password: Password del P12 (opcional, se pide interactivo en CLI si falta)
        is_cli: Si True, permite entrada interactiva para password
        dump_http: Si True, incluye request/response truncados en la respuesta
        
    Returns:
        Dict con:
        - ok: bool
        - http_code: int
        - dCodRes: str|None
        - dMsgRes: str|None
        - sifen_env: "test"|"prod"
        - endpoint: str (URL usada)
        - signed_xml_sha256: str (hash del XML firmado enviado)
        - raw_response: str (opcional, truncado a 100KB)
        - raw_request: str (opcional, truncado a 100KB)
        - extra: dict (información adicional)
        
    Raises:
        SendDeError: Si falla generación, firma o envío
    """
    # Obtener configuración si no se proporciona
    if config is None:
        try:
            config = get_sifen_config()
        except Exception as e:
            raise SendDeError(f"Error al cargar configuración SIFEN: {e}") from e
    
    # Obtener password si no se proporciona
    if not p12_password:
        p12_password = config.p12_password
    
    # Materializar certificados PEM para mTLS
    cert_pem_path = None
    key_pem_path = None
    cleanup_obj = None
    
    try:
        cert_pem_path, key_pem_path, cleanup_obj = materialize_cert_files_from_p12(
            p12_path=config.p12_path,
            p12_password=p12_password,
            is_cli=is_cli
        )
        
        # Crear configuración legacy para SoapClient
        legacy_config = LegacySifenConfig(env=config.env)
        legacy_config.cert_pem_path = cert_pem_path
        legacy_config.key_pem_path = key_pem_path
        
        # ===== PASO 1: Generar XML DE crudo =====
        # Usar tools.build_de.build_de_xml() (función exacta del repo)
        # Extraer datos de invoice_data para build_de_xml
        buyer = invoice_data.get("buyer", {})
        transaction = invoice_data.get("transaction", {})
        
        # Normalizar RUC del emisor (obtener de config o invoice_data)
        ruc_emisor = os.getenv("SIFEN_TEST_RUC") or os.getenv("SIFEN_RUC") or "80012345"
        timbrado = transaction.get("numeroTimbrado") or os.getenv("SIFEN_TIMBRADO") or "12345678"
        establecimiento = transaction.get("establecimiento") or "001"
        punto_expedicion = transaction.get("puntoExpedicion") or "001"
        numero_documento = transaction.get("numeroComprobanteVenta") or "0000001"
        tipo_documento = str(transaction.get("tipoComprobante", "1"))
        
        # Fecha y hora
        issue_date = invoice_data.get("issue_date")
        issue_datetime = invoice_data.get("issue_datetime")
        fecha = None
        hora = None
        if issue_date:
            fecha = issue_date  # YYYY-MM-DD
        if issue_datetime:
            # Parsear datetime (formato puede variar)
            if 'T' in issue_datetime:
                fecha, hora_part = issue_datetime.split('T', 1)
                hora = hora_part.split('.')[0]  # Remover microsegundos si existen
            else:
                hora = issue_datetime.split(' ')[1] if ' ' in issue_datetime else None
        
        # CSC
        csc = os.getenv("SIFEN_CSC") or os.getenv("SIFEN_TEST_CSC")
        
        try:
            de_xml_raw = build_de_xml(
                ruc=ruc_emisor,
                timbrado=timbrado,
                establecimiento=establecimiento,
                punto_expedicion=punto_expedicion,
                numero_documento=numero_documento,
                tipo_documento=tipo_documento,
                fecha=fecha,
                hora=hora,
                csc=csc,
                env=config.env
            )
        except Exception as e:
            raise SendDeError(f"Error al generar XML DE con build_de_xml: {e}") from e
        
        # ===== PASO 2: Wrappear DE en rDE =====
        # sign_de_with_p12() espera rDE como root, pero build_de_xml retorna solo DE
        # Necesitamos wrappear DE en rDE antes de firmar
        de_root = etree.fromstring(de_xml_raw.encode('utf-8'))
        
        # Construir rDE wrapper
        rde_el = etree.Element(
            f"{{{SIFEN_NS}}}rDE",
            nsmap={None: SIFEN_NS, "xsi": XSI_NS}
        )
        rde_el.set(f"{{{XSI_NS}}}schemaLocation", 
                   "http://ekuatia.set.gov.py/sifen/xsd/siRecepDE_v150.xsd")
        
        # Agregar dVerFor
        dverfor = etree.SubElement(rde_el, f"{{{SIFEN_NS}}}dVerFor")
        dverfor.text = "150"
        
        # Mover DE dentro de rDE
        rde_el.append(de_root)
        
        # Serializar rDE para firmar
        rde_xml_bytes = etree.tostring(
            rde_el,
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=False
        )
        
        # ===== PASO 3: Firmar rDE =====
        # Usar app.sifen_client.xmlsec_signer.sign_de_with_p12() (función exacta del repo)
        try:
            signed_rde_bytes = sign_de_with_p12(
                rde_xml_bytes,
                cert_path=config.p12_path,
                p12_password=p12_password
            )
            signed_rde_xml = signed_rde_bytes.decode('utf-8')
        except Exception as e:
            raise SendDeError(f"Error al firmar rDE con sign_de_with_p12: {e}") from e
        
        # Calcular hash del XML firmado
        signed_xml_sha256 = hashlib.sha256(signed_rde_xml.encode('utf-8')).hexdigest()
        
        # ===== PASO 4: Wrappear rDE firmado en siRecepDE =====
        # Usar tools.build_sirecepde.build_sirecepde_xml() (función exacta del repo)
        # IMPORTANTE: build_sirecepde_xml acepta sign_p12_path/sign_p12_password pero
        # ya tenemos el DE firmado, así que NO pasamos esos parámetros (solo wrappea)
        # Generar dId único (formato: YYYYMMDDHHMMSS + 1 dígito aleatorio = 15 dígitos)
        d_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(0, 9)}"
        
        # Remover declaración XML del rDE firmado antes de wrappear
        # (build_sirecepde_xml espera contenido sin prolog XML)
        rde_without_declaration = strip_xml_declaration(signed_rde_xml)
        
        # Wrappear en siRecepDE (sin firmar de nuevo, solo wrappear)
        sirecepde_xml = build_sirecepde_xml(
            de_xml_content=rde_without_declaration,
            d_id=d_id,
            sign_p12_path=None,  # Ya está firmado, no firmar de nuevo
            sign_p12_password=None
        )
        
        # ===== PASO 5: Enviar a SIFEN vía SOAP + mTLS =====
        # Usar app.sifen_client.soap_client.SoapClient.recepcion_de() (función exacta del repo)
        try:
            with SoapClient(legacy_config) as client:
                result = client.recepcion_de(sirecepde_xml)
        except SifenClientError as e:
            # Extraer información del error si tiene result
            error_msg = str(e)
            if hasattr(e, "result") and e.result:
                error_msg += f" (dCodRes: {e.result.get('dCodRes', 'N/A')}, dMsgRes: {e.result.get('dMsgRes', 'N/A')})"
            raise SendDeError(f"Error en envío SOAP a SIFEN: {error_msg}") from e
        
        # ===== PASO 6: Formatear respuesta =====
        # Recepción DE individual retorna códigos 0200 (éxito) o errores 0160, etc.
        # Recepción Lote retorna 0300 (lote recibido) o 0301 (no encolado)
        d_cod_res = result.get("codigo_respuesta") or result.get("dCodRes")
        response = {
            "ok": result.get("ok", False) or (d_cod_res in ("0200", "0300", "0301", "0302") if d_cod_res else False),
            "http_code": result.get("codigo_estado") or result.get("http_status"),
            "dCodRes": d_cod_res,
            "dMsgRes": result.get("mensaje") or result.get("dMsgRes"),
            "sifen_env": config.env,
            "endpoint": legacy_config.get_soap_service_url("recibe"),
            "signed_xml_sha256": signed_xml_sha256,
            "extra": {
                "cdc": result.get("cdc"),
                "estado": result.get("estado"),
                "dProtConsLote": result.get("d_prot_cons_lote"),  # Solo para lotes
            }
        }
        
        if dump_http:
            # Extraer raw_xml de result si existe
            raw_xml = result.get("raw_xml") or result.get("raw_response")
            if raw_xml:
                response["raw_response"] = _truncate_string(raw_xml)
            response["raw_request"] = _truncate_string(sirecepde_xml)
        
        # Guardar evidence
        try:
            meta = {
                "http_code": response["http_code"],
                "dCodRes": response["dCodRes"],
                "dMsgRes": response["dMsgRes"],
                "signed_xml_sha256": signed_xml_sha256,
                "endpoint": response["endpoint"],
                "sifen_env": config.env,
                "ok": response["ok"],
            }
            if "cdc" in response.get("extra", {}):
                meta["dCDC"] = response["extra"]["cdc"]
            
            # Capturar XMLs para evidence
            response_xml_for_evidence = result.get("raw_xml") or result.get("raw_response")
            write_evidence(
                kind="send_de",
                request_xml=sirecepde_xml,
                response_xml=response_xml_for_evidence,
                meta_dict=meta
            )
        except Exception as e:
            logger.warning(f"Error al guardar evidence de send_de: {e}")
        
        return response
        
    except SendDeError:
        raise
    except Exception as e:
        raise SendDeError(f"Error inesperado en envío de DE: {e}") from e
    finally:
        # Limpiar archivos PEM temporales
        if cleanup_obj:
            try:
                if hasattr(cleanup_obj, 'cleanup'):
                    cleanup_obj.cleanup()
            except Exception as e:
                logger.warning(f"Error al limpiar archivos PEM temporales: {e}")
