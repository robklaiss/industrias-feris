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
import logging
from typing import Dict, Any, Optional, TYPE_CHECKING
from pathlib import Path
from urllib.parse import urlparse, urlunparse

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

from .config import SifenConfig, get_mtls_cert_path_and_password
from .exceptions import (
    SifenClientError,
    SifenSizeLimitError,
)
from .pkcs12_utils import p12_to_temp_pem_files, cleanup_pem_files, PKCS12Error

logger = logging.getLogger(__name__)

# Constantes de namespace SIFEN
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"
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


class SoapClient:
    """Cliente SOAP 1.2 (document/literal) para SIFEN, con mTLS."""

    def __init__(self, config: SifenConfig):
        self.config = config

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

        # Transporte con mTLS
        self.transport = self._create_transport()

        # Cache
        self.clients: Dict[str, Any] = {}  # Client de Zeep
        self._soap_address: Dict[str, str] = {}

        # PEM temporales (si se convierten desde P12)
        self._temp_pem_files: Optional[tuple[str, str]] = None

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

    def _extract_soap_address_from_wsdl(self, wsdl_url: str) -> Optional[str]:
        """Parsea el SOAP address (location) desde el XML del WSDL.

        Normaliza el WSDL URL y el endpoint resultante.
        """
        try:
            import lxml.etree as etree  # noqa: F401

            # Normalizar WSDL URL antes del GET
            wsdl_url_final = self._normalize_wsdl_url(wsdl_url)
            logger.debug(f"WSDL URL normalizada: {wsdl_url} -> {wsdl_url_final}")

            session = (
                self.transport.session if hasattr(self, "transport") else Session()
            )
            resp = session.get(
                wsdl_url_final, timeout=(self.connect_timeout, self.read_timeout)
            )

            logger.debug(
                f"WSDL GET: status={resp.status_code}, len={len(resp.content or b'')}"
            )

            if resp.status_code != 200 or not resp.content:
                logger.warning(
                    f"WSDL vacío o error HTTP al obtener WSDL: {wsdl_url_final} "
                    f"(status={resp.status_code}, len={len(resp.content or b'')})"
                )
                return None

            wsdl_xml = etree.fromstring(resp.content)

            ns = {
                "wsdl": "http://schemas.xmlsoap.org/wsdl/",
                "soap12": "http://schemas.xmlsoap.org/wsdl/soap12/",
                "soap": "http://schemas.xmlsoap.org/wsdl/soap/",
            }

            location_raw = None
            # Preferir soap12:address
            addr = wsdl_xml.find(".//soap12:address", namespaces=ns)
            if addr is not None:
                location_raw = addr.get("location")
            else:
                # Fallback a soap:address
                addr = wsdl_xml.find(".//soap:address", namespaces=ns)
                if addr is not None:
                    location_raw = addr.get("location")

            if location_raw:
                # En modo Roshka, NO normalizar el endpoint (usar exacto del WSDL)
                if self.roshka_compat:
                    logger.debug(
                        f"SOAP endpoint extraído (Roshka compat, sin normalizar): "
                        f"{location_raw}"
                    )
                    return location_raw
                else:
                    endpoint_normalized = self._normalize_soap_endpoint(location_raw)
                    logger.debug(
                        f"SOAP endpoint extraído: location_raw={location_raw}, "
                        f"endpoint_normalized={endpoint_normalized}"
                    )
                    return endpoint_normalized

            return None
        except Exception as e:
            logger.debug(
                f"No se pudo extraer SOAP address desde WSDL ({wsdl_url}): {e}"
            )
            return None

    # ---------------------------------------------------------------------
    # Transport (mTLS)
    # ---------------------------------------------------------------------
    def _create_transport(self) -> Any:  # Transport de Zeep
        """Crea el transporte Zeep con requests.Session configurada para mTLS."""
        session = Session()

        # Modo 1: PEM directo (prioridad)
        pem_cert = getattr(self.config, "cert_pem_path", None) or os.getenv(
            "SIFEN_CERT_PEM_PATH"
        )
        pem_key = getattr(self.config, "key_pem_path", None) or os.getenv(
            "SIFEN_KEY_PEM_PATH"
        )

        if pem_cert and pem_key:
            cert_path = Path(pem_cert)
            key_path = Path(pem_key)
            if not cert_path.exists():
                raise SifenClientError(f"Certificado PEM no encontrado: {cert_path}")
            if not key_path.exists():
                raise SifenClientError(f"Clave privada PEM no encontrada: {key_path}")

            session.cert = (str(cert_path), str(key_path))
            self._temp_pem_files = None
            logger.info(
                f"Usando mTLS via PEM: cert={cert_path.name}, key={key_path.name}"
            )

        else:
            # Modo 2: PKCS12 (fallback) - usar helper para mTLS
            resolved_cert_path, resolved_cert_password = get_mtls_cert_path_and_password()
            
            # Fallback a config si no hay env vars
            if not resolved_cert_path:
                resolved_cert_path = getattr(self.config, "cert_path", None)
            if not resolved_cert_password:
                resolved_cert_password = getattr(self.config, "cert_password", None)

            missing = []
            if not resolved_cert_path:
                missing.append("SIFEN_MTLS_P12_PATH o SIFEN_CERT_PATH")
            if not resolved_cert_password:
                missing.append("SIFEN_MTLS_P12_PASSWORD o SIFEN_CERT_PASSWORD")

            if missing:
                raise SifenClientError(
                    "mTLS es requerido para SIFEN. Falta: "
                    + ", ".join(missing)
                    + ". Opciones: 1) export SIFEN_CERT_PEM_PATH=... "
                    "y SIFEN_KEY_PEM_PATH=... "
                    "2) export SIFEN_MTLS_P12_PATH=/ruta/al/certificado.p12 "
                    "y SIFEN_MTLS_P12_PASSWORD=..."
                )

            # resolved_cert_path está garantizado como no-None
            # por la validación anterior
            assert resolved_cert_path is not None
            cert_path = Path(resolved_cert_path)
            if not cert_path.exists():
                raise SifenClientError(f"Certificado no encontrado: {cert_path}")

            ext = cert_path.suffix.lower()
            is_p12 = ext in (".p12", ".pfx")

            if is_p12:
                try:
                    cert_pem_path, key_pem_path = p12_to_temp_pem_files(
                        str(cert_path), resolved_cert_password or ""
                    )
                    self._temp_pem_files = (cert_pem_path, key_pem_path)
                    session.cert = (cert_pem_path, key_pem_path)
                    
                    # Debug: guardar paths si está habilitado
                    debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
                    if debug_enabled:
                        logger.info(
                            f"mTLS: Certificado P12 convertido a PEM temporales: "
                            f"cert={cert_pem_path}, key={key_pem_path}"
                        )
                    else:
                        logger.info(
                            f"Certificado P12 convertido a PEM temporales para mTLS: "
                            f"{Path(cert_pem_path).name}, {Path(key_pem_path).name}"
                        )
                except PKCS12Error as e:
                    raise SifenClientError(
                        f"Error al convertir certificado P12 a PEM: {e}"
                    ) from e
                except Exception as e:
                    raise SifenClientError(
                        f"Error inesperado al procesar certificado: {e}"
                    ) from e
            else:
                session.cert = str(cert_path)
                logger.info(f"Usando certificado en formato: {ext}")

        # SSL verify
        session.verify = True
        ca_bundle_path = getattr(self.config, "ca_bundle_path", None)
        if ca_bundle_path:
            session.verify = ca_bundle_path

        session.mount("https://", HTTPAdapter())

        # Transport está disponible porque ZEEP_AVAILABLE es True (verificado en __init__)
        # timeout puede ser int o tuple (connect, read) según requests/zeep
        return Transport(  # type: ignore[arg-type]
            session=session,
            timeout=(self.connect_timeout, self.read_timeout),  # type: ignore[arg-type]
            operation_timeout=self.read_timeout,
        )

    # ---------------------------------------------------------------------
    # Zeep client (solo para WSDL/address)
    # ---------------------------------------------------------------------
    def _get_client(self, service_key: str) -> Any:  # Client de Zeep
        if service_key in self.clients:
            return self.clients[service_key]

        wsdl_url = self.config.get_soap_service_url(service_key)
        wsdl_url_final = self._normalize_wsdl_url(wsdl_url)

        logger.info(f"Cargando WSDL para servicio '{service_key}': {wsdl_url_final}")

        try:
            plugins = []
            debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")

            if debug_enabled:
                from zeep.plugins import HistoryPlugin

                history = HistoryPlugin()
                plugins.append(history)
                if not hasattr(self, "_history_plugins"):
                    self._history_plugins = {}
                self._history_plugins[service_key] = history

            # Client y Settings están disponibles porque ZEEP_AVAILABLE es True (verificado en __init__)
            client = Client(  # type: ignore
                wsdl=wsdl_url_final,
                transport=self.transport,
                settings=Settings(strict=False, xml_huge_tree=True),  # type: ignore
                plugins=plugins or None,
            )
            self.clients[service_key] = client

            # Extraer SOAP address desde zeep (si se puede)
            try:
                addr = None
                if hasattr(client.service, "_binding_options"):
                    addr = client.service._binding_options.get("address")
                if not addr:
                    for service in client.wsdl.services.values():
                        for port in service.ports.values():
                            if hasattr(port, "binding") and hasattr(
                                port.binding, "options"
                            ):
                                addr = port.binding.options.get("address")
                                if addr:
                                    break
                        if addr:
                            break
                if addr:
                    # En modo Roshka, NO normalizar el endpoint
                    if self.roshka_compat:
                        self._soap_address[service_key] = addr
                        logger.info(
                            f"SOAP address para '{service_key}' (desde Zeep, Roshka compat): {addr}"
                        )
                    else:
                        addr_normalized = self._normalize_soap_endpoint(addr)
                        self._soap_address[service_key] = addr_normalized
                        logger.info(
                            f"SOAP address para '{service_key}' (desde Zeep): {addr} -> {addr_normalized}"
                        )
            except Exception as e:
                logger.debug(f"No se pudo leer SOAP address desde Zeep: {e}")

            # Fallback: parsear WSDL (por si zeep no lo expone)
            if service_key not in self._soap_address:
                addr = self._extract_soap_address_from_wsdl(wsdl_url_final)
                if addr:
                    self._soap_address[service_key] = addr
                    logger.info(
                        f"SOAP address para '{service_key}' (desde WSDL): {addr}"
                    )

            return client

        except Exception as e:
            raise SifenClientError(
                f"Error al crear cliente SOAP para {service_key}: {e}"
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
    # XML namespace normalization (para DE) - usa namespace DEFAULT sin prefijos
    # ---------------------------------------------------------------------
    def _clone_de_to_sifen_default_ns(self, de_original: Any) -> Any:
        """Clona el DE para que TODOS los elementos SIFEN estén en namespace default (sin prefijo).

        Reglas CRÍTICAS:
        - Root DE: <DE xmlns="http://ekuatia.set.gov.py/sifen/xsd" xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        - TODOS los elementos SIFEN (incluyendo los que venían sin namespace) deben quedar en SIFEN_NS
        - NUNCA crear elementos sin namespace (etree.Element(local_name)) para elementos que deben ser SIFEN
        - Los elementos de firma (DS_NS) mantienen prefijo ds:
        - Esto evita que lxml inserte xmlns="" (que causa error "Prefijo [null] no reconocido")
        """
        import lxml.etree as etree  # noqa: F401

        def split_tag(tag: str) -> tuple[Optional[str], str]:
            if "}" in tag and tag.startswith("{"):
                ns, local = tag[1:].split("}", 1)
                return ns, local
            return None, tag

        def clone(node: Any, is_root: bool = False) -> Any:
            node_ns, local = split_tag(node.tag)

            # Regla CRÍTICA: si viene sin namespace (None), TRATARLO COMO SIFEN_NS
            # Esto evita que queden elementos en namespace None que generen xmlns=""
            if node_ns is None:
                node_ns = SIFEN_NS

            # Crear elemento según su namespace
            if node_ns == SIFEN_NS:
                # Elementos SIFEN: usar namespace DEFAULT (sin prefijo)
                if is_root:
                    # Root DE: declarar namespace default SIFEN y prefijo ds para firma
                    nsmap = {None: SIFEN_NS, "ds": DS_NS}
                    new_elem = etree.Element(f"{{{SIFEN_NS}}}{local}", nsmap=nsmap)
                else:
                    # Elementos hijos SIFEN: usar namespace SIFEN sin prefijo (heredan xmlns default)
                    # IMPORTANTE: siempre usar {SIFEN_NS}local, NUNCA solo local
                    new_elem = etree.Element(f"{{{SIFEN_NS}}}{local}")
            elif node_ns == DS_NS:
                # Elementos de firma: usar prefijo ds:
                new_elem = etree.Element(f"{{{DS_NS}}}{local}")
            else:
                # Otros namespaces: preservar (pero asegurar que no sea None)
                if node_ns:
                    new_elem = etree.Element(f"{{{node_ns}}}{local}")
                else:
                    # Fallback: si por alguna razón node_ns sigue siendo None, tratarlo como SIFEN
                    new_elem = etree.Element(f"{{{SIFEN_NS}}}{local}")

            # Copiar atributos (preservar namespaces en atributos si los tienen)
            for attr_name, attr_value in node.attrib.items():
                new_elem.set(attr_name, attr_value)

            # Copiar texto y tail
            if node.text:
                new_elem.text = node.text
            if node.tail:
                new_elem.tail = node.tail

            # Copiar hijos recursivamente
            for child in node:
                if isinstance(child, etree._Element):
                    cloned_child = clone(child, is_root=False)
                    new_elem.append(cloned_child)

            return new_elem

        return clone(de_original, is_root=True)

    def _extract_r_envi_de_substring(self, xml_sirecepde: str) -> bytes:
        """Extrae el rEnviDe original preservando namespaces y firma.

        Si no se puede extraer substring exacto, usa parse+serialize preservando estructura.
        """
        import lxml.etree as etree  # noqa: F401

        # Remover XML declaration si existe
        xml_clean = xml_sirecepde.strip()
        if xml_clean.startswith("<?xml"):
            end_decl = xml_clean.find("?>")
            if end_decl != -1:
                xml_clean = xml_clean[end_decl + 2 :].strip()

        # Intentar extraer substring exacto primero
        try:
            import re

            # Buscar <rEnviDe (puede tener prefijo o namespace)
            match = re.search(r"<[^>]*rEnviDe[^>]*>", xml_clean, re.IGNORECASE)
            if match:
                start_pos = match.start()
                # Buscar el cierre balanceado (método simple: contar tags)
                # Esto es aproximado pero funciona para la mayoría de casos
                depth = 0
                i = start_pos
                while i < len(xml_clean):
                    if xml_clean[i : i + 2] == "</":
                        # Buscar si es </rEnviDe
                        tag_end = xml_clean.find(">", i)
                        if tag_end != -1:
                            closing_tag = xml_clean[i + 2 : tag_end].strip()
                            if "rEnviDe" in closing_tag:
                                depth -= 1
                                if depth == 0:
                                    end_pos = tag_end + 1
                                    substring = xml_clean[start_pos:end_pos]
                                    # Validar que es XML válido
                                    etree.fromstring(substring.encode("utf-8"))
                                    return substring.encode("utf-8")
                    elif xml_clean[i] == "<" and xml_clean[i + 1] != "/":
                        # Opening tag
                        tag_end = xml_clean.find(">", i)
                        if tag_end != -1:
                            opening_tag = xml_clean[i : tag_end + 1]
                            if "rEnviDe" in opening_tag:
                                depth += 1
                            i = tag_end + 1
                            continue
                    i += 1
        except Exception as e:
            logger.debug(
                f"No se pudo extraer substring exacto, usando parse+serialize: {e}"
            )

        # Fallback: parsear y serializar preservando estructura
        try:
            root = etree.fromstring(xml_clean.encode("utf-8"))
            # Serializar solo el root (rEnviDe) sin declaration, preservando namespaces
            r_envi_de_bytes = etree.tostring(
                root,
                xml_declaration=False,
                encoding="UTF-8",
                pretty_print=False,
                method="xml",
            )
            return r_envi_de_bytes
        except Exception as e:
            raise SifenClientError(f"Error al extraer rEnviDe del XML: {e}")

    def _ensure_rde_wrapper(self, xml_root: Any) -> Any:
        """Asegura que xDE contenga rDE como wrapper de DE.

        Si xDE tiene un hijo directo <DE> (sin rDE), crea <rDE> con:
        - Namespace SIFEN como default (sin prefijo)
        - xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        - xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd"
        - Mueve el <DE> dentro de <rDE>

        Si ya existe <rDE>, no hace nada.

        Args:
            xml_root: Elemento rEnviDe parseado (etree._Element)

        Returns:
            El mismo xml_root modificado (o sin cambios si ya tenía rDE)

        Validación:
            # Limpiar artifacts anteriores
            rm -f artifacts/soap_last_sent*.xml artifacts/soap_last_received*.xml

            # Enviar SOAP con modo Roshka
            SIFEN_DEBUG_SOAP=1 SIFEN_SOAP_COMPAT=roshka python -u -m tools.send_sirecepde --env test --xml latest

            # Verificar que xDE contiene rDE
            grep -n "<xDE><rDE" artifacts/soap_last_sent.xml

            # El error debería cambiar (idealmente dejar de ser 0100/0160)
        """
        import lxml.etree as etree  # noqa: F401

        def get_local_name(tag: str) -> str:
            """Extrae el nombre local de un tag (sin namespace)."""
            if "}" in tag and tag.startswith("{"):
                return tag.split("}")[1]
            return tag

        def get_namespace(tag: str) -> Optional[str]:
            """Extrae el namespace de un tag."""
            if "}" in tag and tag.startswith("{"):
                return tag.split("}")[0][1:]
            return None

        # Buscar xDE dentro de rEnviDe
        x_de = None
        for child in xml_root:
            if get_local_name(child.tag) == "xDE":
                x_de = child
                break

        if x_de is None:
            logger.warning(
                "No se encontró xDE en rEnviDe, no se puede agregar rDE wrapper"
            )
            return xml_root

        # Verificar si ya tiene rDE
        has_rde = False
        for child in x_de:
            if get_local_name(child.tag) == "rDE":
                has_rde = True
                break

        if has_rde:
            logger.debug("xDE ya contiene rDE, no se modifica")
            return xml_root

        # Buscar DE dentro de xDE
        de_elem = None
        for child in x_de:
            if get_local_name(child.tag) == "DE":
                de_elem = child
                break

        if de_elem is None:
            logger.warning("No se encontró DE en xDE, no se puede agregar rDE wrapper")
            return xml_root

        # Crear rDE con namespace default SIFEN
        # nsmap: None -> SIFEN_NS (default), "xsi" -> XSI_NS
        r_de = etree.Element(
            f"{{{SIFEN_NS}}}rDE", nsmap={None: SIFEN_NS, "xsi": XSI_NS}
        )

        # Agregar xsi:schemaLocation (debe estar en namespace XSI)
        r_de.set(f"{{{XSI_NS}}}schemaLocation", SIFEN_SCHEMA_LOCATION)

        # Mover DE dentro de rDE (esto preserva todo el contenido, incluyendo ds:Signature)
        r_de.append(de_elem)

        # Reemplazar contenido de xDE con rDE
        # Primero limpiar xDE
        x_de.clear()
        # Luego agregar rDE
        x_de.append(r_de)

        logger.info("Agregado wrapper rDE alrededor de DE en xDE")
        return xml_root

    def _build_raw_envelope_with_original_content(
        self, r_envi_de_bytes: bytes, action: Optional[str] = None
    ) -> bytes:
        """Construye SOAP 1.2 envelope embebiendo el rEnviDe original sin modificar.

        Esto preserva namespaces, prefijos y firma digital intactos.
        
        Args:
            r_envi_de_bytes: XML bytes a embeder (rEnviDe, rEnvioLote, rEnviConsLoteDe, etc.)
            action: Acción SOAP (opcional, para headers)
        """
        import lxml.etree as etree  # noqa: F401

        # Envelope SOAP 1.2
        envelope = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap={"soap-env": SOAP_NS})
        body = etree.SubElement(envelope, f"{{{SOAP_NS}}}Body")

        # Parsear el rEnviDe original y embederlo directamente (sin modificar)
        # Esto preserva namespaces y estructura original
        r_envi_de_elem = etree.fromstring(r_envi_de_bytes)
        body.append(r_envi_de_elem)

        # Serializar
        return etree.tostring(
            envelope, xml_declaration=True, encoding="UTF-8", pretty_print=False
        )

    # ---------------------------------------------------------------------
    # SOAP Helpers
    # ---------------------------------------------------------------------
    def _soap_headers(self, version: str, action: str) -> dict:
        """
        Genera headers HTTP según versión SOAP.
        
        Args:
            version: "1.2" o "1.1"
            action: Nombre de la acción SOAP (ej: "siRecepLoteDE")
            
        Returns:
            Dict con headers HTTP
        """
        if version == "1.2":
            return {
                "Content-Type": f'application/soap+xml; charset=utf-8; action="{action}"',
                "Accept": "application/soap+xml, text/xml, */*",
            }
        elif version == "1.1":
            return {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{action}"',
                "Accept": "text/xml, */*",
            }
        else:
            raise ValueError(f"Versión SOAP no soportada: {version}")

    def _wrap_body(self, payload_xml: bytes, wrapper: bool, action: str, ns: str) -> bytes:
        """
        Envuelve el payload XML en un Body SOAP, opcionalmente con wrapper de operación.
        
        Args:
            payload_xml: XML del payload (ej: <rEnvioLote>...</rEnvioLote>)
            wrapper: Si True, envuelve en <action>...</action>
            action: Nombre de la acción (ej: "siRecepLoteDE")
            ns: Namespace para el wrapper (ej: SIFEN_NS)
            
        Returns:
            Bytes del Body SOAP
        """
        if etree is None:
            raise SifenClientError("lxml.etree no está disponible")
        
        if wrapper:
            # Crear wrapper <action xmlns="ns"> + payload + </action>
            wrapper_elem = etree.Element(etree.QName(ns, action), nsmap={None: ns})  # type: ignore
            payload_root = etree.fromstring(payload_xml)  # type: ignore
            wrapper_elem.append(payload_root)
            return etree.tostring(wrapper_elem, xml_declaration=False, encoding="UTF-8")  # type: ignore
        else:
            # Retornar payload directo
            return payload_xml

    def _build_soap_envelope(
        self,
        body_content: bytes,
        version: str,
        header_msg_did: Optional[str] = None,
    ) -> bytes:
        """
        Construye un envelope SOAP 1.1 o 1.2.
        
        Args:
            body_content: Contenido del Body (ya envuelto si corresponde)
            version: "1.2" o "1.1"
            header_msg_did: dId para HeaderMsg (opcional)
            
        Returns:
            Bytes del envelope SOAP completo
        """
        if etree is None:
            raise SifenClientError("lxml.etree no está disponible")
        
        if version == "1.2":
            envelope_ns = "http://www.w3.org/2003/05/soap-envelope"
            prefix = "soap-env"
        elif version == "1.1":
            envelope_ns = "http://schemas.xmlsoap.org/soap/envelope/"
            prefix = "soap"
        else:
            raise ValueError(f"Versión SOAP no soportada: {version}")

        envelope = etree.Element(f"{{{envelope_ns}}}Envelope", nsmap={prefix: envelope_ns})  # type: ignore
        
        # Header (si hay HeaderMsg)
        if header_msg_did is not None:
            header = etree.SubElement(envelope, f"{{{envelope_ns}}}Header")  # type: ignore
            header_msg = etree.SubElement(  # type: ignore
                header, f"{{{SIFEN_NS}}}HeaderMsg", nsmap={None: SIFEN_NS}
            )
            header_d_id = etree.SubElement(header_msg, f"{{{SIFEN_NS}}}dId")  # type: ignore
            header_d_id.text = str(header_msg_did)
        else:
            # Header vacío para SOAP 1.2
            if version == "1.2":
                header = etree.SubElement(envelope, f"{{{envelope_ns}}}Header")  # type: ignore
        
        # Body
        body = etree.SubElement(envelope, f"{{{envelope_ns}}}Body")  # type: ignore
        body_root = etree.fromstring(body_content)  # type: ignore
        body.append(body_root)
        
        return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8", pretty_print=False)  # type: ignore

    def _save_http_debug(
        self,
        post_url: str,
        original_url: str,
        version: str,
        action: str,
        headers: dict,
        soap_bytes: bytes,
        response_status: Optional[int] = None,
        response_headers: Optional[dict] = None,
        response_body: Optional[bytes] = None,
        mtls_cert_path: Optional[str] = None,
        mtls_key_path: Optional[str] = None,
    ):
        """
        Guarda debug completo de un intento HTTP/SOAP.
        """
        import hashlib
        
        debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
        if not debug_enabled and response_status == 200:
            return  # Solo guardar en error si no está habilitado
        
        try:
            debug_file = Path("artifacts") / "soap_last_http_debug.txt"
            debug_file.parent.mkdir(exist_ok=True)
            
            soap_sha256 = hashlib.sha256(soap_bytes).hexdigest()
            soap_str = soap_bytes.decode("utf-8", errors="replace")
            
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(f"POST_URL={post_url}\n")
                f.write(f"ORIGINAL_URL={original_url}\n")
                f.write(f"VERSION={version}\n")
                f.write(f"ACTION={action}\n")
                f.write(f"HEADERS={headers}\n")
                if mtls_cert_path:
                    f.write(f"MTLS_CERT={mtls_cert_path}\n")
                if mtls_key_path:
                    f.write(f"MTLS_KEY={mtls_key_path}\n")
                f.write(f"SOAP_BYTES_SHA256={soap_sha256}\n")
                f.write(f"SOAP_BYTES_LEN={len(soap_bytes)}\n")
                f.write("---- SOAP BEGIN ----\n")
                f.write(soap_str)
                f.write("\n---- SOAP END ----\n")
                
                if response_status is not None:
                    f.write(f"RESPONSE_STATUS={response_status}\n")
                if response_headers:
                    f.write(f"RESPONSE_HEADERS={response_headers}\n")
                if response_body:
                    body_str = response_body.decode("utf-8", errors="replace")
                    f.write(f"RESPONSE_BODY_FIRST_2000={body_str[:2000]}\n")
            
            logger.debug(f"HTTP debug guardado en: {debug_file}")
        except Exception as e:
            logger.warning(f"Error al guardar HTTP debug: {e}")

    # ---------------------------------------------------------------------
    # RAW POST (requests)
    # ---------------------------------------------------------------------
    def _post_raw_soap(self, service_key: str, soap_bytes: bytes) -> bytes:
        if service_key not in self._soap_address:
            self._get_client(service_key)  # intenta poblar _soap_address

        if service_key not in self._soap_address:
            wsdl_url = self._normalize_wsdl_url(
                self.config.get_soap_service_url(service_key)
            )
            addr = self._extract_soap_address_from_wsdl(wsdl_url)
            if addr:
                self._soap_address[service_key] = addr

        if service_key not in self._soap_address:
            raise SifenClientError(
                f"No se encontró SOAP address para servicio '{service_key}'. Verifique que el WSDL se cargó correctamente."
            )

        url = self._soap_address[service_key]
        logger.info(f"Enviando SOAP a endpoint: {url}")
        session = self.transport.session

        # Headers según modo de compatibilidad
        if self.roshka_compat:
            # Roshka usa: application/xml; charset=utf-8 (sin action, sin SOAPAction)
            headers = {
                "Content-Type": "application/xml; charset=utf-8",
            }
        else:
            # Headers SOAP 1.2 estándar: action va en Content-Type
            # Determinar la acción según el servicio
            if service_key == "recibe_lote":
                action = "rEnvioLote"
            elif service_key == "consulta_lote":
                action = "siConsLoteDE"
            else:
                action = "rEnviDe"  # default para "recibe"
            headers = {
                "Content-Type": f'application/soap+xml; charset=utf-8; action="{action}"',
            }

        resp = session.post(
            url,
            data=soap_bytes,
            headers=headers,
            timeout=(self.connect_timeout, self.read_timeout),
        )
        if resp.status_code != 200:
            raise SifenClientError(
                f"Error HTTP {resp.status_code} al enviar SOAP: {resp.text[:500]}"
            )
        return resp.content

    def _save_raw_soap_debug(
        self,
        soap_bytes: bytes,
        response_bytes: Optional[bytes] = None,
        suffix: str = "",
    ):
        """
        Guarda SOAP RAW enviado/recibido para debugging.

        IMPORTANTE: Este método NUNCA debe romper el flujo principal.
        Si falla algo en el debug, se loguea warning y se continúa.
        """
        debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
        if not debug_enabled:
            return

        try:
            from pathlib import Path

            out_dir = Path("artifacts")
            out_dir.mkdir(exist_ok=True)

            # Guardar SOAP enviado
            sent_file = out_dir / f"soap_last_sent{suffix}.xml"
            sent_file.write_bytes(soap_bytes)
            logger.debug(f"SOAP RAW enviado guardado en: {sent_file}")

            # Guardar respuesta si existe
            if response_bytes is not None:
                received_file = out_dir / f"soap_last_received{suffix}.xml"
                received_file.write_bytes(response_bytes)
                logger.debug(f"SOAP RAW recibido guardado en: {received_file}")

            # Validaciones ligeras (NO deben lanzar excepciones)
            try:
                soap_str = soap_bytes.decode("utf-8", errors="replace")

                # 1) xmlns="" es CRÍTICO: causa error "Prefijo [null] no reconocido"
                if 'xmlns=""' in soap_str:
                    logger.warning(
                        "DEBUG SOAP: CRÍTICO - Se detectó 'xmlns=\"\"' en el SOAP enviado. "
                        "Esto causa error 'Prefijo [null] no reconocido' en SIFEN."
                    )

                # 2) ns0 no permitido (validación simple con 'in', no regex)
                if "ns0:" in soap_str:
                    logger.warning(
                        "DEBUG SOAP: Se detectó prefijo 'ns0:' en el SOAP enviado (no permitido)."
                    )

                # 3) xsns no permitido (ya no usamos prefijos)
                if "<xsns:" in soap_str:
                    logger.warning(
                        "DEBUG SOAP: Se detectó prefijo 'xsns:' en el SOAP enviado (no permitido)."
                    )

                # 4) Detectar namespaces raros (helper interno)
                self._debug_detect_rare_namespaces(soap_bytes)

            except Exception as e:
                logger.warning(f"DEBUG SOAP: validación interna falló (ignorado): {e}")

        except Exception as e:
            logger.warning(f"No se pudo guardar SOAP RAW para debug (ignorado): {e}")

    def _debug_detect_rare_namespaces(self, soap_bytes: bytes) -> None:
        """Helper para detectar namespaces raros en el SOAP (solo logs, no excepciones)."""
        try:
            import lxml.etree as etree  # noqa: F401

            # Parsear el SOAP
            root = etree.fromstring(soap_bytes)

            # Namespaces esperados
            expected_ns = {SOAP_NS, SIFEN_NS, DS_NS}

            # Recopilar elementos con namespaces raros
            rare_elements = []
            for elem in root.iter():
                if hasattr(elem, "tag"):
                    tag = elem.tag
                    if "}" in tag:
                        ns = tag.split("}")[0][1:]  # Extraer namespace
                        local = tag.split("}")[1]
                        if ns not in expected_ns:
                            rare_elements.append((local, ns))
                            if len(rare_elements) >= 20:
                                break

            # Loggear si hay namespaces raros
            if rare_elements:
                unique_rare = list(set(rare_elements))[:20]
                logger.warning(
                    f"DEBUG SOAP: Se detectaron elementos con namespaces no esperados "
                    f"(primeros {len(unique_rare)}): {unique_rare}"
                )

        except Exception as e:
            # NUNCA lanzar excepción desde debug
            logger.debug(f"DEBUG SOAP: No se pudo analizar namespaces (ignorado): {e}")

    # ---------------------------------------------------------------------
    # Parsing de respuesta (XML)
    # ---------------------------------------------------------------------
    def _parse_recepcion_response_from_xml(self, xml_root: Any) -> Dict[str, Any]:
        import lxml.etree as etree  # noqa: F401

        result = {
            "ok": False,
            "codigo_estado": None,
            "codigo_respuesta": None,
            "mensaje": None,
            "cdc": None,
            "estado": None,
            "raw_response": None,
            "parsed_fields": {},
        }

        def find_text(xpath_expr: str) -> Optional[str]:
            try:
                nodes = xml_root.xpath(xpath_expr)
                if nodes:
                    val = nodes[0].text
                    return val.strip() if val else None
            except Exception:
                return None
            return None

        # Busca por local-name para tolerar prefijos
        result["codigo_respuesta"] = find_text('//*[local-name()="dCodRes"]')
        result["mensaje"] = find_text('//*[local-name()="dMsgRes"]')
        result["estado"] = find_text('//*[local-name()="dEstRes"]')
        result["cdc"] = find_text('//*[local-name()="Id"]') or find_text(
            '//*[local-name()="cdc"]'
        )
        # Para respuestas de lote, extraer también dProtConsLote
        result["d_prot_cons_lote"] = find_text('//*[local-name()="dProtConsLote"]')

        result["parsed_fields"] = {"xml": etree.tostring(xml_root, encoding="unicode")}

        codigo = (result.get("codigo_respuesta") or "").strip()
        result["ok"] = codigo in ("0200", "0300", "0301", "0302")

        return result

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def recepcion_de(self, xml_sirecepde: str) -> Dict[str, Any]:
        """Envía un rEnviDe (siRecepDE) a SIFEN vía SOAP 1.2 (RAW).

        IMPORTANTE: NO re-serializa el XML para evitar romper firma/namespaces.
        Extrae el substring original del rEnviDe y lo embede directamente en el envelope SOAP.
        """
        service = "siRecepDE"

        if isinstance(xml_sirecepde, bytes):
            xml_sirecepde = xml_sirecepde.decode("utf-8")

        self._validate_size(service, xml_sirecepde)

        # Validación mínima: verificar que el root sea rEnviDe (solo para validar estructura)
        import lxml.etree as etree  # noqa: F401

        try:
            xml_root = etree.fromstring(xml_sirecepde.encode("utf-8"))
        except Exception as e:
            raise SifenClientError(f"Error al parsear XML siRecepDE: {e}")

        # Verificar root (con o sin namespace)
        expected_tag = f"{{{SIFEN_NS}}}rEnviDe"
        if xml_root.tag != expected_tag and xml_root.tag != "rEnviDe":
            try:
                if etree.QName(xml_root).localname != "rEnviDe":
                    raise SifenClientError(
                        f"XML root debe ser 'rEnviDe', encontrado: {xml_root.tag}"
                    )
            except Exception:
                raise SifenClientError(
                    f"XML root debe ser 'rEnviDe', encontrado: {xml_root.tag}"
                )

        # Asegurar que xDE contenga rDE como wrapper de DE (estructura esperada por SIFEN)
        xml_root = self._ensure_rde_wrapper(xml_root)

        # Re-serializar el XML modificado para extraer el substring
        # Esto preserva namespaces y estructura, incluyendo el nuevo rDE
        r_envi_de_content = etree.tostring(
            xml_root,
            xml_declaration=False,
            encoding="UTF-8",
            pretty_print=False,
            method="xml",
        )

        # Construir envelope SOAP 1.2 con el rEnviDe original embebido
        soap_bytes = self._build_raw_envelope_with_original_content(r_envi_de_content)

        response_bytes = None
        try:
            response_bytes = self._post_raw_soap("recibe", soap_bytes)
            self._save_raw_soap_debug(soap_bytes, response_bytes, suffix="")
        except Exception:
            self._save_raw_soap_debug(soap_bytes, None, suffix="")
            raise

        try:
            resp_root = etree.fromstring(response_bytes)
        except Exception as e:
            raise SifenClientError(f"Error al parsear respuesta XML de SIFEN: {e}")

        return self._parse_recepcion_response_from_xml(resp_root)

    def recepcion_lote(self, xml_renvio_lote: str) -> Dict[str, Any]:
        """Envía un rEnvioLote (siRecepLoteDE) a SIFEN vía SOAP 1.2 (RAW).

        Similar a recepcion_de() pero para envío de lotes.
        """
        service = "siRecepLoteDE"

        if isinstance(xml_renvio_lote, bytes):
            xml_renvio_lote = xml_renvio_lote.decode("utf-8")

        self._validate_size(service, xml_renvio_lote)

        # Validación mínima: verificar que el root sea rEnvioLote
        import lxml.etree as etree  # noqa: F401

        try:
            xml_root = etree.fromstring(xml_renvio_lote.encode("utf-8"))
        except Exception as e:
            raise SifenClientError(f"Error al parsear XML rEnvioLote: {e}")

        # Verificar root (con o sin namespace)
        expected_tag = f"{{{SIFEN_NS}}}rEnvioLote"
        if xml_root.tag != expected_tag and xml_root.tag != "rEnvioLote":
            try:
                if etree.QName(xml_root).localname != "rEnvioLote":
                    raise SifenClientError(
                        f"XML root debe ser 'rEnvioLote', encontrado: {xml_root.tag}"
                    )
            except Exception:
                raise SifenClientError(
                    f"XML root debe ser 'rEnvioLote', encontrado: {xml_root.tag}"
                )

        # Extraer dId del rEnvioLote para el HeaderMsg
        d_id_elem = xml_root.find(f".//{{{SIFEN_NS}}}dId")
        if d_id_elem is None:
            # Fallback: buscar sin namespace
            d_id_elem = xml_root.find(".//dId")
        d_id_value = d_id_elem.text if d_id_elem is not None and d_id_elem.text else "1"

        # Re-serializar el XML para extraer el substring
        r_envio_lote_content = etree.tostring(
            xml_root,
            xml_declaration=False,
            encoding="UTF-8",
            pretty_print=False,
            method="xml",
        )

        # Obtener URL base (sin ?wsdl)
        service_key = "recibe_lote"
        if service_key not in self._soap_address:
            self._get_client(service_key)
        if service_key not in self._soap_address:
            wsdl_url = self._normalize_wsdl_url(
                self.config.get_soap_service_url(service_key)
            )
            addr = self._extract_soap_address_from_wsdl(wsdl_url)
            if addr:
                self._soap_address[service_key] = addr
        
        if service_key not in self._soap_address:
            raise SifenClientError(
                f"No se encontró SOAP address para servicio '{service_key}'."
            )
        
        original_url = self._soap_address[service_key]
        
        # Quitar solo querystring, mantener .wsdl
        parsed = urlparse(original_url)
        post_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,  # Mantiene .wsdl
            parsed.params,
            "",  # Sin query
            parsed.fragment
        ))
        
        # Construir SOAP 1.2 exacto: Header vacío, Body con rEnvioLote directamente
        envelope = etree.Element(
            f"{{{SOAP_NS}}}Envelope",
            nsmap={"soap": SOAP_NS, "xsd": SIFEN_NS}
        )
        
        # Header vacío
        header = etree.SubElement(envelope, f"{{{SOAP_NS}}}Header")
        
        # Body con rEnvioLote directamente (sin wrapper)
        body = etree.SubElement(envelope, f"{{{SOAP_NS}}}Body")
        r_envio_lote_elem = etree.fromstring(r_envio_lote_content)
        body.append(r_envio_lote_elem)
        
        soap_bytes = etree.tostring(
            envelope, xml_declaration=True, encoding="UTF-8", pretty_print=False
        )
        
        # Headers SOAP 1.2
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "Accept": "application/soap+xml, text/xml, */*",
        }
        
        # POST con mTLS (la sesión ya tiene cert configurado)
        session = self.transport.session
        
        # Obtener paths de certificado para debug
        mtls_cert_path = None
        mtls_key_path = None
        if hasattr(self, '_temp_pem_files') and self._temp_pem_files:
            mtls_cert_path, mtls_key_path = self._temp_pem_files
        elif session.cert:
            if isinstance(session.cert, tuple):
                mtls_cert_path, mtls_key_path = session.cert
            else:
                mtls_cert_path = session.cert
        
        try:
            resp = session.post(
                post_url,
                data=soap_bytes,
                headers=headers,
                timeout=(self.connect_timeout, self.read_timeout),
            )
            
            # Guardar debug
            self._save_http_debug(
                post_url=post_url,
                original_url=original_url,
                version="1.2",
                action="siRecepLoteDE",
                headers=headers,
                soap_bytes=soap_bytes,
                response_status=resp.status_code,
                response_headers=dict(resp.headers),
                response_body=resp.content,
                mtls_cert_path=mtls_cert_path,
                mtls_key_path=mtls_key_path,
            )
            
            # Verificar éxito
            is_success = False
            if resp.status_code == 200:
                is_success = True
            else:
                # Verificar si hay respuesta XML válida aunque HTTP != 200
                try:
                    resp_body_str = resp.content.decode("utf-8", errors="replace")
                    if "<rRetEnviDe" in resp_body_str or "<dCodRes>" in resp_body_str:
                        is_success = True
                except Exception:
                    pass
            
            if is_success:
                # Guardar SOAP debug adicional
                self._save_raw_soap_debug(soap_bytes, resp.content, suffix="_lote")
                
                try:
                    resp_root = etree.fromstring(resp.content)
                    return self._parse_recepcion_response_from_xml(resp_root)
                except Exception as e:
                    raise SifenClientError(f"Error al parsear respuesta XML de SIFEN: {e}")
            else:
                # Error HTTP pero con respuesta XML válida
                error_msg = f"Error HTTP {resp.status_code} al enviar SOAP: {resp.text[:500]}"
                self._save_raw_soap_debug(soap_bytes, resp.content, suffix="_lote")
                raise SifenClientError(error_msg)
                
        except Exception as e:
            # Guardar debug incluso en error
            self._save_http_debug(
                post_url=post_url,
                original_url=original_url,
                version="1.2",
                action="siRecepLoteDE",
                headers=headers,
                soap_bytes=soap_bytes,
                response_status=None,
                response_headers=None,
                response_body=None,
                mtls_cert_path=mtls_cert_path,
                mtls_key_path=mtls_key_path,
            )
            self._save_raw_soap_debug(soap_bytes, None, suffix="_lote")
            raise SifenClientError(f"Error al enviar SOAP a SIFEN: {e}") from e

    def consulta_lote(self, xml_renvi_cons_lote_de: str, timeout: int = 60) -> Dict[str, Any]:
        """Envía un rEnviConsLoteDe (siConsLoteDE) a SIFEN vía SOAP 1.2 (RAW).
        
        Args:
            xml_renvi_cons_lote_de: XML del rEnviConsLoteDe (string o bytes)
            timeout: Timeout en segundos (se usa en _post_raw_soap)
            
        Returns:
            Dict con response_xml, cod_res_lot, msg_res_lot, etc.
        """
        service_key = "consulta_lote"
        service_action = "siConsLoteDE"
        
        if isinstance(xml_renvi_cons_lote_de, bytes):
            xml_renvi_cons_lote_de = xml_renvi_cons_lote_de.decode("utf-8")
        
        self._validate_size(service_action, xml_renvi_cons_lote_de)
        
        # Validación mínima: verificar que el root sea rEnviConsLoteDe
        import lxml.etree as etree  # noqa: F401
        
        try:
            xml_root = etree.fromstring(xml_renvi_cons_lote_de.encode("utf-8"))
        except Exception as e:
            raise SifenClientError(f"Error al parsear XML rEnviConsLoteDe: {e}")
        
        # Verificar root (con o sin namespace)
        expected_tag = f"{{{SIFEN_NS}}}rEnviConsLoteDe"
        if xml_root.tag != expected_tag and xml_root.tag != "rEnviConsLoteDe":
            try:
                if etree.QName(xml_root).localname != "rEnviConsLoteDe":
                    raise SifenClientError(
                        f"XML root debe ser 'rEnviConsLoteDe', encontrado: {xml_root.tag}"
                    )
            except Exception:
                raise SifenClientError(
                    f"XML root debe ser 'rEnviConsLoteDe', encontrado: {xml_root.tag}"
                )
        
        # Re-serializar el XML para el envelope
        r_envi_cons_lote_de_content = etree.tostring(
            xml_root,
            xml_declaration=False,
            encoding="UTF-8",
            pretty_print=False,
            method="xml",
        )
        
        # Construir envelope SOAP 1.2 con el rEnviConsLoteDe embebido
        soap_bytes = self._build_raw_envelope_with_original_content(
            r_envi_cons_lote_de_content, action=service_action
        )
        
        response_bytes = None
        try:
            response_bytes = self._post_raw_soap(service_key, soap_bytes)
            self._save_raw_soap_debug(soap_bytes, response_bytes, suffix="_consulta")
        except Exception:
            self._save_raw_soap_debug(soap_bytes, None, suffix="_consulta")
            raise
        
        try:
            resp_root = etree.fromstring(response_bytes)
        except Exception as e:
            raise SifenClientError(f"Error al parsear respuesta XML de SIFEN: {e}")
        
        return self._parse_consulta_lote_response_from_xml(resp_root)

    def _parse_consulta_lote_response_from_xml(self, xml_root: Any) -> Dict[str, Any]:
        """Parsea la respuesta de consulta de lote desde XML."""
        import lxml.etree as etree  # noqa: F401
        
        result: Dict[str, Any] = {
            "ok": False,
            "response_xml": etree.tostring(xml_root, encoding="unicode"),
            "cod_res_lot": None,
            "msg_res_lot": None,
        }
        
        def find_text(xpath_expr: str) -> Optional[str]:
            try:
                nodes = xml_root.xpath(xpath_expr)
                if nodes:
                    val = nodes[0].text
                    return val.strip() if val else None
            except Exception:
                return None
            return None
        
        # Buscar campos de respuesta de consulta lote
        result["cod_res_lot"] = find_text('//*[local-name()="dCodResLot"]')
        result["msg_res_lot"] = find_text('//*[local-name()="dMsgResLot"]')
        
        # Determinar éxito basado en código
        cod_res_lot = result.get("cod_res_lot", "")
        if cod_res_lot in ("0361", "0362"):
            result["ok"] = True
        elif cod_res_lot == "0364":
            result["ok"] = False  # Requiere CDC
        else:
            result["ok"] = False
        
        return result

    def consulta_lote_raw(self, dprot_cons_lote: str, did: int = 1) -> Dict[str, Any]:
        """Consulta lote sin depender del WSDL (POST directo al endpoint).
        
        Args:
            dprot_cons_lote: dProtConsLote (número de lote)
            did: dId (default: 1)
            
        Returns:
            Dict con http_status, raw_xml, y opcionalmente dCodResLot/dMsgResLot
        """
        import lxml.etree as etree  # noqa: F401
        
        # Construir SOAP envelope manualmente (SIN HeaderMsg)
        envelope = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap={"soap-env": SOAP_NS})
        body = etree.SubElement(envelope, f"{{{SOAP_NS}}}Body")
        
        r_envi_cons = etree.SubElement(
            body, f"{{{SIFEN_NS}}}rEnviConsLoteDe", nsmap={None: SIFEN_NS}
        )
        d_id_elem = etree.SubElement(r_envi_cons, f"{{{SIFEN_NS}}}dId")
        d_id_elem.text = str(did)
        d_prot_elem = etree.SubElement(r_envi_cons, f"{{{SIFEN_NS}}}dProtConsLote")
        d_prot_elem.text = str(dprot_cons_lote)
        
        soap_bytes = etree.tostring(
            envelope, xml_declaration=True, encoding="UTF-8", pretty_print=False
        )
        
        # Determinar endpoint según ambiente (con .wsdl al final)
        if self.config.env == "test":
            endpoint = "https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl"
        else:
            endpoint = "https://sifen.set.gov.py/de/ws/consultas/consulta-lote.wsdl"
        
        # Headers SOAP 1.2 (solo Content-Type, sin action, sin SOAPAction)
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
        }
        
        # Guardar debug antes de enviar
        debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
        if debug_enabled:
            try:
                from pathlib import Path
                out_dir = Path("artifacts")
                out_dir.mkdir(exist_ok=True)
                sent_file = out_dir / "soap_last_sent_consulta.xml"
                sent_file.write_bytes(soap_bytes)
            except Exception:
                pass  # No romper el flujo si falla debug
        
        # POST usando la sesión existente con mTLS
        session = self.transport.session
        result: Dict[str, Any] = {
            "http_status": 0,
            "raw_xml": "",
        }
        
        try:
            resp = session.post(
                endpoint,
                data=soap_bytes,
                headers=headers,
                timeout=(self.connect_timeout, self.read_timeout),
            )
            result["http_status"] = resp.status_code
            result["raw_xml"] = resp.text
            
            # Guardar debug incluso si HTTP != 200
            if debug_enabled:
                try:
                    from pathlib import Path
                    out_dir = Path("artifacts")
                    out_dir.mkdir(exist_ok=True)
                    received_file = out_dir / "soap_last_received_consulta.xml"
                    received_file.write_bytes(resp.content)
                except Exception:
                    pass  # No romper el flujo si falla debug
            
            # Intentar parsear XML y extraer dCodResLot/dMsgResLot si existen
            try:
                resp_root = etree.fromstring(resp.content)
                cod_res = resp_root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dCodResLot")
                msg_res = resp_root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dMsgResLot")
                if cod_res is not None and cod_res.text:
                    result["dCodResLot"] = cod_res.text.strip()
                if msg_res is not None and msg_res.text:
                    result["dMsgResLot"] = msg_res.text.strip()
            except Exception:
                pass  # Si no se puede parsear, solo devolver raw_xml
            
        except Exception as e:
            # Guardar debug incluso si hay excepción
            if debug_enabled:
                try:
                    from pathlib import Path
                    out_dir = Path("artifacts")
                    out_dir.mkdir(exist_ok=True)
                    received_file = out_dir / "soap_last_received_consulta.xml"
                    received_file.write_bytes(b"")  # Vacío si no hay respuesta
                except Exception:
                    pass
            raise SifenClientError(f"Error al consultar lote: {e}") from e
        
        return result

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

        if self._temp_pem_files:
            cert_path, key_path = self._temp_pem_files
            cleanup_pem_files(cert_path, key_path)
            self._temp_pem_files = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
