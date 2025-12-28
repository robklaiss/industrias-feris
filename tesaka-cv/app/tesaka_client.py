"""
Cliente HTTP para comunicación con la API RESTful de Tesaka (SET)
"""
import json
import httpx
from typing import Dict, Any, Optional, List
from pathlib import Path


class TesakaClientError(Exception):
    """Excepción base para errores del cliente Tesaka"""
    pass


class TesakaClient:
    """
    Cliente HTTP para enviar comprobantes a Tesaka (SET)
    
    Soporta entorno de producción (prod) y homologación (homo)
    """
    
    # URLs base según entorno
    BASE_URLS = {
        'prod': 'https://marangatu.set.gov.py/eset-restful',
        'homo': 'https://m2hom.set.gov.py/servicios-retenciones'
    }
    
    # Endpoints
    ENDPOINTS = {
        'factura': '/facturas/guardar',
        'retencion': '/retenciones/guardar',
        'autofactura': '/autofacturas/guardar',
        'contribuyente': '/contribuyentes/consultar'
    }
    
    def __init__(self, env: str = 'homo', user: str = '', password: str = '', timeout: int = 30, verify: bool = True):
        """
        Inicializa el cliente Tesaka
        
        Args:
            env: Entorno a usar ('prod' o 'homo')
            user: Usuario para Basic Auth
            password: Contraseña para Basic Auth
            timeout: Timeout de peticiones HTTP en segundos
            verify: Si verificar certificados SSL (default: True)
        """
        if env not in self.BASE_URLS:
            raise ValueError(f"Entorno inválido: {env}. Debe ser 'prod' o 'homo'")
        
        self.env = env
        self.base_url = self.BASE_URLS[env]
        self.user = user
        self.password = password
        self.timeout = timeout
        self.verify = verify
        
        # Configurar cliente HTTP
        self.client = httpx.Client(
            auth=(self.user, self.password),
            timeout=self.timeout,
            verify=self.verify
        )
    
    def _build_url(self, endpoint_key: str) -> str:
        """Construye la URL completa del endpoint"""
        endpoint = self.ENDPOINTS.get(endpoint_key)
        if not endpoint:
            raise ValueError(f"Endpoint inválido: {endpoint_key}")
        return f"{self.base_url}{endpoint}"
    
    def _make_request(self, method: str, url: str, json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Realiza una petición HTTP y maneja errores
        
        Returns:
            Diccionario con la respuesta JSON
            
        Raises:
            TesakaClientError: Si hay algún error en la petición
        """
        try:
            response = self.client.request(method, url, json=json_data)
            
            # Manejar diferentes códigos de estado
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    raise TesakaClientError(f"Respuesta no es JSON válido: {response.text[:200]}")
            
            elif response.status_code == 401:
                raise TesakaClientError("Error de autenticación (401): Usuario o contraseña incorrectos")
            
            elif response.status_code == 400:
                error_msg = "Error de validación (400)"
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        error_msg += f": {error_data['message']}"
                    elif 'error' in error_data:
                        error_msg += f": {error_data['error']}"
                except:
                    error_msg += f": {response.text[:200]}"
                raise TesakaClientError(error_msg)
            
            elif response.status_code >= 500:
                raise TesakaClientError(f"Error del servidor Tesaka ({response.status_code}): {response.text[:200]}")
            
            else:
                raise TesakaClientError(f"Error HTTP {response.status_code}: {response.text[:200]}")
                
        except httpx.TimeoutException:
            raise TesakaClientError(f"Timeout: La petición excedió {self.timeout} segundos")
        
        except httpx.RequestError as e:
            raise TesakaClientError(f"Error de conexión: {str(e)}")
        
        except TesakaClientError:
            raise
        
        except Exception as e:
            raise TesakaClientError(f"Error inesperado: {str(e)}")
    
    def enviar_facturas(self, payload_json_array: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Envía facturas a Tesaka
        
        Args:
            payload_json_array: Lista de comprobantes Tesaka (formato importación)
            
        Returns:
            Respuesta del servidor Tesaka
        """
        url = self._build_url('factura')
        return self._make_request('POST', url, json_data=payload_json_array)
    
    def enviar_retenciones(self, payload_json_array: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Envía retenciones a Tesaka
        
        Args:
            payload_json_array: Lista de comprobantes Tesaka (formato importación)
            
        Returns:
            Respuesta del servidor Tesaka
        """
        url = self._build_url('retencion')
        return self._make_request('POST', url, json_data=payload_json_array)
    
    def enviar_autofacturas(self, payload_json_array: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Envía autofacturas a Tesaka
        
        Args:
            payload_json_array: Lista de comprobantes Tesaka (formato importación)
            
        Returns:
            Respuesta del servidor Tesaka
        """
        url = self._build_url('autofactura')
        return self._make_request('POST', url, json_data=payload_json_array)
    
    def consultar_contribuyente(self, ruc: str) -> Dict[str, Any]:
        """
        Consulta información de un contribuyente por RUC
        
        Args:
            ruc: RUC del contribuyente
            
        Returns:
            Información del contribuyente
        """
        url = self._build_url('contribuyente')
        # Ajustar según la API real - podría necesitar parámetros en query o body
        return self._make_request('GET', f"{url}?ruc={ruc}")
    
    def close(self):
        """Cierra el cliente HTTP"""
        self.client.close()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()

