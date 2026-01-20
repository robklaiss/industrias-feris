"""
Cliente SOAP 1.2 Document/Literal para SIFEN

Requisitos:
- SOAP 1.2
- Estilo Document/Literal
- mTLS (TLS 1.2) con certificados
- Validación de tamaño antes de enviar
- Manejo de códigos de error SIFEN

Notas importantes:
- El WSDL .../recibe.wsdl en test puede devolver body vacío; se debe usar ?wsdl.
- NO usar elem1 or elem2 con lxml Elements (pueden ser "falsy" si no tienen hijos).
"""

import os
import datetime as _dt
import json
import logging
import time
import ssl
from typing import Dict, Any, Optional, List, TYPE_CHECKING, Tuple
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from dataclasses import dataclass
import re
from io import BytesIO

# Constante para el nombre del archivo XML dentro del ZIP (debe coincidir con send_sirecepde.py)
ZIP_INTERNAL_FILENAME = "lote.xml"

try:
    # Import lxml.etree - el linter puede no reconocerlo, pero funciona correctamente
    import lxml.etree as etree  # noqa: F401
except ImportError:
    etree = None  # type: ignore

if TYPE_CHECKING:
    from lxml.etree import _Element as etree_type  # noqa: F401

try:
    from zeep import Client, Settings
    from zeep.transports import Transport
    from zeep.exceptions import Fault, TransportError
    from zeep.helpers import serialize_object

    ZEEP_AVAILABLE = True
except ImportError:
    ZEEP_AVAILABLE = False
    serialize_object = None
    Client = None
    Settings = None
    Transport = None
    Fault = Exception
    TransportError = Exception

from requests import Session
from requests.adapters import HTTPAdapter
import requests
from urllib3.util.retry import Retry

from .config import (
    SifenConfig,
    get_artifacts_dir,
    get_project_root,
)
from .ruc_format import normalize_sifen_truc, RucFormatError
from .exceptions import (
    SifenClientError,
    SifenSizeLimitError,
)

try:
    from .wsdl_introspect import inspect_wsdl, save_wsdl_inspection
except ImportError:
    inspect_wsdl = None  # type: ignore
    save_wsdl_inspection = None  # type: ignore

logger = logging.getLogger(__name__)

# WSDL cache directory
WSDL_CACHE_DIR = get_artifacts_dir("wsdl_cache")

# Constantes de namespace SIFEN
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"
SOAP_NS_11 = "http://schemas.xmlsoap.org/soap/envelope/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SIFEN_SCHEMA_LOCATION = "http://ekuatia.set.gov.py/sifen/xsd/siRecepDE_v150.xsd"

# Límites de tamaño según requisitos SIFEN (en bytes)
SIZE_LIMITS = {
    "siRecepDE": 1000 * 1024,  # 1000 KB
    "siRecepLoteDE": 10000 * 1024,  # 10.000 KB
    "siConsRUC": 1000 * 1024,  # 1000 KB
    "siConsDE": 1000 * 1024,  # 1000 KB (asumido)
    "siConsLoteDE": 10000 * 1024,  # 10.000 KB (asumido)
}

# Códigos de error SIFEN (parciales)
ERROR_CODES = {
    "0200": "Mensaje excede tamaño máximo (siRecepDE)",
    "0270": "Lote excede tamaño máximo (siRecepLoteDE)",
    "0460": "Mensaje excede tamaño máximo (siConsRUC)",
    "0500": "RUC inexistente",
    "0501": "Sin permiso para consultar",
    "0502": "Éxito (RUC encontrado)",
    "0183": "RUC del certificado no activo/válido",
}


def _preferred_envio_root_name() -> str:
    val = os.getenv("SIFEN_ENVIOLOTE_ROOT", "").strip()
    if val not in ("rEnvioLote", "rEnvioLoteDe"):
        return "rEnvioLote"
    return val


def _is_soap_action_disabled() -> bool:
    return os.getenv("SIFEN_DISABLE_SOAPACTION", "0").strip().lower() in ("1", "true", "yes", "y")


def _soapaction_mode(service: str) -> str:
    """
    Devuelve modo SOAPAction por servicio: on|off|auto.
    Default: gate=on, lote=off.
    """
    defaults = {"gate": "on", "lote": "off"}
    env_map = {
        "gate": "SIFEN_SOAPACTION_MODE_GATE",
        "lote": "SIFEN_SOAPACTION_MODE_LOTE",
    }
    key = env_map.get(service, "")
    val = os.getenv(key, "").strip().lower()
    if val not in ("on", "off", "auto"):
        val = defaults.get(service, "auto")
    return val


def _build_soap12_headers(service: str, action_value: str, accept: str = "application/soap+xml, text/xml, */*") -> Dict[str, str]:
    """
    Construye headers para SOAP 1.2 según modo on/off/auto por servicio.
    - on: Content-Type con action= y header SOAPAction
    - off: Content-Type sin action=, sin SOAPAction
    - auto: Content-Type con action=, sin SOAPAction (comportamiento previo)
    """
    mode = _soapaction_mode(service)
    content_type = "application/soap+xml; charset=utf-8"
    if mode in ("on", "auto"):
        content_type += f'; action="{action_value}"'
    headers = {
        "Content-Type": content_type,
        "Accept": accept,
    }
    if mode == "on":
        headers["SOAPAction"] = f'"{action_value}"'
    return headers


def _content_type_action_value(default: str = "http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE") -> str:
    override = os.getenv("SIFEN_CONTENT_TYPE_ACTION", "").strip()
    return override or default


def _body_preview_summary(body_elem: Optional["etree_type"], limit: int = 200) -> str:
    if body_elem is None:
        return "(Body no disponible)"
    raw = etree.tostring(body_elem, encoding="unicode", pretty_print=False)
    redacted = re.sub(r'(<xDE[^>]*>)(.*?)(</xDE>)', r'\1__BASE64_REDACTED__\3', raw, flags=re.DOTALL)
    redacted = " ".join(redacted.split())
    if len(redacted) > limit:
        return redacted[:limit] + "..."
    return redacted


def _local_name(tag: Any) -> str:
    """Extrae el localname de un tag lxml (con o sin namespace)."""
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[1]
    return str(tag)


def _namespace_uri(tag: Any) -> Optional[str]:
    """Retorna el namespace URI de un tag lxml, si existe."""
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[0][1:]
    return None


@dataclass
class _LoteStructureInfo:
    valid: bool
    mode: str
    root_localname: str
    root_namespace: Optional[str]
    direct_rde_total: int
    direct_rde_sifen: int
    xde_total: int
    xde_sifen: int
    nested_rde_total: int
    first_rde: Optional["etree_type"]
    message: Optional[str] = None


def _evaluate_lote_structure(lote_root: "etree_type") -> _LoteStructureInfo:
    """Valida si rLoteDE tiene rDE directos o xDE->rDE (ambos soportados)."""
    localname = _local_name(lote_root.tag)
    ns = _namespace_uri(lote_root.tag)

    direct_rde = [c for c in list(lote_root) if _local_name(c.tag) == "rDE"]
    direct_rde_sifen = [c for c in direct_rde if _namespace_uri(c.tag) == SIFEN_NS]

    xde_children = [c for c in list(lote_root) if _local_name(c.tag) == "xDE"]
    xde_sifen = [c for c in xde_children if _namespace_uri(c.tag) == SIFEN_NS]

    info = _LoteStructureInfo(
        valid=False,
        mode="invalid",
        root_localname=localname,
        root_namespace=ns,
        direct_rde_total=len(direct_rde),
        direct_rde_sifen=len(direct_rde_sifen),
        xde_total=len(xde_children),
        xde_sifen=len(xde_sifen),
        nested_rde_total=0,
        first_rde=None,
    )

    if localname != "rLoteDE":
        info.message = f"lote.xml root debe ser 'rLoteDE', encontrado: {localname}"
        return info

    if ns != SIFEN_NS:
        info.message = f"rLoteDE debe tener namespace {SIFEN_NS}, encontrado: {ns or '(vacío)'}"
        return info

    if direct_rde_sifen:
        info.valid = True
        info.mode = "direct_rde"
        info.nested_rde_total = len(direct_rde_sifen)
        info.first_rde = direct_rde_sifen[0]
        return info

    if direct_rde and not direct_rde_sifen:
        info.message = "Los elementos <rDE> directos deben usar el namespace SIFEN"
        return info

    if not xde_children:
        info.message = "lote.xml debe contener al menos un <rDE> (directo o dentro de <xDE>)"
        return info

    if not xde_sifen:
        info.message = "Los elementos <xDE> deben estar namespaceados con SIFEN"
        return info

    nested_total = 0
    for idx, xde in enumerate(xde_sifen, start=1):
        nested_rde = [c for c in list(xde) if _local_name(c.tag) == "rDE"]
        if len(nested_rde) != 1:
            info.message = f"Cada <xDE> debe contener exactamente un <rDE> (xDE #{idx} tiene {len(nested_rde)})"
            return info
        if _namespace_uri(nested_rde[0].tag) != SIFEN_NS:
            info.message = f"El <rDE> dentro de <xDE> #{idx} debe usar el namespace SIFEN"
            return info
        nested_total += 1
        if info.first_rde is None:
            info.first_rde = nested_rde[0]

    if nested_total == 0:
        info.message = "lote.xml debe contener al menos un <rDE> (directo o dentro de <xDE>)"
        return info

    info.valid = True
    info.mode = "xde_wrapped"
    info.nested_rde_total = nested_total
    return info


def _verify_double_wrapper_tips(payload_xml: str, artifacts_dir: Path):
    """
    Verifica que el xml_file.xml dentro del xDE tenga el doble wrapper TIPS.
    
    Expected: <?xml ...?><rLoteDE><rLoteDE xmlns=...>...</rLoteDE></rLoteDE>
    """
    import base64
    import zipfile
    import re
    
    try:
        # Extraer xDE del SOAP
        xde_match = re.search(r"<(?:sifen:)?xDE>([^<]+)</(?:sifen:)?xDE>", payload_xml)
        if not xde_match:
            print("❌ DEBUG DOUBLE WRAPPER: No se encontró <xDE> en el SOAP")
            return
        
        # Decodificar base64
        xde_b64 = xde_match.group(1).strip()
        zip_bytes = base64.b64decode(xde_b64)
        
        # Guardar ZIP para referencia
        xde_zip_path = artifacts_dir / "xde_from_stage13.zip"
        with open(xde_zip_path, "wb") as f:
            f.write(zip_bytes)
        print(f"✅ DEBUG DOUBLE WRAPPER: ZIP guardado: {xde_zip_path}")
        
        # Extraer lote.xml
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
            if ZIP_INTERNAL_FILENAME not in zf.namelist():
                print(f"❌ DEBUG DOUBLE WRAPPER: No se encontró {ZIP_INTERNAL_FILENAME} en el ZIP")
                return
            
            xml_content = zf.read(ZIP_INTERNAL_FILENAME).decode("utf-8")
        
        # Verificar doble wrapper
        # Buscar patrón: <?xml ...?><rLoteDE><rLoteDE xmlns=...
        pattern = r'^<\?xml[^>]*\?>\s*<rLoteDE>\s*<rLoteDE[^>]*xmlns='
        if re.match(pattern, xml_content):
            print("✅ DEBUG DOUBLE WRAPPER: Estructura TIPS correcta encontrada!")
            print(f"   HEAD: {xml_content[:100]}...")
        else:
            print("❌ DEBUG DOUBLE WRAPPER: Estructura TIPS NO encontrada")
            print(f"   HEAD: {xml_content[:100]}...")
            
            # Guardar xml_file.xml para inspección
            xml_file_path = artifacts_dir / "xml_file_from_xde.xml"
            with open(xml_file_path, "w", encoding="utf-8") as f:
                f.write(xml_content)
            print(f"   Guardado para inspección: {xml_file_path}")
    
    except Exception as e:
        print(f"❌ DEBUG DOUBLE WRAPPER: Error verificando: {e}")
        import traceback
        traceback.print_exc()


class SoapClient:
    """Cliente SOAP 1.2 (document/literal) para SIFEN, con mTLS."""

    def __init__(self, config: SifenConfig):
        self.config = config
        self.roshka_mode = os.getenv("SIFEN_ROSHKA_MODE", "0") == "1"

        if not ZEEP_AVAILABLE:
            raise SifenClientError(
                "zeep no está instalado. Instale con: pip install zeep"
            )

        # Timeouts / retries
        self.connect_timeout = int(os.getenv("SIFEN_SOAP_TIMEOUT_CONNECT", "15"))
        self.read_timeout = int(os.getenv("SIFEN_SOAP_TIMEOUT_READ", "45"))
        self.max_retries = int(os.getenv("SIFEN_SOAP_MAX_RETRIES", "3"))

        # Modo compatibilidad Roshka
        self.roshka_compat = os.getenv("SIFEN_SOAP_COMPAT", "").lower() == "roshka"
        if self.roshka_compat:
            logger.info("Modo compatibilidad Roshka activado")
        if self.roshka_mode:
            logger.info(
                "ROSHKA_MODE enabled: SOAP 1.1 + Content-Type application/xml; no SOAPAction; endpoint .wsdl"
            )
        else:
            logger.info("ROSHKA_MODE disabled: SOAP 1.2 default")

        # Transporte con mTLS
        self.transport = self._create_transport()

        # Cache
        self.clients: Dict[str, Any] = {}  # Client de Zeep
        self._soap_address: Dict[str, str] = {}
        self._zeep_client = None
        self._zeep_wsdl = None

    # ---------------------------------------------------------------------
    # Helpers WSDL
    # ---------------------------------------------------------------------
    def _normalize_wsdl_url(self, wsdl_url: str) -> str:
        """Normaliza URLs de WSDL.

        En SIFEN-test se observó:
        - .../recibe.wsdl -> HTTP 200 pero body vacío (len=0)
        - .../recibe.wsdl?wsdl -> WSDL real
        Por eso forzamos ?wsdl si no está.
        """
        u = (wsdl_url or "").strip()
        if not u:
            return u

        # Si ya trae query, no tocamos (ej: ?wsdl)
        if "?" in u:
            return u

        # Si termina en .wsdl, forzar ?wsdl
        if u.endswith(".wsdl"):
            return f"{u}?wsdl"

        return u

    @staticmethod
    def _normalize_soap_endpoint(url: str) -> str:
        """Normaliza un endpoint SOAP quitando .wsdl y query strings.

        Ejemplos:
        - https://.../recibe.wsdl?wsdl -> https://.../recibe
        - https://.../recibe.wsdl      -> https://.../recibe
        - https://.../recibe            -> https://.../recibe
        """
        if not url:
            return url

        # Quitar query string
        if "?" in url:
            url = url.split("?")[0]

        # Quitar .wsdl si termina en eso
        if url.endswith(".wsdl"):
            url = url[:-5]  # quitar ".wsdl"

        return url

    def _parse_soap_address_from_wsdl(self, wsdl_content: bytes) -> Optional[str]:
        """Extrae soap:address/soap12:address desde un WSDL ya descargado."""
        if not wsdl_content:
            return None

        try:
            wsdl_xml = etree.fromstring(wsdl_content)
        except Exception as exc:
            logger.debug(f"No se pudo parsear WSDL para extraer soap:address: {exc}")
            return None

        ns = {
            "wsdl": "http://schemas.xmlsoap.org/wsdl/",
            "soap12": "http://schemas.xmlsoap.org/wsdl/soap12/",
            "soap": "http://schemas.xmlsoap.org/wsdl/soap/",
        }

        location_raw = None
        addr = wsdl_xml.find(".//soap12:address", namespaces=ns)
        if addr is not None:
            location_raw = addr.get("location")
        else:
            addr = wsdl_xml.find(".//soap:address", namespaces=ns)
            if addr is not None:
                location_raw = addr.get("location")

        if not location_raw:
            return None

        if self.roshka_compat:
            logger.debug(
                f"SOAP endpoint extraído (Roshka compat, sin normalizar): {location_raw}"
            )
            return location_raw

        endpoint_normalized = self._normalize_soap_endpoint(location_raw)
        logger.debug(
            f"SOAP endpoint extraído: location_raw={location_raw}, "
            f"endpoint_normalized={endpoint_normalized}"
        )
        return endpoint_normalized

    def _get_zeep_client(self, wsdl_url: str) -> Client:
        """Crea (o reutiliza) un cliente Zeep para generar envelopes."""
        if self._zeep_client is not None and self._zeep_wsdl == wsdl_url:
            return self._zeep_client

        transport = Transport(session=self.transport.session, cache=None, timeout=self.read_timeout)
        settings = Settings(strict=False, xml_huge_tree=True)
        self._zeep_client = Client(wsdl_url, transport=transport, settings=settings)
        self._zeep_wsdl = wsdl_url
        return self._zeep_client

    def _is_valid_wsdl_content(self, content: bytes) -> bool:
        """Check if content is a valid WSDL (not HTML/redirect from BIG-IP)."""
        if not content:
            return False
        
        content_str = content.decode('utf-8', errors='ignore').lower()
        
        # Check for HTML indicators (BIG-IP logout page)
        if '<html' in content_str or 'big-ip' in content_str:
            logger.warning("WSDL content appears to be HTML/BIG-IP logout page")
            return False
        
        # Check for WSDL indicators
        if 'definitions' in content_str or 'wsdl:definitions' in content_str:
            return True
        
        logger.warning("Content does not appear to be a valid WSDL")
        return False
    
    def _get_cached_wsdl(self, cache_key: str) -> Optional[bytes]:
        """Get WSDL from local cache if valid."""
        cache_file = WSDL_CACHE_DIR / cache_key
        
        if not cache_file.exists():
            return None
        
        try:
            content = cache_file.read_bytes()
            if self._is_valid_wsdl_content(content):
                logger.info(f"Using cached WSDL: {cache_key}")
                return content
            else:
                logger.warning(f"Cached WSDL is invalid, deleting: {cache_key}")
                cache_file.unlink()
        except Exception as e:
            logger.warning(f"Error reading cached WSDL {cache_key}: {e}")
        
        return None
    
    def _cache_wsdl(self, cache_key: str, content: bytes) -> None:
        """Save WSDL to local cache."""
        try:
            cache_file = WSDL_CACHE_DIR / cache_key
            cache_file.write_bytes(content)
            logger.info(f"WSDL cached: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to cache WSDL {cache_key}: {e}")
    
    def _resolve_endpoint_and_wsdl(
        self, wsdl_url: str
    ) -> Tuple[Optional[str], Optional[bytes], str, Optional[int], Optional[str]]:
        """Obtiene WSDL, extrae soap:address y retorna metadata.
        
        Now includes BIG-IP protection and local caching.
        """
        wsdl_url = (wsdl_url or "").strip()
        wsdl_url_final = self._normalize_wsdl_url(wsdl_url)
        session = (
            self.transport.session if hasattr(self, "transport") else Session()
        )

        wsdl_status: Optional[int] = None
        wsdl_error: Optional[str] = None
        content: Optional[bytes] = None
        
        # Generate cache key based on environment and service
        env = "test" if "test" in wsdl_url_final.lower() else "prod"
        service = "unknown"
        if "consulta-ruc" in wsdl_url_final:
            service = "consulta-ruc"
        elif "recibe-lote" in wsdl_url_final:
            service = "recibe-lote"
        elif "recibe" in wsdl_url_final:
            service = "recibe"
        cache_key = f"{service}_{env}.wsdl"

        # Try cache first
        cached_content = self._get_cached_wsdl(cache_key)
        if cached_content:
            endpoint = self._parse_soap_address_from_wsdl(cached_content)
            if not endpoint:
                wsdl_error = "soap:address no encontrado en WSDL cacheado"
            return endpoint, cached_content, wsdl_url_final, wsdl_status, wsdl_error
        
        # Si existe snapshot local para este WSDL, usarlo
        local_snapshot = None
        snapshots_dir = get_project_root() / "wsdl_snapshots"
        snapshot_candidates = [
            snapshots_dir / "consulta-ruc_test.wsdl",
            snapshots_dir / "consulta-ruc_prod.wsdl",
        ]

        for snapshot in snapshot_candidates:
            if snapshot.exists() and snapshot.stat().st_size > 0:
                local_snapshot = snapshot.read_bytes()
                logger.info(f"Usando snapshot WSDL local: {snapshot}")
                break

        if local_snapshot:
            endpoint = self._parse_soap_address_from_wsdl(local_snapshot)
            if not endpoint:
                wsdl_error = "soap:address no encontrado en snapshot WSDL"
            return endpoint, local_snapshot, wsdl_url_final, wsdl_status, wsdl_error

        try:
            # Make request WITHOUT following redirects (BIG-IP protection)
            resp = session.get(
                wsdl_url_final, 
                timeout=(self.connect_timeout, self.read_timeout),
                cert=getattr(session, "cert", None),
                allow_redirects=False  # Don't follow redirects to avoid BIG-IP hangup
            )
            wsdl_status = resp.status_code
            
            # Check for redirects (BIG-IP hangup)
            if resp.status_code in (301, 302, 303, 307, 308):
                wsdl_error = f"WSDL inválido: recibí redirect (status {resp.status_code}) - BIG-IP hangup. Reintentar o usar cache local."
                logger.error(wsdl_error)
                raise SifenClientError(wsdl_error)
            
            content = resp.content if resp.content else None
            
            # Validate content is WSDL (not HTML)
            if content and not self._is_valid_wsdl_content(content):
                wsdl_error = "WSDL inválido: recibí HTML/redirect (BIG-IP hangup). Reintentar o usar cache local."
                logger.error(wsdl_error)
                raise SifenClientError(wsdl_error)

            if resp.status_code != 200 or not resp.content:
                wsdl_error = (
                    f"status={resp.status_code}, len={len(resp.content or b'')}"
                )
                logger.warning(
                    f"WSDL vacío o error HTTP al obtener WSDL: {wsdl_url_final} "
                    f"({wsdl_error})"
                )
                return None, content, wsdl_url_final, wsdl_status, wsdl_error

            # Cache the valid WSDL
            self._cache_wsdl(cache_key, resp.content)
            
            endpoint = self._parse_soap_address_from_wsdl(resp.content)
            if not endpoint:
                wsdl_error = "soap:address no encontrado en WSDL"
            return endpoint, resp.content, wsdl_url_final, wsdl_status, wsdl_error
        except Exception as exc:
            wsdl_error = str(exc)
            logger.debug(
                f"No se pudo extraer SOAP address desde WSDL ({wsdl_url_final}): {exc}"
            )
            return None, content, wsdl_url_final, wsdl_status, wsdl_error

    def _extract_soap_address_from_wsdl(self, wsdl_url: str) -> Optional[str]:
        """Compat wrapper que retorna solo el endpoint resuelto desde un WSDL."""
        endpoint, _, _, _, _ = self._resolve_endpoint_and_wsdl(wsdl_url)
        return endpoint

    # ---------------------------------------------------------------------
    # Transport (mTLS)
    # ---------------------------------------------------------------------
    def _create_transport(self) -> Any:  # Transport de Zeep
        """Crea el transporte Zeep con requests.Session configurada para mTLS."""
        session = Session()

        # Usar certificado mTLS (PEM)
        # Soporta:
        #   - combined.pem (cert+key en un solo archivo) via SIFEN_CERT_PATH
        #   - cert/key separados via SIFEN_CERT_PATH + SIFEN_KEY_PATH
        cert_path = os.getenv('SIFEN_CERT_PATH') or getattr(self.config, 'cert_path', None)
        key_path  = os.getenv('SIFEN_KEY_PATH')  or getattr(self.config, 'key_path', None)

        if cert_path:
            cert_path_p = Path(str(cert_path))
            if not cert_path_p.exists():
                raise SifenClientError(f'Certificado PEM no encontrado: {cert_path_p}')

            if key_path:
                key_path_p = Path(str(key_path))
                if not key_path_p.exists():
                    raise SifenClientError(f'Key PEM no encontrada: {key_path_p}')
                session.cert = (str(cert_path_p), str(key_path_p))
                logger.info(f'Usando mTLS via cert/key: {cert_path_p.name} + {key_path_p.name}')
            else:
                session.cert = str(cert_path_p)
                logger.info(f'Usando mTLS via combined PEM: {cert_path_p.name}')
        else:
            raise SifenClientError(
                "mTLS es requerido para SIFEN. Configurá SIFEN_CERT_PATH (combined.pem) o SIFEN_CERT_PATH+SIFEN_KEY_PATH (cert/key separados).",
                result={
                    'ok': False,
                    'error': 'Missing SIFEN_CERT_PATH for mTLS certificate',
                    'endpoint': None,
                    'http_status': None,
                    'raw_xml': None,
                    'dCodRes': None,
                    'dMsgRes': None,
                }
            )

        return Transport(  # type: ignore[arg-type]
            session=session,
            timeout=(self.connect_timeout, self.read_timeout),  # type: ignore[arg-type]
            operation_timeout=self.read_timeout,
        )

    # ---------------------------------------------------------------------
    # Size validation
    # ---------------------------------------------------------------------
    def _validate_size(self, service: str, content: str) -> None:
        size = len(content.encode("utf-8"))
        limit = SIZE_LIMITS.get(service)
        if limit and size > limit:
            error_code = {
                "siRecepDE": "0200",
                "siRecepLoteDE": "0270",
                "siConsRUC": "0460",
            }.get(service, "0000")
            raise SifenSizeLimitError(service, size, limit, error_code)

    # ---------------------------------------------------------------------
    # Endpoint resolution con fallback (enfoque Roshka)
    # ---------------------------------------------------------------------
    def _resolve_endpoint_with_fallback(self, service_key: str) -> str:
        """
        Resuelve endpoint SOAP con fallback en orden:
        1. Variable de entorno específica (SIFEN_*_ENDPOINT)
        2. Config.get_soap_service_url()
        3. URL normalizada sin ?wsdl
        """
        # Mapeo de servicios a env vars
        env_var_map = {
            "consulta_ruc": "SIFEN_GATE_ENDPOINT",
            "consulta": "SIFEN_CONSDE_ENDPOINT",
            "recibe_lote": "SIFEN_RECEP_LOTE_ENDPOINT",
        }
        
        # 1. Intentar usar env var si existe
        env_var = env_var_map.get(service_key)
        if env_var:
            endpoint = os.getenv(env_var, "").strip()
            if endpoint:
                logger.info(f"Usando endpoint desde {env_var}: {endpoint}")
                return endpoint
        
        # 2. Usar config
        config_url = self.config.get_soap_service_url(service_key)
        if config_url:
            # Intentar extraer endpoint del WSDL, pero sin fallar si hay errores de conexión
            try:
                resolved = self._extract_soap_address_from_wsdl(config_url)
                if resolved:
                    logger.info(f"Endpoint resuelto desde WSDL: {resolved}")
                    return resolved
            except Exception as e:
                logger.warning(f"No se pudo resolver endpoint desde WSDL ({config_url}): {e}. Usando fallback.")
                # Continuar al fallback sin error
        
        # 3. Fallback: normalizar URL sin ?wsdl
        if config_url:
            fallback = self._normalize_soap_endpoint(config_url)
            logger.info(f"Usando endpoint fallback (normalizado): {fallback}")
            return fallback
        
        raise SifenClientError(f"No se pudo resolver endpoint para servicio '{service_key}'")

    # ---------------------------------------------------------------------
    # Métodos de consulta (como métodos de clase)
    # ---------------------------------------------------------------------

    def consulta_ruc_raw(self, ruc: str, dump_http: bool = False, did: Optional[str] = None) -> Dict[str, Any]:
        """Consulta estado y habilitación de un RUC (modo GATE) sin descargar WSDL.

        Intenta variantes en orden:
        1) SOAP 1.2 + RUC sin DV
        2) SOAP 1.2 + RUC con DV
        3) SOAP 1.1 + RUC sin DV
        4) SOAP 1.1 + RUC con DV
        """
        import lxml.etree as etree  # noqa: F401
        import datetime as _dt
        import random
        import time

        action_value = "siConsRUC"

        # Resolver endpoint fijo para consulta_ruc (sin descargar WSDL)
        def _normalize_gate_endpoint(url: str) -> str:
            """Alinea con Roshka: usar .wsdl sin ?wsdl."""
            u = (url or "").strip()
            if not u:
                return u
            # quitar ?wsdl o cualquier query
            if "?" in u:
                u = u.split("?", 1)[0]
            u = u.rstrip("/")
            if not u.endswith(".wsdl"):
                if u.endswith("consulta-ruc"):
                    u = f"{u}.wsdl"
                else:
                    u = f"{u}.wsdl"
            return u

        env_override = os.getenv("SIFEN_CONSULTA_RUC_URL", "").strip()
        if env_override:
            post_url = _normalize_gate_endpoint(env_override)
            logger.info(f"consulta_ruc usando SIFEN_CONSULTA_RUC_URL={post_url}")
        else:
            cfg_url = self.config.get_soap_service_url("consulta_ruc")
            if not cfg_url:
                raise SifenClientError("No se pudo resolver endpoint para consulta_ruc (config vacío)")
            post_url = _normalize_gate_endpoint(cfg_url)
            logger.info(f"consulta_ruc endpoint desde config (gate-normalized): {post_url}")

        # Validar/normalizar RUC (manteniendo base y DV para compat mode)
        try:
            normalized_ruc = normalize_sifen_truc(ruc)
        except RucFormatError as e:
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            raise SifenClientError(f"Formato de RUC inválido para consultaRUC: {e}", result=result) from e

        raw_digits = re.sub(r"[^0-9]", "", ruc or "")
        base_part = raw_digits
        dv_part = ""
        if "-" in ruc:
            base_candidate, dv_candidate = ruc.split("-", 1)
            base_part = re.sub(r"[^0-9]", "", base_candidate)
            dv_clean = re.sub(r"[^0-9]", "", dv_candidate)
            dv_part = dv_clean[:1] if dv_clean else ""

        if dv_part:
            ruc_without_dv = base_part or normalized_ruc
            ruc_with_dv = f"{ruc_without_dv}{dv_part}"
        else:
            # Sin DV en el input: ambas variantes son el RUC normalizado (7-8 dígitos)
            ruc_with_dv = normalized_ruc
            ruc_without_dv = normalized_ruc

        if not ruc_without_dv:
            ruc_without_dv = normalized_ruc

        logger.info(
            f"consulta_ruc variantes RUC: sin_dv={ruc_without_dv} con_dv={ruc_with_dv} (input={ruc})"
        )

        # Generar dId (15 dígitos)
        if did is None:
            base = _dt.datetime.now().strftime("%Y%m%d%H%M%S")  # 14 dígitos
            did = f"{base}{random.randint(0, 9)}"

        # Sesión robusta para GATE (retries + connection: close)
        base_session = self.transport.session
        gate_timeout = int(os.getenv("SIFEN_GATE_TIMEOUT", str(self.connect_timeout)))
        gate_retries = int(os.getenv("SIFEN_GATE_RETRIES", "5"))
        session = requests.Session()
        session.cert = getattr(base_session, "cert", None)
        session.verify = getattr(base_session, "verify", None)
        adapter = HTTPAdapter(
            max_retries=Retry(
                total=gate_retries,
                connect=gate_retries,
                read=gate_retries,
                backoff_factor=0.5,
                status_forcelist=[502, 503, 504],
                allowed_methods=False,
            )
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        mtls_cert = getattr(session, "cert", None)
        verify_value = getattr(session, "verify", None)
        mtls_enabled = bool(mtls_cert)

        # Asegurar mTLS para consulta_ruc aunque el transport no lo haya seteado
        if not mtls_enabled:
            cert_path = os.getenv("SIFEN_CERT_PATH")
            
            if cert_path:
                cert_file = Path(cert_path)
                if cert_file.exists():
                    session.cert = str(cert_path)
                    mtls_cert = session.cert
                    mtls_enabled = True
                    
                    if dump_http:
                        logger.info(f"consulta_ruc mTLS FORZADO desde env: cert={cert_path}")
                else:
                    if dump_http:
                        logger.warning(f"No se encontró archivo de certificado: {cert_path}")

        if dump_http:
            logger.info(f"consulta_ruc mTLS enabled={mtls_enabled} verify={verify_value}")

        # Helpers -----------------------------------------------------------
        def _build_envelope(soap_ns: str, ruc_value: str) -> Tuple[bytes, str]:
            envelope = etree.Element(f"{{{soap_ns}}}Envelope", nsmap={"soap": soap_ns})
            etree.SubElement(envelope, f"{{{soap_ns}}}Header")
            body = etree.SubElement(envelope, f"{{{soap_ns}}}Body")
            r_envi = etree.SubElement(body, "rEnviConsRUC", nsmap={None: SIFEN_NS})
            etree.SubElement(r_envi, "dId").text = str(did)
            etree.SubElement(r_envi, "dRUCCons").text = str(ruc_value)

            soap_bytes_local = etree.tostring(
                envelope, xml_declaration=True, encoding="UTF-8", pretty_print=False
            )

            # Validación mínima para detectar XML roto antes de enviarlo
            try:
                parsed = etree.fromstring(soap_bytes_local)
                body_elem = parsed.find(f".//{{{soap_ns}}}Body")
                if body_elem is None or body_elem.find(f"{{{SIFEN_NS}}}rEnviConsRUC") is None:
                    raise RuntimeError("rEnviConsRUC no encontrado en Body")
            except Exception as exc:
                raise RuntimeError(f"Error al construir SOAP consulta RUC: {exc}") from exc

            return soap_bytes_local, soap_bytes_local.decode("utf-8", errors="replace")

        def _build_headers(soap_version: str, roshka_headers: bool = False) -> Dict[str, str]:
            if soap_version == "1.2":
                if roshka_headers:
                    # Roshka usa application/xml sin SOAPAction
                    headers_local = {
                        "Accept": "application/soap+xml, text/xml, */*",
            "Content-Type": "application/soap+xml; charset=utf-8; action=\"siConsRUC\"",
                    }
                else:
                    headers_local = _build_soap12_headers(
                        service="gate", action_value=action_value, accept="application/soap+xml, text/xml, */*"
                    )
            else:
                headers_local = {
                    "Content-Type": "text/xml; charset=utf-8",
                    "Accept": "application/soap+xml, text/xml, */*",
                }
                mode = _soapaction_mode("gate")
                if mode in ("on", "auto"):
                    headers_local["SOAPAction"] = f'"{action_value}"'

            headers_local["Connection"] = "close"
            return headers_local

        def _parse_response(content: bytes) -> Dict[str, Any]:
            parsed: Dict[str, Any] = {}
            if not content:
                return parsed
            try:
                root = etree.fromstring(content)
                def _find_text(local: str) -> Optional[str]:
                    elem = root.find(f".//{{{SIFEN_NS}}}{local}")
                    return elem.text.strip() if elem is not None and elem.text else None

                parsed["dCodRes"] = _find_text("dCodRes")
                parsed["dMsgRes"] = _find_text("dMsgRes")
                parsed["dEstRes"] = _find_text("dEstRes")

                x_cont = root.find(f".//{{{SIFEN_NS}}}xContRUC")
                if x_cont is not None:
                    cont_dict: Dict[str, Any] = {}
                    def _find_child(local: str) -> Optional[str]:
                        elem = x_cont.find(f".//{{{SIFEN_NS}}}{local}")
                        return elem.text.strip() if elem is not None and elem.text else None

                    cont_dict["dRUCCons"] = _find_child("dRUCCons")
                    cont_dict["dRazCons"] = _find_child("dRazCons")
                    cont_dict["dCodEstCons"] = _find_child("dCodEstCons")
                    cont_dict["dDesEstCons"] = _find_child("dDesEstCons")
                    cont_dict["dRUCFactElec"] = _find_child("dRUCFactElec")
                    parsed["xContRUC"] = {k: v for k, v in cont_dict.items() if v is not None}
            except Exception as exc:
                parsed["parse_error"] = f"{type(exc).__name__}: {exc}"
            return parsed

        # Intentos (compat mode)
        attempt_plan = [
            {"soap_version": "1.2", "ruc_value": ruc_without_dv, "label": "soap12_no_dv", "roshka_headers": True},
            {"soap_version": "1.2", "ruc_value": ruc_with_dv, "label": "soap12_with_dv", "roshka_headers": True},
            {"soap_version": "1.1", "ruc_value": ruc_without_dv, "label": "soap11_no_dv", "roshka_headers": False},
            {"soap_version": "1.1", "ruc_value": ruc_with_dv, "label": "soap11_with_dv", "roshka_headers": False},
        ]

        artifacts_dir = get_artifacts_dir()
        attempt_artifacts: List[str] = []
        last_result: Optional[Dict[str, Any]] = None
        success_result: Optional[Dict[str, Any]] = None
        last_error: Optional[Exception] = None

        connection_retry_delays = [0.5, 1.5]
        max_connection_attempts = len(connection_retry_delays) + 1

        for idx, attempt in enumerate(attempt_plan, start=1):
            headers: Dict[str, str] = {}
            soap_xml_str: Optional[str] = None
            attempt_record: Dict[str, Any] = {
                "attempt": idx,
                "label": attempt["label"],
                "endpoint": post_url,
                "soap_version": attempt["soap_version"],
                "ruc_sent": attempt["ruc_value"],
            }
            response_obj = None
            elapsed_ms: Optional[int] = None

            try:
                soap_bytes, soap_xml_str = _build_envelope(
                    SOAP_NS if attempt["soap_version"] == "1.2" else SOAP_NS_11,
                    attempt["ruc_value"],
                )
                headers = _build_headers(attempt["soap_version"], attempt.get("roshka_headers", False))
                attempt_record["xml_size"] = len(soap_bytes)
                attempt_record["request_body"] = soap_xml_str
                attempt_record["request_headers"] = headers

                logger.info(
                    f"[consulta_ruc attempt {idx}] endpoint={post_url} soap={attempt['soap_version']} "
                    f"ruc={attempt['ruc_value']} headers={headers} xml_size={len(soap_bytes)}"
                )
                if dump_http:
                    print(
                        f"[consulta_ruc attempt {idx}] soap={attempt['soap_version']} ruc={attempt['ruc_value']} "
                        f"endpoint={post_url} headers={headers}"
                    )

                # Enviar con reintentos para RemoteDisconnected/errores de conexión
                conn_error: Optional[Exception] = None
                for retry_idx in range(max_connection_attempts):
                    try:
                        start_ts = time.time()
                        response_obj = session.post(
                            post_url,
                            data=soap_bytes,
                            headers=headers,
                            timeout=gate_timeout,
                        )
                        elapsed_ms = int((time.time() - start_ts) * 1000)
                        break
                    except requests.exceptions.ConnectionError as exc:
                        conn_error = exc
                        err_text = f"{type(exc).__name__}: {exc}"
                        attempt_record.setdefault("connection_errors", []).append(err_text)
                        is_remote = "RemoteDisconnected" in err_text or "Remote end" in err_text
                        if is_remote and retry_idx < max_connection_attempts - 1:
                            delay = connection_retry_delays[min(retry_idx, len(connection_retry_delays) - 1)]
                            logger.warning(
                                f"consulta_ruc attempt {idx} conexión caída ({err_text}), retry en {delay}s"
                            )
                            time.sleep(delay)
                            continue
                        raise

                if response_obj is None:
                    raise conn_error or RuntimeError("No se obtuvo respuesta HTTP")

                attempt_record["http_status"] = response_obj.status_code
                attempt_record["response_headers"] = dict(response_obj.headers)
                attempt_record["response_body"] = response_obj.text
                attempt_record["elapsed_ms"] = elapsed_ms

                parsed_fields = _parse_response(response_obj.content)
                attempt_record["parsed"] = parsed_fields

                # Armar resultado para el caller
                result_candidate: Dict[str, Any] = {
                    "endpoint": post_url,
                    "attempt": idx,
                    "http_status": response_obj.status_code,
                    "raw_xml": response_obj.text,
                    "elapsed_ms": elapsed_ms,
                    "soap_version": attempt["soap_version"],
                    "ruc_sent": attempt["ruc_value"],
                    "attempt_artifacts": attempt_artifacts,
                }

                for key in ("dCodRes", "dMsgRes", "dEstRes"):
                    if parsed_fields.get(key):
                        result_candidate[key] = parsed_fields[key]

                if "xContRUC" in parsed_fields:
                    result_candidate["xContRUC"] = parsed_fields["xContRUC"]

                if dump_http:
                    result_candidate["sent_headers"] = headers.copy()
                    result_candidate["sent_xml"] = soap_xml_str
                    result_candidate["received_headers"] = dict(response_obj.headers)

                last_result = result_candidate

                d_cod_res = (parsed_fields.get("dCodRes") or "").strip()
                d_est_res = (parsed_fields.get("dEstRes") or "").strip()
                d_cod_est_cons = ""
                if isinstance(parsed_fields.get("xContRUC"), dict):
                    d_cod_est_cons = str(parsed_fields["xContRUC"].get("dCodEstCons") or "").strip()

                est_ok = d_est_res.upper().startswith("APROB") if d_est_res else False
                est_ok = est_ok or d_cod_est_cons in ("1", "01")
                success = d_cod_res in {"0000", "0502"} or est_ok
                result_candidate["ok"] = success

                if d_cod_res == "0160":
                    logger.warning("consulta_ruc devolvió 0160 XML Mal Formado; probando siguiente variante.")

                # Guardar artifact del intento
                artifact_path = artifacts_dir / f"consulta_ruc_attempt_{idx}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                attempt_artifacts.append(str(artifact_path))
                attempt_record["success"] = success
                attempt_record["artifact_path"] = str(artifact_path)
                try:
                    artifact_path.write_text(
                        json.dumps(attempt_record, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                except Exception:
                    pass

                if success:
                    success_result = result_candidate
                    break

            except Exception as exc:
                last_error = exc
                attempt_record["error"] = f"{type(exc).__name__}: {exc}"
                artifact_path = artifacts_dir / f"consulta_ruc_attempt_{idx}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                attempt_record["artifact_path"] = str(artifact_path)
                attempt_record.setdefault("request_headers", headers)
                attempt_record.setdefault("request_body", soap_xml_str or "")
                try:
                    artifact_path.write_text(
                        json.dumps(attempt_record, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    attempt_artifacts.append(str(artifact_path))
                except Exception:
                    pass
                logger.error(f"consulta_ruc attempt {idx} falló: {type(exc).__name__}: {exc}")
                continue

        if success_result:
            success_result["attempt_artifacts"] = attempt_artifacts
            return success_result

        if last_result:
            last_result["ok"] = last_result.get("ok", False)
            last_result["attempt_artifacts"] = attempt_artifacts
            if last_error:
                last_result["error"] = f"{type(last_error).__name__}: {last_error}"
            return last_result

        raise SifenClientError(
            "No se pudo consultar RUC: sin respuesta utilizable",
            result={"endpoint": post_url, "attempt_artifacts": attempt_artifacts},
        )

    def consulta_de_por_cdc_raw(self, cdc: str, dump_http: bool = False, did: Optional[str] = None) -> Dict[str, Any]:
        """Consulta estado de un DE individual por CDC (sin depender del WSDL).
        
        Args:
            cdc: CDC (Código de Control) del documento electrónico
            dump_http: Si True, retorna también sent_headers y sent_xml para debug
            did: dId opcional (si None, se genera automáticamente con formato YYYYMMDDHHMMSS + 1 dígito = 15 dígitos)
            
        Returns:
            Dict con http_status, raw_xml, y opcionalmente dCodRes/dMsgRes/dProtAut.
            Si dump_http=True, también incluye sent_headers y sent_xml.
        """
        import lxml.etree as etree  # noqa: F401
        import datetime as _dt
        import random
        import time
        
        # Generar dId de 15 dígitos si no se proporciona (formato: YYYYMMDDHHMMSS + 1 dígito aleatorio)
        # Igual que en siRecepLoteDE
        if did is None:
            base = _dt.datetime.now().strftime("%Y%m%d%H%M%S")  # 14 dígitos
            did = f"{base}{random.randint(0, 9)}"  # + 1 dígito = 15 dígitos total
        
        # Construir SOAP 1.2 envelope con estructura exacta requerida según XSD
        # XSD: WS_SiConsDE_v141.xsd define rEnviConsDeRequest con dId y dCDC
        SOAP_12_NS = "http://www.w3.org/2003/05/soap-envelope"
        
        # Envelope SOAP 1.2
        envelope = etree.Element(
            f"{{{SOAP_12_NS}}}Envelope",
            nsmap={"soap": SOAP_12_NS}
        )
        
        # Header vacío
        header = etree.SubElement(envelope, f"{{{SOAP_12_NS}}}Header")
        
        # Body
        body = etree.SubElement(envelope, f"{{{SOAP_12_NS}}}Body")
        
        # rEnviConsDeRequest según XSD (targetNamespace: http://ekuatia.set.gov.py/sifen/xsd)
        # XSD define: <xs:element name="rEnviConsDeRequest">
        # IMPORTANTE: Usar "rEnviConsDeRequest" (con D mayúscula y "Request")
        r_envi_cons_de_request = etree.SubElement(
            body, "rEnviConsDeRequest", nsmap={None: SIFEN_NS}
        )
        
        # dId OBLIGATORIO según XSD (tipo: dIdType) - debe ser hijo directo y primero
        d_id_elem = etree.SubElement(r_envi_cons_de_request, "dId")
        d_id_elem.text = str(did)
        
        # dCDC requerido según XSD (tipo: tCDC) - debe ser hijo directo y segundo
        d_cdc_elem = etree.SubElement(r_envi_cons_de_request, "dCDC")
        d_cdc_elem.text = str(cdc)
        
        # Serializar SOAP
        soap_bytes = etree.tostring(
            envelope, xml_declaration=True, encoding="UTF-8", pretty_print=False
        )
        
        # HARD-FAIL LOCAL ANTES DE ENVIAR: Verificar que el SOAP generado parsea correctamente
        try:
            # Intentar parsear el SOAP generado
            test_root = etree.fromstring(soap_bytes)
            
            # Validar estructura básica: Envelope->Body->rEnviConsDeRequest
            soap_env_ns = "http://www.w3.org/2003/05/soap-envelope"
            body_elem = test_root.find(f".//{{{soap_env_ns}}}Body")
            if body_elem is None:
                raise RuntimeError(f"SOAP Body no encontrado después de generar. SOAP:\n{soap_bytes.decode('utf-8', errors='replace')}")
            
            # Validar que rEnviConsDeRequest existe en Body (hijo directo)
            request_elem = body_elem.find(f"{{{SIFEN_NS}}}rEnviConsDeRequest")
            if request_elem is None:
                # Intentar sin namespace
                request_elem = body_elem.find(".//rEnviConsDeRequest")
            
            if request_elem is None:
                # Intentar buscar cualquier hijo directo de Body para debug
                body_children = [etree.QName(ch.tag).localname if isinstance(ch.tag, str) else str(ch.tag) for ch in body_elem]
                raise RuntimeError(
                    f"rEnviConsDeRequest no encontrado en SOAP Body. "
                    f"Hijos directos de Body: {body_children}. "
                    f"SOAP:\n{soap_bytes.decode('utf-8', errors='replace')}"
                )
            
            # Verificar que rEnviConsDeRequest es hijo directo de Body (no descendiente)
            if request_elem.getparent() is not body_elem:
                raise RuntimeError(
                    f"rEnviConsDeRequest no es hijo directo de Body. "
                    f"Parent: {etree.QName(request_elem.getparent().tag).localname if request_elem.getparent() is not None else 'None'}. "
                    f"SOAP:\n{soap_bytes.decode('utf-8', errors='replace')}"
                )
            
            # Validar que tiene dId y dCDC como hijos directos y no vacíos
            d_id_check = request_elem.find(f"{{{SIFEN_NS}}}dId")
            if d_id_check is None:
                d_id_check = request_elem.find("dId")
            if d_id_check is None:
                raise RuntimeError(
                    f"dId no encontrado en rEnviConsDeRequest. "
                    f"SOAP:\n{soap_bytes.decode('utf-8', errors='replace')}"
                )
            if not d_id_check.text or not d_id_check.text.strip():
                raise RuntimeError(
                    f"dId está vacío en rEnviConsDeRequest. "
                    f"SOAP:\n{soap_bytes.decode('utf-8', errors='replace')}"
                )
            
            d_cdc_check = request_elem.find(f"{{{SIFEN_NS}}}dCDC")
            if d_cdc_check is None:
                d_cdc_check = request_elem.find("dCDC")
            if d_cdc_check is None:
                raise RuntimeError(
                    f"dCDC no encontrado en rEnviConsDeRequest. "
                    f"SOAP:\n{soap_bytes.decode('utf-8', errors='replace')}"
                )
            if not d_cdc_check.text or not d_cdc_check.text.strip():
                raise RuntimeError(
                    f"dCDC está vacío en rEnviConsDeRequest. "
                    f"SOAP:\n{soap_bytes.decode('utf-8', errors='replace')}"
                )
            
            # Validar orden según XSD: primero dId, luego dCDC
            children = list(request_elem)
            if len(children) < 2:
                raise RuntimeError(
                    f"rEnviConsDeRequest debe tener al menos 2 hijos (dId y dCDC), encontrados: {len(children)}. "
                    f"SOAP:\n{soap_bytes.decode('utf-8', errors='replace')}"
                )
            
            first_child_local = etree.QName(children[0]).localname if children[0].tag else None
            second_child_local = etree.QName(children[1]).localname if len(children) > 1 and children[1].tag else None
            
            if first_child_local != "dId":
                raise RuntimeError(
                    f"Primer hijo de rEnviConsDeRequest debe ser 'dId', encontrado: '{first_child_local}'. "
                    f"SOAP:\n{soap_bytes.decode('utf-8', errors='replace')}"
                )
            if second_child_local != "dCDC":
                raise RuntimeError(
                    f"Segundo hijo de rEnviConsDeRequest debe ser 'dCDC', encontrado: '{second_child_local}'. "
                    f"SOAP:\n{soap_bytes.decode('utf-8', errors='replace')}"
                )
            
            # Imprimir SOAP generado para validación (siempre en debug, también en consola si dump_http)
            soap_xml_str = soap_bytes.decode("utf-8", errors="replace")
            logger.debug(f"SOAP generado para consulta DE por CDC (validado OK):\n{soap_xml_str}")
            
            # Si dump_http está activo, también imprimir en consola
            if dump_http:
                print("\n" + "="*70)
                print("SOAP GENERADO PARA CONSULTA DE POR CDC (VALIDADO)")
                print("="*70)
                print(soap_xml_str)
                print("="*70)
                print(f"✅ Validación previa: SOAP parsea correctamente")
                print(f"   - Elemento root: rEnviConsDeRequest")
                print(f"   - Namespace: {SIFEN_NS}")
                print(f"   - dId: {d_id_check.text} (15 dígitos: {len(d_id_check.text) == 15})")
                print(f"   - dCDC: {d_cdc_check.text}")
                print("="*70 + "\n")
                
        except etree.XMLSyntaxError as e:
            raise RuntimeError(f"SOAP generado no es XML válido: {e}\nSOAP:\n{soap_bytes.decode('utf-8', errors='replace')}") from e
        except Exception as e:
            raise RuntimeError(f"Error al validar SOAP generado: {e}") from e
        
        # Usar endpoint con fallback (enfoque Roshka)
        post_url = self._resolve_endpoint_with_fallback("consulta")
        
        # Headers SOAP 1.2 (application/soap+xml con action URI completo, NO "rEnviConsDE")
        headers = {
            "Content-Type": 'application/soap+xml; charset=utf-8; action="http://ekuatia.set.gov.py/sifen/xsd/siConsDE"',
            "Accept": "application/soap+xml, text/xml, */*",
        }
        
        # Si dump_http está activo, guardar headers y XML enviados
        soap_xml_str = soap_bytes.decode("utf-8", errors="replace")
        result: Dict[str, Any] = {
            "http_status": 0,
            "raw_xml": "",
            "endpoint": post_url,
        }
        if dump_http:
            result["sent_headers"] = headers.copy()
            result["sent_xml"] = soap_xml_str
        
        # POST usando la sesión existente con mTLS
        session = self.transport.session
        
        # RETRY por errores de conexión (solo para esta consulta, NO para envíos)
        max_attempts = 3
        retry_delays = [0.5, 1.5]  # 0.5s después del primer intento, 1.5s después del segundo
        
        artifacts_dir = None
        http_log_path = None
        http_log_lines: List[str] = []
        artifact_timestamp = None

        if dump_http:
            artifacts_dir = get_artifacts_dir()
            artifact_timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            http_log_path = artifacts_dir / f"consulta_de_http_{artifact_timestamp}.txt"

            http_log_lines.append(f"Timestamp: {artifact_timestamp}")
            http_log_lines.append(f"Endpoint: {post_url}")

        last_exception = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = session.post(
                    post_url,
                    data=soap_bytes,
                    headers=headers,
                    timeout=(self.connect_timeout, self.read_timeout),
                    cert=getattr(session, "cert", None),
                )
                result["http_status"] = resp.status_code
                result["raw_xml"] = resp.text
                if dump_http and http_log_path:
                    http_log_lines.append(
                        f"HTTP attempt {attempt}: status={resp.status_code}"
                    )
                
                # Si dump_http está activo, agregar headers y body recibidos
                if dump_http:
                    result["received_headers"] = dict(resp.headers)
                    body_lines = resp.text.split("\n") if resp.text else []
                    if len(body_lines) > 500:
                        result["received_body_preview"] = "\n".join(body_lines[:500]) + f"\n... (truncado, total {len(body_lines)} líneas)"
                    else:
                        result["received_body_preview"] = resp.text
                
                # Guardar debug incluso si HTTP != 200
                debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
                if debug_enabled:
                    try:
                        from pathlib import Path
                        out_dir = Path("artifacts")
                        out_dir.mkdir(exist_ok=True)
                        received_file = out_dir / "soap_last_received_consulta_de.xml"
                        received_file.write_bytes(resp.content)
                    except Exception:
                        pass  # No romper el flujo si falla debug
                
                # Guardar artifacts de dump_http incluso si hay error HTTP
                if dump_http:
                    try:
                        from pathlib import Path
                        artifacts_dir = Path("artifacts")
                        artifacts_dir.mkdir(exist_ok=True)
                        timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                        
                        # Guardar SOAP enviado
                        sent_file = artifacts_dir / f"consulta_de_sent_{timestamp}.xml"
                        sent_file.write_text(soap_xml_str, encoding="utf-8")
                        
                        # Guardar headers enviados
                        headers_sent_file = artifacts_dir / f"consulta_de_headers_sent_{timestamp}.json"
                        import json
                        headers_sent_file.write_text(
                            json.dumps(headers, indent=2, ensure_ascii=False),
                            encoding="utf-8"
                        )
                        
                        # Guardar headers recibidos
                        headers_recv_file = artifacts_dir / f"consulta_de_headers_received_{timestamp}.json"
                        headers_recv_file.write_text(
                            json.dumps(dict(resp.headers), indent=2, ensure_ascii=False),
                            encoding="utf-8"
                        )
                        
                        # Guardar body recibido
                        body_recv_file = artifacts_dir / f"consulta_de_response_{timestamp}.xml"
                        body_recv_file.write_text(resp.text, encoding="utf-8")
                    except Exception:
                        pass  # No romper el flujo si falla guardar artifacts
                
                # Intentar parsear XML y extraer dCodRes/dMsgRes/dProtAut si existen
                try:
                    resp_root = etree.fromstring(resp.content)
                    cod_res = resp_root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dCodRes")
                    msg_res = resp_root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dMsgRes")
                    prot_aut = resp_root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dProtAut")
                    if cod_res is not None and cod_res.text:
                        result["dCodRes"] = cod_res.text.strip()
                    if msg_res is not None and msg_res.text:
                        result["dMsgRes"] = msg_res.text.strip()
                    if prot_aut is not None and prot_aut.text:
                        result["dProtAut"] = prot_aut.text.strip()
                except Exception:
                    pass  # Si no se puede parsear, solo devolver raw_xml
                
                # Éxito: salir del loop de retry
                break
                
            except (ConnectionResetError, requests.exceptions.ConnectionError) as e:
                # Errores de conexión: retry
                last_exception = e
                if dump_http and http_log_path:
                    http_log_lines.append(
                        f"HTTP attempt {attempt}: Connection error: {type(e).__name__}: {e}"
                    )
                if attempt < max_attempts:
                    delay = retry_delays[attempt - 1] if attempt <= len(retry_delays) else retry_delays[-1]
                    logger.warning(f"Error de conexión al consultar DE por CDC (intento {attempt}/{max_attempts}): {e}. Reintentando en {delay}s...")
                    time.sleep(delay)
                else:
                    # Último intento falló: guardar artifacts si dump_http y luego re-raise
                    if dump_http:
                        try:
                            from pathlib import Path
                            artifacts_dir = Path("artifacts")
                            artifacts_dir.mkdir(exist_ok=True)
                            timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                            
                            # Guardar SOAP enviado (aunque falló)
                            sent_file = artifacts_dir / f"consulta_de_sent_ERROR_{timestamp}.xml"
                            sent_file.write_text(soap_xml_str, encoding="utf-8")
                            
                            # Guardar headers enviados
                            headers_sent_file = artifacts_dir / f"consulta_de_headers_sent_ERROR_{timestamp}.json"
                            import json
                            headers_sent_file.write_text(
                                json.dumps(headers, indent=2, ensure_ascii=False),
                                encoding="utf-8"
                            )
                            
                            # Guardar error
                            error_file = artifacts_dir / f"consulta_de_error_{timestamp}.txt"
                            error_file.write_text(
                                f"Error de conexión después de {max_attempts} intentos:\n{type(e).__name__}: {e}\n",
                                encoding="utf-8"
                            )
                        except Exception:
                            pass
                    raise SifenClientError(f"Error de conexión al consultar DE por CDC después de {max_attempts} intentos: {e}") from e
            except Exception as e:
                # Otros errores: no retry, guardar artifacts si dump_http y re-raise
                last_exception = e
                if dump_http and http_log_path:
                    http_log_lines.append(
                        f"HTTP attempt {attempt}: Exception: {type(e).__name__}: {e}"
                    )
                if dump_http:
                    try:
                        from pathlib import Path
                        artifacts_dir = Path("artifacts")
                        artifacts_dir.mkdir(exist_ok=True)
                        timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                        
                        # Guardar SOAP enviado (aunque falló)
                        sent_file = artifacts_dir / f"consulta_de_sent_ERROR_{timestamp}.xml"
                        sent_file.write_text(soap_xml_str, encoding="utf-8")
                        
                        # Guardar headers enviados
                        headers_sent_file = artifacts_dir / f"consulta_de_headers_sent_ERROR_{timestamp}.json"
                        import json
                        headers_sent_file.write_text(
                            json.dumps(headers, indent=2, ensure_ascii=False),
                            encoding="utf-8"
                        )
                        
                        # Guardar error
                        error_file = artifacts_dir / f"consulta_de_error_{timestamp}.txt"
                        error_file.write_text(
                            f"Error al consultar DE por CDC:\n{type(e).__name__}: {e}\n",
                            encoding="utf-8"
                        )
                    except Exception:
                        pass
                raise SifenClientError(f"Error al consultar DE por CDC: {e}") from e
        
        # AUTO_EXTRACT_DRUCFactElec: extraer dRUCFactElec del XML crudo
        
        if result.get('raw_xml') and result.get('dRUCFactElec') in (None, ''):
        
            try:
        
                import xml.etree.ElementTree as ET
        
                root = ET.fromstring(result['raw_xml'])
        
                ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
        
                el = root.find('.//s:dRUCFactElec', ns)
        
                if el is not None and el.text is not None:
        
                    result['dRUCFactElec'] = el.text.strip()
        
            except Exception as e:
        
                result.setdefault('warnings', []).append(f"Could not parse dRUCFactElec: {e}")

        
        return result

    # ---------------------------------------------------------------------
    # Context manager
    # ---------------------------------------------------------------------
    def close(self) -> None:
        if (
            hasattr(self, "transport")
            and self.transport
            and hasattr(self.transport, "session")
        ):
            try:
                self.transport.session.close()
            except Exception:
                pass


    
    def send_recibe_lote(self, payload_xml: str, dump_http: bool = False, **kwargs):
        """Envía un lote (siRecepLoteDE) al servicio recibe_lote.
        - payload_xml: puede venir como SOAP completo o como XML "operación" (rEnvioLoteDe).
        - dump_http: si True, guarda artifacts con request/response.
        Retorna dict con http_status, raw_xml y campos parseados (dCodRes, dMsgRes, dProtConsLote, etc).
        """
        import datetime as _dt
        import json
        from pathlib import Path
        import requests
        import lxml.etree as etree
        from copy import deepcopy
        import secrets

        # Generar request_id único para trazabilidad
        request_id = f"{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(2)[:4]}"

        action_value = "siRecepLoteDE"
        # SOAP 1.2 namespace (FIX 0160: SIFEN requiere SOAP 1.2)
        soap_env_ns = "http://www.w3.org/2003/05/soap-envelope"

        # 1) Resolver endpoint real (SOAP address), con fallback
        endpoint = self._resolve_endpoint_with_fallback("recibe_lote")

        # 2) Sesión mTLS (la misma que usa Zeep/Transport si existe)
        session = None
        if hasattr(self, "transport") and self.transport and hasattr(self.transport, "session"):
            session = self.transport.session
        if session is None:
            session = requests.Session()

        # 3) Headers - SOAP 1.2 (application/soap+xml con action en Content-Type, SIN SOAPAction)
        # FIX 0160: Error era por mismatch SOAP 1.1 vs SOAP 1.2
        SOAP_ACTION = "http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE"
        headers = {
            "Accept": "application/soap+xml, text/xml, */*",
            "Content-Type": f'application/soap+xml; charset=utf-8; action="{SOAP_ACTION}"',
            "Connection": "close",
        }
        print(f"🔍 SOAP VERSION: 1.2")
        print(f"🔍 Headers en send_recibe_lote (SOAP 1.2): {headers}")

        # 4) Asegurar SOAP Envelope (si payload_xml viene "pelado")
        payload_xml = (payload_xml or "").strip()
        if not payload_xml:
            raise ValueError("payload_xml vacío")

        try:
            root = etree.fromstring(payload_xml.encode("utf-8"))
        except Exception:
            # si viene con caracteres raros, intentar de todas formas con errors=ignore
            root = etree.fromstring(payload_xml.encode("utf-8", errors="ignore"))

        # Extraer dId y xDE del payload original (buscar por local-name)
        sifen_ns = "http://ekuatia.set.gov.py/sifen/xsd"
        
        def _extract_text(elem, local_name):
            for child in elem.iter():
                if etree.QName(child).localname == local_name:
                    return child.text
            return None
        
        qroot = etree.QName(root)
        
        # Determinar si ya es Envelope o solo la operación
        if qroot.localname == "Envelope":
            # buscar Body y extraer dId/xDE de ahí
            body_elem = root.find(f"{{{soap_env_ns}}}Body")
            if body_elem is not None and len(body_elem):
                op_elem = body_elem[0]
                dId_val = _extract_text(op_elem, "dId")
                xDE_val = _extract_text(op_elem, "xDE")
            else:
                raise ValueError("SOAP Envelope sin Body válido")
        else:
            # root es la operación directa (rEnvioLote o rEnvioLoteDe)
            dId_val = _extract_text(root, "dId")
            xDE_val = _extract_text(root, "xDE")
        
        if not dId_val or not xDE_val:
            raise ValueError(f"No se pudo extraer dId o xDE del payload. dId={dId_val}, xDE={'(presente)' if xDE_val else None}")
        
        # Construir SOAP 1.2 - usar prefijo env para SOAP 1.2 y namespace por defecto para SIFEN (como TIPS)
        # FIX 0160: Usar 'env' como prefijo para SOAP 1.2 (no 'soap') y sin prefijos en body
        env = etree.Element(
            f"{{{soap_env_ns}}}Envelope",
            nsmap={"env": soap_env_ns, None: SIFEN_NS}
        )
        etree.SubElement(env, f"{{{soap_env_ns}}}Header")
        body = etree.SubElement(env, f"{{{soap_env_ns}}}Body")

        envio_root_name = _preferred_envio_root_name()
        # Usar namespace por defecto (sin prefijo) para rEnvioLote (como TIPS)
        r_envio = etree.SubElement(body, envio_root_name)
        dId_elem = etree.SubElement(r_envio, "dId")
        dId_elem.text = dId_val
        xDE_elem = etree.SubElement(r_envio, "xDE")
        xDE_elem.text = xDE_val
        
        # NO usar cleanup_namespaces porque elimina el namespace por defecto
        # etree.cleanup_namespaces(env, top_nsmap={"env": soap_env_ns, None: SIFEN_NS})
        
        # Serializar SOAP (pretty_print opcional para debug)
        pretty_print = os.getenv("SIFEN_SOAP_PRETTY_PRINT", "0") in ("1", "true", "True")
        payload_xml = etree.tostring(env, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print).decode("utf-8")
        # Fix: SIFEN expects double quotes in XML declaration
        payload_xml = payload_xml.replace("<?xml version='1.0' encoding='UTF-8'?>", '<?xml version="1.0" encoding="UTF-8"?>')
        logger.debug(f"SOAP envelope construido con formato sifen: para siRecepLoteDE, dId={dId_val[:20]}...")

        # 6) ANTI-REGRESSION ASSERTIONS
        # Validaciones críticas para evitar 0160
        # FIX 0160: Ahora sin prefijos como TIPS
        assert "<rEnvioLote>" in payload_xml or "<rEnvioLoteDe>" in payload_xml, f"ERROR: payload no contiene 'rEnvioLote' o 'rEnvioLoteDe' - debe usar namespace por defecto"
        assert "<dId>" in payload_xml, f"ERROR: payload no contiene 'dId' - debe usar namespace por defecto"
        assert "<xDE>" in payload_xml, f"ERROR: payload no contiene 'xDE' - debe usar namespace por defecto"
        assert f'xmlns="{SIFEN_NS}"' in payload_xml, f"ERROR: no contiene namespace por defecto SIFEN - debe declarar xmlns"
        # Comentado para permitir SOAP 1.1 (text/xml)
        # assert "application/soap+xml" in headers["Content-Type"], f"ERROR: Content-Type incorrecto: {headers['Content-Type']}"
        
        # Guardar artifacts para debug si falla
        if os.getenv("SIFEN_SAVE_LAST_REQUEST", "1") in ("1", "true", "True"):
            artifacts_dir = Path("artifacts")
            artifacts_dir.mkdir(exist_ok=True)
            with open(artifacts_dir / "soap_last_request_SENT.xml", "w", encoding="utf-8") as f:
                f.write(payload_xml)
            with open(artifacts_dir / "soap_last_headers_SENT.json", "w", encoding="utf-8") as f:
                json.dump(headers, f, indent=2, ensure_ascii=False)
            
            # A/B TEST: Verificar doble wrapper TIPS en xml_file.xml
            if os.getenv("SIFEN_DEBUG_DOUBLE_WRAPPER", "1") in ("1", "true", "True"):
                _verify_double_wrapper_tips(payload_xml, artifacts_dir)

        # 7) POST
        timeout = (getattr(self, "connect_timeout", 10), getattr(self, "read_timeout", 60))
        
        # --- HOTFIX: fuerza prefijo sifen: (estilo TIPS) ---
        if 'xmlns="http://ekuatia.set.gov.py/sifen/xsd"' in payload_xml:
            payload_xml = payload_xml.replace(
                ' xmlns="http://ekuatia.set.gov.py/sifen/xsd"',
                ' xmlns:sifen="http://ekuatia.set.gov.py/sifen/xsd"'
            )
            payload_xml = payload_xml.replace("<rEnvioLote>", "<sifen:rEnvioLote>")
            payload_xml = payload_xml.replace("</rEnvioLote>", "</sifen:rEnvioLote>")
            payload_xml = payload_xml.replace("<dId>", "<sifen:dId>")
            payload_xml = payload_xml.replace("</dId>", "</sifen:dId>")
            payload_xml = payload_xml.replace("<xDE>", "<sifen:xDE>")
            payload_xml = payload_xml.replace("</xDE>", "</sifen:xDE>")
        # --- END HOTFIX ---
        
        resp = session.post(
            endpoint,
            data=payload_xml.encode("utf-8"),
            headers=headers,
            timeout=timeout,
        )

        raw_xml = resp.text or ""
        result = {
            "request_id": request_id,  # Agregar request_id para trazabilidad
            "endpoint": endpoint,
            "http_status": resp.status_code,
            "raw_xml": raw_xml,
            "sent_headers": headers if dump_http else None,
            "sent_xml": payload_xml if dump_http else None,
        }

        # 7) Parse mínimo de campos típicos de SIFEN (usar XPath real, no .find con local-name())
        def _find_text_xpath(xml_root, local_name: str) -> str:
            try:
                v = xml_root.xpath("string(//*[local-name()=$n][1])", n=local_name)
                return (v or "").strip()
            except Exception:
                return ""

        try:
            root_resp = etree.fromstring((raw_xml or "").encode("utf-8"))
            dCodRes = _find_text_xpath(root_resp, "dCodRes")
            dMsgRes = _find_text_xpath(root_resp, "dMsgRes")
            dEstRes = _find_text_xpath(root_resp, "dEstRes")
            dProtConsLote = _find_text_xpath(root_resp, "dProtConsLote") or _find_text_xpath(root_resp, "dProtConsLoteDE")
            dId = _find_text_xpath(root_resp, "dId")

            result.update({
                "dCodRes": dCodRes,
                "dMsgRes": dMsgRes,
                "dEstRes": dEstRes,
                "dProtConsLote": dProtConsLote,
                "dId": dId,
            })

            ok_codes = {"0000", "0502"}
            result["ok"] = (resp.status_code in (200, 500) and (dCodRes in ok_codes or (dEstRes.upper().startswith("ACEP") if dEstRes else False)))
        except Exception as e:
            result["ok"] = False
            result["parse_error"] = f"{type(e).__name__}: {e}"

        # 8) Artifacts si dump_http
        if dump_http:
            artifacts_dir = Path("artifacts")
            artifacts_dir.mkdir(exist_ok=True)
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")

            # mantener nombres esperados por tools/send_sirecepde.py
            (artifacts_dir / "soap_last_request_SENT.xml").write_text(payload_xml, encoding="utf-8")
            (artifacts_dir / "soap_last_response_RECV.xml").write_text(raw_xml, encoding="utf-8")

            # Guardar con request_id para trazabilidad única
            (artifacts_dir / f"recibe_lote_REQ_{request_id}.xml").write_text(payload_xml, encoding="utf-8")
            (artifacts_dir / f"recibe_lote_REQ_{request_id}_headers.json").write_text(json.dumps(headers, indent=2, ensure_ascii=False), encoding="utf-8")
            (artifacts_dir / f"recibe_lote_RESP_{request_id}.xml").write_text(raw_xml, encoding="utf-8")
            
            # Meta con request_id
            meta = {
                "request_id": request_id,
                "endpoint": endpoint,
                "http_status": resp.status_code,
                "timestamp": ts,
                "headers": dict(resp.headers) if dump_http else None
            }
            (artifacts_dir / f"recibe_lote_RESP_{request_id}_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

            # Mantener compatibilidad con nombres antiguos
            (artifacts_dir / f"recibe_lote_sent_{ts}.xml").write_text(payload_xml, encoding="utf-8")
            (artifacts_dir / f"recibe_lote_headers_{ts}.json").write_text(json.dumps(headers, indent=2, ensure_ascii=False), encoding="utf-8")
            (artifacts_dir / f"recibe_lote_raw_{ts}.xml").write_text(raw_xml, encoding="utf-8")
            result_with_request_id = result.copy()
            result_with_request_id["request_id"] = request_id
            (artifacts_dir / f"recibe_lote_result_{ts}.json").write_text(json.dumps({k: v for k, v in result_with_request_id.items() if v is not None}, indent=2, ensure_ascii=False), encoding="utf-8")

        if not dump_http:
            result.pop("sent_headers", None)
            result.pop("sent_xml", None)

        return result


    def recepcion_lote(self, payload_xml, dump_http=False, **kwargs):
        """Alias compat: algunas CLIs llaman `recepcion_lote`, pero la implementación real puede llamarse distinto.
        Intenta delegar a métodos conocidos si existen.
        """
        candidates = (
            "send_recibe_lote",
        )

        last_err = None
        for name in candidates:
            fn = getattr(self, name, None)
            if not callable(fn):
                continue
            try:
                return fn(payload_xml, dump_http=dump_http, **kwargs)
            except TypeError as e:
                last_err = e
                try:
                    return fn(payload_xml, dump_http=dump_http)
                except TypeError as e2:
                    last_err = e2
                    try:
                        return fn(payload_xml)
                    except Exception as e3:
                        last_err = e3
                        continue

        # Si llegamos acá, no hay implementación compatible disponible.
        msg = "SoapClient no expone un método para enviar lote (busqué: %s)." % ", ".join(candidates)
        if last_err:
            msg += f" Último error: {last_err!r}"
        raise AttributeError(msg)


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
