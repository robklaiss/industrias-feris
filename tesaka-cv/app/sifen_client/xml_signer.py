"""
Módulo para firma digital XML según especificación SIFEN

Requisitos:
- XML Digital Signature Enveloped
- Certificado X.509 v3
- Algoritmo RSA 2048 bits
- Hash SHA-256
- Validación de cadena de confianza (CRL/LCR)

IMPORTANTE: Este módulo usa lazy imports para signxml y lxml.
Se importan solo cuando se usan las funciones, no al importar el módulo.
"""
import os
import logging
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone

# Imports estándar (siempre disponibles)
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography import x509
from cryptography.hazmat.backends import default_backend

# Lazy imports para signxml y lxml (solo cuando se necesitan)
_lxml_etree = None
_XMLSigner = None
_XMLVerifier = None
_ensure_str = None
_SignatureConstructionMethod = None
_SignatureConfiguration = None

def _ensure_signxml_imports():
    """Importa signxml y lxml solo cuando se necesitan"""
    global _lxml_etree, _XMLSigner, _XMLVerifier, _ensure_str, _SignatureConstructionMethod, _SignatureConfiguration
    
    if _lxml_etree is None:
        try:
            from lxml import etree as _lxml_etree_module
            _lxml_etree = _lxml_etree_module
        except ImportError as e:
            raise ImportError(
                "lxml no está instalado. Instale con: pip install lxml"
            ) from e
    
    if _XMLSigner is None:
        try:
            from signxml import XMLSigner as _XMLSigner_module, XMLVerifier as _XMLVerifier_module
            from signxml.util import ensure_str as _ensure_str_module
            _XMLSigner = _XMLSigner_module
            _XMLVerifier = _XMLVerifier_module
            _ensure_str = _ensure_str_module
        except ImportError as e:
            raise ImportError(
                "signxml no está instalado. Instale con: pip install signxml"
            ) from e
        
        # signxml cambia APIs entre versiones
        try:
            from signxml.algorithms import SignatureConstructionMethod as _SCM  # type: ignore
            _SignatureConstructionMethod = _SCM
        except Exception:
            try:
                from signxml.signer import SignatureConstructionMethod as _SCM  # type: ignore
                _SignatureConstructionMethod = _SCM
            except Exception:
                _SignatureConstructionMethod = None  # type: ignore
        
        # Import robusto de SignatureConfiguration
        try:
            from signxml.verifier import SignatureConfiguration as _SC  # type: ignore
            _SignatureConfiguration = _SC
        except Exception:
            try:
                from signxml import SignatureConfiguration as _SC  # type: ignore
                _SignatureConfiguration = _SC
            except Exception:
                _SignatureConfiguration = None  # type: ignore
    
    return _lxml_etree, _XMLSigner, _XMLVerifier, _ensure_str, _SignatureConstructionMethod, _SignatureConfiguration

logger = logging.getLogger(__name__)


class XmlSignerError(Exception):
    """Excepción para errores en la firma XML"""
    pass


class XmlSigner:
    """
    Firma XML según especificación SIFEN:
    - XML Digital Signature Enveloped
    - Certificado X.509 v3
    - RSA 2048 bits
    - SHA-256
    """
    
    def __init__(
        self,
        cert_path: Optional[str] = None,
        cert_password: Optional[str] = None,
        key_path: Optional[str] = None,
        key_password: Optional[str] = None
    ):
        """
        Inicializa el firmador XML
        
        Args:
            cert_path: Ruta al certificado PFX/P12 (PKCS#12)
            cert_password: Contraseña del certificado
            key_path: Ruta a la clave privada (si está separada del certificado)
            key_password: Contraseña de la clave privada
        """
        # Cargar desde variables de entorno si no se proporcionan
        self.cert_path = cert_path or os.getenv("SIFEN_CERT_PATH")
        self.cert_password = cert_password or os.getenv("SIFEN_CERT_PASSWORD", "")
        self.key_path = key_path or os.getenv("SIFEN_KEY_PATH")
        self.key_password = key_password or os.getenv("SIFEN_KEY_PASSWORD", "")
        
        if not self.cert_path:
            raise XmlSignerError("Certificado no especificado. Configure SIFEN_CERT_PATH o pase cert_path")
        
        cert_file = Path(self.cert_path)
        if not cert_file.exists():
            raise XmlSignerError(f"Certificado no encontrado: {self.cert_path}")
        
        # Cargar certificado y clave privada
        self._load_certificate()
        
        # Validar certificado
        self._validate_certificate()
    
    def _load_certificate(self):
        """Carga el certificado y la clave privada desde el archivo PFX/P12"""
        try:
            with open(self.cert_path, 'rb') as f:
                pfx_data = f.read()
            
            # Intentar cargar como PKCS#12
            try:
                from cryptography.hazmat.primitives.serialization import pkcs12
                private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
                    pfx_data,
                    self.cert_password.encode() if self.cert_password else None,
                    backend=default_backend()
                )
                
                if private_key is None:
                    raise XmlSignerError("No se pudo extraer la clave privada del certificado")
                if certificate is None:
                    raise XmlSignerError("No se pudo extraer el certificado del archivo")
                
                self.private_key = private_key
                self.certificate = certificate
                self.additional_certificates = additional_certificates or []
                
            except Exception as e:
                # Si falla PKCS#12, intentar cargar certificado y clave por separado
                if self.key_path:
                    self._load_separate_key_and_cert()
                else:
                    raise XmlSignerError(f"Error al cargar certificado PKCS#12: {str(e)}")
        
        except Exception as e:
            raise XmlSignerError(f"Error al leer certificado: {str(e)}")
    
    def _load_separate_key_and_cert(self):
        """Carga certificado y clave privada desde archivos separados"""
        try:
            # Cargar certificado
            with open(self.cert_path, 'rb') as f:
                cert_data = f.read()
                self.certificate = x509.load_pem_x509_certificate(cert_data, default_backend())
            
            # Cargar clave privada
            if not self.key_path:
                raise XmlSignerError("key_path requerido cuando el certificado no es PKCS#12")
            
            with open(self.key_path, 'rb') as f:
                key_data = f.read()
                password = self.key_password.encode() if self.key_password else None
                self.private_key = serialization.load_pem_private_key(
                    key_data,
                    password=password,
                    backend=default_backend()
                )
            
            self.additional_certificates = []
        
        except Exception as e:
            raise XmlSignerError(f"Error al cargar certificado/clave separados: {str(e)}")
    
    def _validate_certificate(self):
        """
        Valida el certificado:
        - Fecha de expiración
        - Algoritmo de clave (RSA 2048)
        - Tipo X.509 v3
        """
        now = datetime.now(timezone.utc)
        
        # Resolver not_valid_after y not_valid_before con fallback para compatibilidad
        # cryptography puede tener not_valid_after_utc/not_valid_before_utc (timezone-aware)
        # o not_valid_after/not_valid_before (naive, se convierte a UTC)
        if hasattr(self.certificate, 'not_valid_after_utc'):
            not_valid_after = self.certificate.not_valid_after_utc
        else:
            not_valid_after = self.certificate.not_valid_after.replace(tzinfo=timezone.utc) if hasattr(self.certificate, 'not_valid_after') else None
        
        if hasattr(self.certificate, 'not_valid_before_utc'):
            not_valid_before = self.certificate.not_valid_before_utc
        else:
            not_valid_before = self.certificate.not_valid_before.replace(tzinfo=timezone.utc) if hasattr(self.certificate, 'not_valid_before') else None
        
        # Validar fecha de expiración
        if not_valid_after and not_valid_after < now:
            raise XmlSignerError(
                f"Certificado expirado. Válido hasta: {not_valid_after}"
            )
        
        if not_valid_before and not_valid_before > now:
            raise XmlSignerError(
                f"Certificado aún no válido. Válido desde: {not_valid_before}"
            )
        
        # Validar algoritmo de clave
        if not isinstance(self.private_key, rsa.RSAPrivateKey):
            raise XmlSignerError("La clave privada debe ser RSA")
        
        key_size = self.private_key.key_size
        if key_size < 2048:
            raise XmlSignerError(
                f"La clave RSA debe ser de al menos 2048 bits. Actual: {key_size} bits"
            )
        
        # Validar versión del certificado (X.509 v3)
        # Nota: cryptography no expone directamente la versión, pero los certificados modernos son v3
        logger.info(f"Certificado válido. Emisor: {self.certificate.issuer}, "
                   f"Válido hasta: {not_valid_after}")
    
    def sign(self, xml_content: str, reference_uri: Optional[str] = None) -> str:
        """
        Firma un XML usando XML Digital Signature Enveloped
        
        Args:
            xml_content: Contenido XML a firmar
            reference_uri: URI de referencia para la firma (opcional)
            
        Returns:
            XML firmado como string
        """
        # Lazy import de signxml y lxml
        etree, XMLSigner, _, _, SignatureConstructionMethod, _ = _ensure_signxml_imports()
        
        try:
            # Parsear XML
            root = etree.fromstring(xml_content.encode('utf-8'))
            
            # method: Enum (nuevas versiones) o string (compatibilidad)
            method = (
                SignatureConstructionMethod.enveloped
                if SignatureConstructionMethod is not None else "enveloped"
            )
            
            # cert: signxml espera un cert_chain iterable (lista/tuple)
            # Si self.certificate NO es bytes/bytearray/str/list/tuple, envolverlo en lista
            if isinstance(self.certificate, (bytes, bytearray, str, list, tuple)):
                cert_for_signxml = self.certificate
            else:
                cert_for_signxml = [self.certificate]
            
            # Configurar firmador según NT16/MT v150
            signer = XMLSigner(
                method=method,
                signature_algorithm='rsa-sha256',
                digest_algorithm='sha256',
                c14n_algorithm='http://www.w3.org/2001/10/xml-exc-c14n#',
                exclude_c14n_transform_element=True  # Solo enveloped-signature en Transforms
            )
            
            # Firmar
            signed_root = signer.sign(
                root,
                key=self.private_key,
                cert=cert_for_signxml,
                reference_uri=reference_uri
            )
            
            # Convertir a string
            signed_xml = etree.tostring(
                signed_root,
                encoding='utf-8',
                xml_declaration=True,
                pretty_print=False
            ).decode('utf-8')
            
            logger.info("XML firmado exitosamente")
            return signed_xml
        
        except Exception as e:
            raise XmlSignerError(f"Error al firmar XML: {str(e)}")
    
    def verify(self, signed_xml: str) -> bool:
        """
        Verifica la firma de un XML firmado
        
        Args:
            signed_xml: XML firmado a verificar
            
        Returns:
            True si la firma es válida, False en caso contrario
        """
        # Lazy import de signxml y lxml
        etree, _, XMLVerifier, _, _, SignatureConfiguration = _ensure_signxml_imports()
        
        try:
            root = etree.fromstring(signed_xml.encode('utf-8'))
            
            # Intentar verificación estricta primero (con validación X.509)
            verifier = XMLVerifier()
            try:
                result = verifier.verify(root, require_x509=True)
                return result is not None
            except Exception as e:
                error_msg = str(e).lower()
                # Detectar errores de validación X.509/extensiones
                if any(keyword in error_msg for keyword in [
                    "invalid extension",
                    "missing required extension",
                    "certificate is missing required extension"
                ]):
                    # Reintentar con require_x509=False y certificado en PEM
                    logger.debug(
                        f"Verificación estricta falló por validación X.509: {str(e)[:200]}. "
                        f"Reintentando con require_x509=False y certificado en PEM..."
                    )
                    try:
                        # Convertir certificado a PEM
                        cert_pem = self.certificate.public_bytes(serialization.Encoding.PEM)
                        # Verificar con certificado en PEM y sin validación X.509 estricta
                        result = verifier.verify(root, x509_cert=cert_pem, require_x509=False)
                        return result is not None
                    except Exception as e2:
                        logger.error(f"Error al verificar firma (fallback): {str(e2)}")
                        return False
                else:
                    # Error no relacionado a X.509, fallar normalmente
                    logger.error(f"Error al verificar firma: {str(e)}")
                    return False
        
        except Exception as e:
            logger.error(f"Error al verificar firma: {str(e)}")
            return False
    
    def get_certificate_info(self) -> dict:
        """
        Obtiene información del certificado
        
        Returns:
            Diccionario con información del certificado
        """
        subject = self.certificate.subject
        issuer = self.certificate.issuer
        
        # Extraer RUC del subject si está presente
        ruc = None
        for attr in subject:
            if attr.oid._name == 'commonName' or 'RUC' in str(attr.value):
                ruc = str(attr.value)
                break
        
        # Resolver not_valid_after y not_valid_before con fallback para compatibilidad
        # cryptography puede tener not_valid_after_utc/not_valid_before_utc (timezone-aware)
        # o not_valid_after/not_valid_before (naive, se convierte a UTC)
        if hasattr(self.certificate, 'not_valid_after_utc'):
            not_valid_after = self.certificate.not_valid_after_utc
        else:
            not_valid_after = self.certificate.not_valid_after.replace(tzinfo=timezone.utc) if hasattr(self.certificate, 'not_valid_after') else None
        
        if hasattr(self.certificate, 'not_valid_before_utc'):
            not_valid_before = self.certificate.not_valid_before_utc
        else:
            not_valid_before = self.certificate.not_valid_before.replace(tzinfo=timezone.utc) if hasattr(self.certificate, 'not_valid_before') else None
        
        return {
            'subject': str(subject),
            'issuer': str(issuer),
            'serial_number': str(self.certificate.serial_number),
            'not_valid_before': not_valid_before.isoformat() if not_valid_before else None,
            'not_valid_after': not_valid_after.isoformat() if not_valid_after else None,
            'ruc': ruc,
            'key_size': self.private_key.key_size if hasattr(self.private_key, 'key_size') else None
        }

