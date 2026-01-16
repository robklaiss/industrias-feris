"""
Módulo cliente para integración con SIFEN (Sistema Integrado de Facturación Electrónica Nacional)
Paraguay - DNIT

IMPORTANTE: Este módulo usa lazy imports para evitar errores cuando faltan dependencias opcionales
(signxml, xmlsec, lxml). Los módulos pesados se importan solo cuando se usan.
"""
from .config import SifenConfig, get_sifen_config
from .client import SifenClient, SifenClientError
from .validator import SifenValidator
from .soap_client import SoapClient, SIZE_LIMITS
from .pkcs12_utils import p12_to_temp_pem_files, cleanup_pem_files, PKCS12Error
from .exceptions import (
    SifenException,
    SifenValidationError,
    SifenSignatureError,
    SifenQRError,
    SifenSizeLimitError,
    SifenResponseError
)

# Lazy imports para módulos que requieren signxml/xmlsec/lxml
# Estos se importan solo cuando se usan, no al importar el paquete
def _lazy_import_xml_signer():
    """Importa XmlSigner solo cuando se necesita"""
    try:
        from .xml_signer import XmlSigner, XmlSignerError
        return XmlSigner, XmlSignerError
    except ImportError as e:
        raise ImportError(
            "XmlSigner requiere signxml y lxml. "
            "Instale con: pip install signxml lxml"
        ) from e

def _lazy_import_qr_generator():
    """Importa QRGenerator solo cuando se necesita"""
    try:
        from .qr_generator import QRGenerator, QRGeneratorError
        return QRGenerator, QRGeneratorError
    except ImportError as e:
        raise ImportError(
            "QRGenerator requiere dependencias adicionales. "
            "Instale con: pip install -r requirements-sifen.txt"
        ) from e

# Exportar getters para acceso lazy
def get_xml_signer():
    """Obtiene XmlSigner (lazy import)"""
    return _lazy_import_xml_signer()[0]

def get_xml_signer_error():
    """Obtiene XmlSignerError (lazy import)"""
    return _lazy_import_xml_signer()[1]

def get_qr_generator():
    """Obtiene QRGenerator (lazy import)"""
    return _lazy_import_qr_generator()[0]

def get_qr_generator_error():
    """Obtiene QRGeneratorError (lazy import)"""
    return _lazy_import_qr_generator()[1]

__all__ = [
    'SifenConfig',
    'get_sifen_config',
    'SifenClient',
    'SifenClientError',
    'SifenValidator',
    'SoapClient',
    'SIZE_LIMITS',
    'SifenException',
    'SifenValidationError',
    'SifenSignatureError',
    'SifenQRError',
    'SifenSizeLimitError',
    'SifenResponseError',
    'p12_to_temp_pem_files',
    'cleanup_pem_files',
    'PKCS12Error',
    # Lazy imports (usar get_xml_signer() o importar directamente desde .xml_signer)
    'get_xml_signer',
    'get_xml_signer_error',
    'get_qr_generator',
    'get_qr_generator_error',
]

