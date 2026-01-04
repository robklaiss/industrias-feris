"""
Configuración para cliente SIFEN
"""
import os
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

# Cargar dotenv si está disponible (opcional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv no está instalado, continuar sin cargar .env
    pass


def get_cert_path_and_password() -> Tuple[str, str]:
    """
    Helper unificado para obtener certificado P12 y contraseña desde variables de entorno.
    
    Prioridad:
    1. SIFEN_CERT_PATH / SIFEN_CERT_PASSWORD (estándar)
    2. SIFEN_SIGN_P12_PATH / SIFEN_SIGN_P12_PASSWORD (alias, compatibilidad)
    
    Returns:
        Tupla (cert_path, cert_password)
        
    Raises:
        RuntimeError: Si faltan las variables de entorno o el archivo no existe
    """
    cert_path = os.environ.get("SIFEN_CERT_PATH") or os.environ.get("SIFEN_SIGN_P12_PATH")
    if not cert_path:
        raise RuntimeError("Falta SIFEN_CERT_PATH (o SIFEN_SIGN_P12_PATH) en el entorno")
    
    cert_password = os.environ.get("SIFEN_CERT_PASSWORD") or os.environ.get("SIFEN_SIGN_P12_PASSWORD")
    if not cert_password:
        raise RuntimeError("Falta SIFEN_CERT_PASSWORD (o SIFEN_SIGN_P12_PASSWORD) en el entorno")
    
    # Validar que el archivo existe
    if not os.path.exists(cert_path):
        raise RuntimeError(f"Certificado no encontrado: {cert_path}")
    
    return cert_path, cert_password


def get_mtls_cert_path_and_password() -> Tuple[str, str]:
    """
    Helper para obtener certificado P12 y contraseña para mTLS desde variables de entorno.
    
    Prioridad:
    1. SIFEN_MTLS_P12_PATH / SIFEN_MTLS_P12_PASSWORD (específico para mTLS)
    2. SIFEN_CERT_PATH / SIFEN_CERT_PASSWORD (fallback)
    3. SIFEN_SIGN_P12_PATH / SIFEN_SIGN_P12_PASSWORD (fallback)
    
    Returns:
        Tupla (cert_path, cert_password)
        
    Raises:
        RuntimeError: Si faltan las variables de entorno o el archivo no existe
    """
    cert_path = (
        os.environ.get("SIFEN_MTLS_P12_PATH") or
        os.environ.get("SIFEN_CERT_PATH") or
        os.environ.get("SIFEN_SIGN_P12_PATH")
    )
    if not cert_path:
        raise RuntimeError("Falta SIFEN_MTLS_P12_PATH, SIFEN_CERT_PATH o SIFEN_SIGN_P12_PATH en el entorno")
    
    cert_password = (
        os.environ.get("SIFEN_MTLS_P12_PASSWORD") or
        os.environ.get("SIFEN_CERT_PASSWORD") or
        os.environ.get("SIFEN_SIGN_P12_PASSWORD")
    )
    if not cert_password:
        raise RuntimeError("Falta SIFEN_MTLS_P12_PASSWORD, SIFEN_CERT_PASSWORD o SIFEN_SIGN_P12_PASSWORD en el entorno")
    
    # Validar que el archivo existe
    if not os.path.exists(cert_path):
        raise RuntimeError(f"Certificado no encontrado: {cert_path}")
    
    return cert_path, cert_password


class SifenConfig:
    """Configuración del cliente SIFEN por ambiente"""
    
    ENV_TEST = "test"
    ENV_PROD = "prod"
    
    # URLs base según "Guía de Mejores Prácticas para la Gestión del Envío de DE" (Oct 2024)
    # Fuente: https://ekuatia.set.gov.py
    BASE_URLS = {
        "test": os.getenv("SIFEN_TEST_BASE_URL", "https://sifen-test.set.gov.py"),
        "prod": os.getenv("SIFEN_PROD_BASE_URL", "https://sifen.set.gov.py"),
    }
    
    # Prevalidador (público - herramienta de desarrollo)
    # Fuente: Guía de Mejores Prácticas, pág. 4
    PREVALIDADOR_URL = "https://ekuatia.set.gov.py/prevalidador/"
    
    # Servicios Web SOAP según Manual Técnico SIFEN V150
    # SOAP 1.2 Document/Literal
    # Fuente: Manual Técnico SIFEN V150
    SOAP_SERVICES = {
        "test": {
            "recibe": "https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl",
            "recibe_lote": "https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl",
            "evento": "https://sifen-test.set.gov.py/de/ws/eventos/evento.wsdl",
            "consulta_lote": "https://sifen-test.set.gov.py/de/ws/consultas-lote/consulta-lote.wsdl",
            "consulta_ruc": "https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl",
            "consulta": "https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl",
        },
        "prod": {
            "recibe": "https://sifen.set.gov.py/de/ws/sync/recibe.wsdl",
            "recibe_lote": "https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl",
            "evento": "https://sifen.set.gov.py/de/ws/eventos/evento.wsdl",
            "consulta_lote": "https://sifen.set.gov.py/de/ws/consultas-lote/consulta-lote.wsdl",
            "consulta_ruc": "https://sifen.set.gov.py/de/ws/consultas/consulta-ruc.wsdl",
            "consulta": "https://sifen.set.gov.py/de/ws/consultas/consulta.wsdl",
        }
    }
    
    # Tipo de servicio - CONFIRMADO: SOAP según Guía de Mejores Prácticas
    SERVICE_TYPE = "SOAP"  # SIFEN usa SOAP 1.2 según documentación oficial
    
    # WSDL URLs
    WSDL_URL_TEST = os.getenv("SIFEN_WSDL_URL_TEST", SOAP_SERVICES["test"]["recibe_lote"])
    WSDL_URL_PROD = os.getenv("SIFEN_WSDL_URL_PROD", SOAP_SERVICES["prod"]["recibe_lote"])
    
    def __init__(self, env: str = ENV_TEST):
        """
        Inicializa la configuración SIFEN
        
        Args:
            env: Ambiente ('test' o 'prod')
        """
        if env not in [self.ENV_TEST, self.ENV_PROD]:
            raise ValueError(f"Ambiente inválido: {env}. Debe ser 'test' o 'prod'")
        
        self.env = env
        self.base_url = self.BASE_URLS[env]
        
        # Autenticación - mTLS es REQUERIDO según Manual Técnico SIFEN V150
        # TLS 1.2 con autenticación mutua usando certificados X.509 v3
        self.use_mtls = os.getenv("SIFEN_USE_MTLS", "true").lower() == "true"
        
        # Atributos de certificado (mTLS) - inicializados como None
        # Se pueden asignar desde variables de entorno en get_sifen_config()
        self.cert_path: Optional[str] = None
        self.cert_password: Optional[str] = None
        
        # Atributos para mTLS con PEM directo (cert + key separados)
        # Prioridad: si están presentes, se usan en lugar de PKCS12
        self.cert_pem_path: Optional[str] = None
        self.key_pem_path: Optional[str] = None
        
        if self.use_mtls:
            # Configuración mTLS (mutual TLS) - usar helper unificado
            # El helper ya valida existencia y lanza RuntimeError si faltan env vars
            try:
                cert_path, cert_password = get_cert_path_and_password()
                self.cert_path = cert_path
                self.cert_password = cert_password
            except RuntimeError:
                # Si falla, dejar como None (puede ser que use_mtls=False más adelante)
                # o que se configure desde otro lugar
                pass
            
            ca_bundle_path = os.getenv("SIFEN_CA_BUNDLE_PATH")
            # ca_bundle_path se mantiene como Path para compatibilidad
            self.ca_bundle_path = Path(ca_bundle_path) if ca_bundle_path else None
        else:
            # Otro tipo de autenticación (API Key, OAuth, etc.)
            self.api_key = os.getenv("SIFEN_API_KEY")
            self.user = os.getenv("SIFEN_USER")
            self.password = os.getenv("SIFEN_PASSWORD")
        
        # Timeouts
        self.request_timeout = int(os.getenv("SIFEN_REQUEST_TIMEOUT", "30"))
        
        # Datos de prueba (solo para ambiente test)
        if env == self.ENV_TEST:
            self.test_ruc = os.getenv("SIFEN_TEST_RUC", "")
            self.test_timbrado = os.getenv("SIFEN_TEST_TIMBRADO", "")
            self.test_csc = os.getenv("SIFEN_TEST_CSC", "")
            self.test_razon_social = os.getenv("SIFEN_TEST_RAZON_SOCIAL", "")
    
    @property
    def wsdl_url(self) -> Optional[str]:
        """Retorna la URL del WSDL según el ambiente (si es SOAP)"""
        if self.SERVICE_TYPE != "SOAP":
            return None
        return self.WSDL_URL_TEST if self.env == self.ENV_TEST else self.WSDL_URL_PROD
    
    def get_soap_service_url(self, service_key: str) -> str:
        """
        Obtiene la URL de un servicio SOAP según el ambiente
        
        Args:
            service_key: Clave del servicio ('recibe_lote', 'consulta_lote', 'consulta')
            
        Returns:
            URL del WSDL del servicio
            
        Nota:
            Para consulta_lote, se permite override mediante env var SIFEN_WSDL_CONSULTA_LOTE
        """
        valid_keys = ["recibe", "recibe_lote", "evento", "consulta_lote", "consulta_ruc", "consulta"]
        if service_key not in valid_keys:
            raise ValueError(f"Servicio SOAP inválido: {service_key}. Válidos: {valid_keys}")
        
        # Permitir override por env var para consulta_lote
        if service_key == "consulta_lote":
            override_url = os.getenv("SIFEN_WSDL_CONSULTA_LOTE")
            if override_url:
                return override_url
        
        return self.SOAP_SERVICES[self.env][service_key]
    
    def get_endpoint_url(self, endpoint_key: str) -> str:
        """
        Construye la URL completa de un endpoint (legacy - usar get_soap_service_url para SOAP)
        
        Args:
            endpoint_key: Clave del endpoint
            
        Returns:
            URL completa
        """
        # Para SOAP, redirigir a servicios SOAP
        if self.SERVICE_TYPE == "SOAP":
            if endpoint_key == "envio_de" or endpoint_key == "recibe_lote":
                return self.get_soap_service_url("recibe_lote")
            elif endpoint_key == "consulta_lote":
                return self.get_soap_service_url("consulta_lote")
            elif endpoint_key == "consulta":
                return self.get_soap_service_url("consulta")
        
        # Legacy REST endpoints (no usados en producción según guía)
        raise ValueError(f"Endpoint '{endpoint_key}' no disponible. Use get_soap_service_url() para servicios SOAP")


def get_sifen_config(env: Optional[str] = None) -> SifenConfig:
    """
    Obtiene la configuración SIFEN desde variables de entorno
    
    Args:
        env: Ambiente ('test' o 'prod'). Si None, usa SIFEN_ENV
        
    Returns:
        Configuración SIFEN
    """
    if env is None:
        env = os.getenv("SIFEN_ENV", SifenConfig.ENV_TEST)
    
    cfg = SifenConfig(env)
    
    # Cargar certificado desde variables de entorno si no están ya asignados
    # (esto permite que funcionen incluso si use_mtls=False en el __init__)
    # Usar helper unificado para mantener compatibilidad con ambos nombres
    # El helper valida y lanza RuntimeError si faltan env vars
    if not cfg.cert_path or not cfg.cert_password:
        try:
            env_cert_path, env_cert_password = get_cert_path_and_password()
            cfg.cert_path = cfg.cert_path or env_cert_path
            cfg.cert_password = cfg.cert_password or env_cert_password
        except RuntimeError:
            # Si falla, dejar como None (puede ser configuración opcional en algunos casos)
            pass
    
    # Cargar rutas PEM directas (prioridad sobre PKCS12)
    if not cfg.cert_pem_path:
        cfg.cert_pem_path = os.getenv("SIFEN_CERT_PEM_PATH")
    if not cfg.key_pem_path:
        cfg.key_pem_path = os.getenv("SIFEN_KEY_PEM_PATH")
    
    return cfg

