"""
Configuración para cliente SIFEN
"""
import os
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


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
    
    # Servicios Web SOAP según Guía de Mejores Prácticas
    # Los documentos electrónicos se envían en lotes (hasta 50 DE por lote)
    # Fuente: Guía de Mejores Prácticas, pág. 5-6
    SOAP_SERVICES = {
        "test": {
            "recibe_lote": "https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl",
            "consulta_lote": "https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl",
            "consulta": "https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl",
        },
        "prod": {
            "recibe_lote": "https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl",
            "consulta_lote": "https://sifen.set.gov.py/de/ws/consultas/consulta-lote.wsdl",
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
        
        # Autenticación - REQUIERE CONFIRMACIÓN
        # TODO: Verificar tipo de autenticación desde documentación
        self.use_mtls = os.getenv("SIFEN_USE_MTLS", "false").lower() == "true"
        
        if self.use_mtls:
            # Configuración mTLS (mutual TLS)
            cert_path = os.getenv("SIFEN_CERT_PATH")
            cert_password = os.getenv("SIFEN_CERT_PASSWORD", "")
            ca_bundle_path = os.getenv("SIFEN_CA_BUNDLE_PATH")
            
            if not cert_path:
                raise ValueError("SIFEN_CERT_PATH debe estar configurado cuando SIFEN_USE_MTLS=true")
            
            self.cert_path = Path(cert_path)
            self.cert_password = cert_password
            self.ca_bundle_path = Path(ca_bundle_path) if ca_bundle_path else None
            
            if not self.cert_path.exists():
                raise FileNotFoundError(f"Certificado no encontrado: {self.cert_path}")
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
        """
        if service_key not in ["recibe_lote", "consulta_lote", "consulta"]:
            raise ValueError(f"Servicio SOAP inválido: {service_key}")
        
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
    
    return SifenConfig(env)

