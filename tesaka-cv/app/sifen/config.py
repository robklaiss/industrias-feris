"""
Configuración para módulo SIFEN (backend)

Centraliza la lectura de variables de entorno y provee configuración
repetible sin secretos en el repo.
"""
import os
from typing import Dict, Tuple, Optional, Any
from pathlib import Path

# Cargar dotenv si está disponible
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_sifen_endpoints(env: str = "test") -> Dict[str, str]:
    """
    Obtiene las URLs de endpoints SIFEN según el ambiente.
    
    Args:
        env: Ambiente ('test' o 'prod')
        
    Returns:
        Dict con:
        - consulta_ruc_wsdl_url: URL para GET con ?wsdl (metadatos)
        - consulta_ruc_post_url: URL para POST sin ?wsdl (SOAP request)
    """
    if env == "test":
        base = "https://sifen-test.set.gov.py"
    elif env == "prod":
        base = "https://sifen.set.gov.py"
    else:
        raise ValueError(f"Ambiente inválido: {env}. Debe ser 'test' o 'prod'")
    
    wsdl_path = "/de/ws/consultas/consulta-ruc.wsdl"
    
    return {
        "consulta_ruc_wsdl_url": f"{base}{wsdl_path}?wsdl",  # GET con ?wsdl
        "consulta_ruc_post_url": f"{base}{wsdl_path}",       # POST sin ?wsdl
    }


class SifenConfig:
    """Configuración del módulo SIFEN"""
    
    def __init__(self, env: str = None, p12_path: Optional[str] = None, p12_password: Optional[str] = None):
        """
        Inicializa configuración SIFEN.
        
        Args:
            env: Ambiente ('test' o 'prod'). Si None, usa SIFEN_ENV o default 'test'
            p12_path: Ruta al archivo P12. Si None, lee de SIFEN_P12_PATH o busca default
            p12_password: Password del P12. Si None, lee de SIFEN_P12_PASS (opcional)
        """
        # Ambiente
        if env is None:
            env = os.getenv("SIFEN_ENV", "test")
        if env not in ("test", "prod"):
            raise ValueError(f"SIFEN_ENV inválido: {env}. Debe ser 'test' o 'prod'")
        self.env = env
        
        # Endpoints
        endpoints = get_sifen_endpoints(env)
        self.consulta_ruc_wsdl_url = endpoints["consulta_ruc_wsdl_url"]
        self.consulta_ruc_post_url = endpoints["consulta_ruc_post_url"]
        
        # RUC default para consultas
        self.ruc_cons_default = os.getenv("SIFEN_RUC_CONS_DEFAULT")
        
        # Certificado P12
        if p12_path is None:
            # Buscar en SIFEN_P12_PATH o default ~/.sifen/certs/*.p12
            p12_path = os.getenv("SIFEN_P12_PATH")
            if not p12_path:
                # Buscar default en ~/.sifen/certs/
                default_dir = Path.home() / ".sifen" / "certs"
                if default_dir.exists():
                    # Buscar primer .p12
                    p12_files = list(default_dir.glob("*.p12"))
                    if p12_files:
                        p12_path = str(p12_files[0])
        
        if not p12_path:
            raise ValueError(
                "SIFEN_P12_PATH no está configurado y no se encontró certificado en ~/.sifen/certs/*.p12. "
                "Configure SIFEN_P12_PATH en .env o coloque el certificado en ~/.sifen/certs/"
            )
        
        if not os.path.exists(p12_path):
            raise ValueError(f"Certificado P12 no encontrado: {p12_path}")
        
        self.p12_path = p12_path
        
        # Password (opcional en __init__, puede pedirse interactivo en CLI)
        if p12_password is None:
            p12_password = os.getenv("SIFEN_P12_PASS")
        self.p12_password = p12_password  # Puede ser None (se pedirá interactivo en CLI si falta)


def get_sifen_config(env: Optional[str] = None, p12_path: Optional[str] = None, p12_password: Optional[str] = None) -> SifenConfig:
    """
    Factory para obtener configuración SIFEN.
    
    Args:
        env: Ambiente (opcional, default desde SIFEN_ENV)
        p12_path: Ruta P12 (opcional, default desde SIFEN_P12_PATH)
        p12_password: Password P12 (opcional, default desde SIFEN_P12_PASS)
        
    Returns:
        SifenConfig instance
    """
    return SifenConfig(env=env, p12_path=p12_path, p12_password=p12_password)


class SifenConfigError(Exception):
    """Error de configuración SIFEN"""
    pass


def validate_required_env(is_web: bool = True) -> Dict[str, Any]:
    """
    Valida las variables de entorno requeridas para SIFEN.
    
    Args:
        is_web: Si True, requiere password en env. Si False (CLI), permite password vacío.
    
    Returns:
        Dict con configuración resuelta:
        - env: Ambiente ('test' o 'prod')
        - endpoints: Dict con URLs
        - p12_path: Ruta al certificado
        - p12_password: Password (puede ser None en modo CLI)
        
    Raises:
        SifenConfigError: Si la configuración no es válida
    """
    # Validar SIFEN_ENV
    env = os.getenv("SIFEN_ENV", "test")
    if env not in ("test", "prod"):
        raise SifenConfigError(
            f"SIFEN_ENV inválido: '{env}'. Debe ser 'test' o 'prod'"
        )
    
    # Obtener endpoints
    endpoints = get_sifen_endpoints(env)
    
    # Validar P12 path
    p12_path = os.getenv("SIFEN_P12_PATH")
    if not p12_path:
        # Buscar default en ~/.sifen/certs/
        default_dir = Path.home() / ".sifen" / "certs"
        if default_dir.exists():
            p12_files = list(default_dir.glob("*.p12"))
            if p12_files:
                p12_path = str(p12_files[0])
    
    if not p12_path:
        raise SifenConfigError(
            "SIFEN_P12_PATH no está configurado y no se encontró certificado en ~/.sifen/certs/*.p12. "
            "Configure SIFEN_P12_PATH en .env o coloque el certificado en ~/.sifen/certs/"
        )
    
    if not os.path.exists(p12_path):
        raise SifenConfigError(
            f"Certificado P12 no encontrado en: {p12_path}. "
            "Verifique que el archivo existe y que SIFEN_P12_PATH apunta al archivo correcto."
        )
    
    # Validar password según modo
    p12_password = os.getenv("SIFEN_P12_PASSWORD") or os.getenv("SIFEN_P12_PASS")
    
    if is_web:
        # En modo web, el password debe estar en env
        if not p12_password:
            raise SifenConfigError(
                "SIFEN_P12_PASSWORD o SIFEN_P12_PASS no está configurado. "
                "En modo web, el password debe estar en variables de entorno."
            )
    # En modo CLI, el password puede ser None (se pedirá interactivo)
    
    return {
        "env": env,
        "endpoints": endpoints,
        "p12_path": p12_path,
        "p12_password": p12_password,
    }
